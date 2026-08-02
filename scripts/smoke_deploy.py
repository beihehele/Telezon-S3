#!/usr/bin/env python3
"""Post-deploy smoke checks against a running Telezon-S3 instance."""

from __future__ import annotations

import os
import sys
import time
import uuid
from urllib.parse import quote

import httpx

USER = os.environ.get("CONSOLE_E2E_USER", "")
PASSWORD = os.environ.get("CONSOLE_E2E_PASSWORD", "")
TIMEOUT = float(os.environ.get("TELEZON_SMOKE_TIMEOUT", "30"))
TIMEOUT_TG = float(os.environ.get("TELEZON_SMOKE_TG_TIMEOUT", "180"))
CONTENT_PROXY_LIMIT = 8 * 1024 * 1024

# Result: (name, status, detail) where status is pass | fail | skip
Result = tuple[str, str, str]


class Check:
    def __init__(self) -> None:
        self.results: list[Result] = []

    def ok(self, name: str, detail: str = "") -> None:
        self.results.append((name, "pass", detail))

    def fail(self, name: str, detail: str) -> None:
        self.results.append((name, "fail", detail))

    def skip(self, name: str, detail: str) -> None:
        self.results.append((name, "skip", detail))

    def exit_code(self) -> int:
        return 1 if any(s == "fail" for _, s, _ in self.results) else 0


def _base_url() -> str:
    raw = os.environ.get("TELEZON_SMOKE_BASE", "").strip().rstrip("/")
    if not raw:
        print(
            "Set TELEZON_SMOKE_BASE (e.g. http://192.168.0.115:8088)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return raw


def _object_path(bucket: str, key: str, suffix: str = "") -> str:
    enc = quote(key, safe="/")
    return f"/api/v1/buckets/{quote(bucket, safe='')}/objects/{enc}{suffix}"


def _bucket_owner_username(entry: dict) -> str | None:
    owner = entry.get("owner")
    if isinstance(owner, dict):
        return owner.get("username")
    if entry.get("owner_username"):
        return str(entry["owner_username"])
    return None


def main() -> int:
    base = _base_url()
    c = Check()
    if not USER or not PASSWORD:
        print("Set CONSOLE_E2E_USER and CONSOLE_E2E_PASSWORD", file=sys.stderr)
        return 2

    with httpx.Client(base_url=base, timeout=TIMEOUT, follow_redirects=True) as client:
        try:
            r = client.get("/api/health")
            if r.status_code == 200 and r.json().get("status") == "ok":
                db_ok = r.json().get("database", {}).get("ok")
                tg_ok = r.json().get("telegram", {}).get("ok")
                c.ok("health", f"db={db_ok} telegram={tg_ok}")
            else:
                c.fail("health", f"status={r.status_code} body={r.text[:200]}")
        except httpx.HTTPError as e:
            c.fail("health", str(e))
            _report(c, base)
            return c.exit_code()

        try:
            r = client.get("/console/")
            if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
                if "NoSuchBucket" in r.text or "<Code>NoSuchBucket</Code>" in r.text:
                    c.fail("console_spa", "S3 NoSuchBucket on /console/")
                else:
                    c.ok("console_spa", f"{len(r.content)} bytes html")
            else:
                c.fail("console_spa", f"status={r.status_code}")
        except httpx.HTTPError as e:
            c.fail("console_spa", str(e))

        try:
            r = client.get("/console", follow_redirects=False)
            if r.status_code in (301, 302, 307, 308):
                c.ok("console_redirect", f"{r.status_code} -> {r.headers.get('location', '')}")
            else:
                c.fail("console_redirect", f"status={r.status_code}")
        except httpx.HTTPError as e:
            c.fail("console_redirect", str(e))

        try:
            r = client.get("/api/auth/config")
            if r.status_code == 200 and "allow_signup" in r.json():
                c.ok("auth_config", f"allow_signup={r.json()['allow_signup']}")
            else:
                c.fail("auth_config", f"status={r.status_code}")
        except httpx.HTTPError as e:
            c.fail("auth_config", str(e))

        token = ""
        try:
            r = client.post(
                "/api/auth/login",
                data={"username": USER, "password": PASSWORD},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if r.status_code == 200 and r.json().get("access_token"):
                token = r.json()["access_token"]
                c.ok("login", "bearer token issued")
            else:
                c.fail("login", f"status={r.status_code} detail={r.text[:120]}")
        except httpx.HTTPError as e:
            c.fail("login", str(e))

        if not token:
            _report(c, base)
            return c.exit_code()

        headers = {"Authorization": f"Bearer {token}"}
        buckets_json: list[dict] = []
        bucket = USER

        try:
            r = client.get("/api/v1/buckets/", headers=headers)
            if r.status_code != 200:
                c.fail("list_buckets", f"status={r.status_code}")
            else:
                buckets_json = r.json()
                names = [b.get("name") for b in buckets_json]
                if names:
                    bucket = names[0]
                c.ok("list_buckets", f"count={len(names)} first={bucket}")
        except httpx.HTTPError as e:
            c.fail("list_buckets", str(e))

        large_key: str | None = None
        large_size = 0
        try:
            r = client.get(
                f"/api/v1/buckets/{quote(bucket, safe='')}/objects",
                headers=headers,
                params={"delimiter": "/", "max_keys": 50},
            )
            if r.status_code == 200:
                contents = r.json().get("contents") or []
                for obj in contents:
                    sz = int(obj.get("size") or 0)
                    if sz > large_size:
                        large_size = sz
                        large_key = obj.get("key")
                c.ok("list_objects", f"contents={len(contents)} largest={large_size}")
            else:
                c.fail("list_objects", f"status={r.status_code}")
        except httpx.HTTPError as e:
            c.fail("list_objects", str(e))

        try:
            others = [
                b["name"]
                for b in buckets_json
                if _bucket_owner_username(b) not in (USER, None)
            ]
            if not others:
                c.skip(
                    "admin_no_cross_bucket",
                    "no bucket owned by another user in list",
                )
            else:
                other = others[0]
                r = client.get(
                    f"/api/v1/buckets/{quote(other, safe='')}/objects",
                    headers=headers,
                    params={"max_keys": 1},
                )
                if r.status_code == 403:
                    c.ok("admin_no_cross_bucket", f"{other} -> 403")
                else:
                    c.fail("admin_no_cross_bucket", f"{other} status={r.status_code}")
        except httpx.HTTPError as e:
            c.fail("admin_no_cross_bucket", str(e))

        smoke_key = f".__smoke__/probe-{int(time.time())}-{uuid.uuid4().hex[:8]}.txt"
        body = b"telezon-smoke\n"
        put_ok = False
        try:
            pr = client.post(
                "/api/v1/presign/",
                headers=headers,
                json={"bucket": bucket, "key": smoke_key, "method": "PUT"},
            )
            if pr.status_code != 200:
                c.fail("presign_put", f"status={pr.status_code}")
            else:
                put_r = httpx.put(pr.json()["url"], content=body, timeout=TIMEOUT)
                if put_r.status_code not in (200, 201, 204):
                    c.fail("presign_put_upload", f"status={put_r.status_code}")
                else:
                    put_ok = True
                    c.ok("presign_put_upload", smoke_key)
                    gr = client.post(
                        "/api/v1/presign/",
                        headers=headers,
                        json={"bucket": bucket, "key": smoke_key, "method": "GET"},
                    )
                    if gr.status_code != 200:
                        c.fail("presign_get", f"status={gr.status_code}")
                    else:
                        get_r = httpx.get(gr.json()["url"], timeout=TIMEOUT_TG)
                        if get_r.content == body:
                            c.ok("presign_get_download", f"{len(body)} bytes")
                        else:
                            c.fail(
                                "presign_get_download",
                                f"len={len(get_r.content)} status={get_r.status_code}",
                            )
        except httpx.HTTPError as e:
            c.fail("presign_roundtrip", str(e))

        if put_ok:
            try:
                del_r = client.delete(_object_path(bucket, smoke_key), headers=headers)
                if del_r.status_code in (200, 204):
                    c.ok("delete_smoke_object", smoke_key)
                else:
                    c.fail("delete_smoke_object", f"status={del_r.status_code}")
            except httpx.HTTPError as e:
                c.fail("delete_smoke_object", str(e))

        if large_key and large_size > CONTENT_PROXY_LIMIT:
            try:
                tr = client.post(
                    _object_path(bucket, large_key, "/content-ticket"),
                    headers=headers,
                )
                if tr.status_code != 200:
                    c.fail("content_ticket", f"status={tr.status_code}")
                else:
                    params = {"media_token": tr.json()["media_token"]}
                    content_path = _object_path(bucket, large_key, "/content")
                    full = client.get(content_path, params=params)
                    if full.status_code == 413:
                        c.ok("content_413_no_range", f"size={large_size}")
                    else:
                        c.fail(
                            "content_413_no_range",
                            f"expected 413 got {full.status_code}",
                        )
                    rng = client.get(
                        content_path,
                        params=params,
                        headers={"Range": "bytes=0-1023"},
                        timeout=TIMEOUT_TG,
                    )
                    if rng.status_code == 206 and len(rng.content) == 1024:
                        c.ok("content_range_206", large_key)
                    else:
                        c.fail(
                            "content_range_206",
                            f"status={rng.status_code} len={len(rng.content)}",
                        )
            except httpx.HTTPError as e:
                c.fail("content_proxy_large", str(e))
        else:
            c.skip(
                "content_413_no_range",
                f"no object >8MB in first 50 keys (largest={large_size})",
            )
            c.skip("content_range_206", "same as content_413_no_range")

    _report(c, base)
    return c.exit_code()


def _report(c: Check, base: str) -> None:
    print(f"Base: {base}\n")
    w = max(len(n) for n, _, _ in c.results) if c.results else 10
    for name, status, detail in c.results:
        mark = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[status]
        line = f"[{mark}] {name.ljust(w)}"
        if detail:
            line += f"  {detail}"
        print(line)
    n_pass = sum(1 for _, s, _ in c.results if s == "pass")
    n_fail = sum(1 for _, s, _ in c.results if s == "fail")
    n_skip = sum(1 for _, s, _ in c.results if s == "skip")
    print(f"\n{n_pass} passed, {n_fail} failed, {n_skip} skipped")


if __name__ == "__main__":
    raise SystemExit(main())
