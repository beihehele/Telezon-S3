from datetime import datetime, timezone
from xml.sax.saxutils import escape

from app.models.blob import BlobInDb
from app.models.bucket import Bucket


def _fmt_iso(dt: datetime | None) -> str:
    if dt is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def object_etag(blob: BlobInDb) -> str:
    return f'"{blob.file or blob.path}-{blob.size}"'


def build_list_buckets_xml(buckets: list[Bucket], owner_id: str, owner_display: str) -> str:
    bucket_xml = []
    for bucket in buckets:
        bucket_xml.append(
            "<Bucket>"
            f"<Name>{escape(bucket.name)}</Name>"
            f"<CreationDate>{_fmt_iso(bucket.created_at)}</CreationDate>"
            "</Bucket>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ListAllMyBucketsResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        "<Owner>"
        f"<ID>{escape(owner_id)}</ID>"
        f"<DisplayName>{escape(owner_display)}</DisplayName>"
        "</Owner>"
        f"<Buckets>{''.join(bucket_xml)}</Buckets>"
        "</ListAllMyBucketsResult>"
    )


def rollup_with_delimiter(
    blobs: list[BlobInDb],
    *,
    prefix: str,
    delimiter: str,
    max_keys: int,
) -> tuple[list[BlobInDb], list[str], bool, str | None]:
    """Fold keys into Contents + CommonPrefixes (S3 delimiter semantics)."""
    contents: list[BlobInDb] = []
    common_prefixes: list[str] = []
    seen: set[str] = set()
    last_key: str | None = None
    truncated = False

    for blob in blobs:
        key = blob.path
        last_key = key
        if prefix and not key.startswith(prefix):
            continue
        rest = key[len(prefix) :]
        if delimiter and delimiter in rest:
            common = prefix + rest.split(delimiter, 1)[0] + delimiter
            if common in seen:
                continue
            seen.add(common)
            common_prefixes.append(common)
        else:
            contents.append(blob)

        if len(contents) + len(common_prefixes) >= max_keys:
            truncated = True
            break

    if not truncated and last_key is not None and len(blobs) > 0:
        # Caller may have fetched max_keys+1 raw rows; truncation decided upstream.
        pass

    return contents, common_prefixes, truncated, last_key


def build_list_objects_v2_xml(
    *,
    bucket_name: str,
    prefix: str,
    max_keys: int,
    blobs: list[BlobInDb],
    is_truncated: bool,
    next_continuation_token: str | None,
    continuation_token: str | None,
    start_after: str | None,
    delimiter: str | None = None,
    common_prefixes: list[str] | None = None,
) -> str:
    contents = []
    for blob in blobs:
        contents.append(
            "<Contents>"
            f"<Key>{escape(blob.path)}</Key>"
            f"<LastModified>{_fmt_iso(getattr(blob, 'updated_at', None) or getattr(blob, 'created_at', None))}</LastModified>"
            f"<ETag>{escape(object_etag(blob))}</ETag>"
            f"<Size>{int(blob.size or 0)}</Size>"
            "<StorageClass>STANDARD</StorageClass>"
            "</Contents>"
        )

    prefix_xml = []
    for common in common_prefixes or []:
        prefix_xml.append(
            "<CommonPrefixes>"
            f"<Prefix>{escape(common)}</Prefix>"
            "</CommonPrefixes>"
        )

    key_count = len(blobs) + len(common_prefixes or [])
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">',
        f"<Name>{escape(bucket_name)}</Name>",
        f"<Prefix>{escape(prefix)}</Prefix>",
        f"<MaxKeys>{max_keys}</MaxKeys>",
        f"<KeyCount>{key_count}</KeyCount>",
        f"<IsTruncated>{str(is_truncated).lower()}</IsTruncated>",
    ]
    if delimiter:
        parts.append(f"<Delimiter>{escape(delimiter)}</Delimiter>")
    if continuation_token:
        parts.append(f"<ContinuationToken>{escape(continuation_token)}</ContinuationToken>")
    if next_continuation_token:
        parts.append(
            f"<NextContinuationToken>{escape(next_continuation_token)}</NextContinuationToken>"
        )
    if start_after:
        parts.append(f"<StartAfter>{escape(start_after)}</StartAfter>")
    parts.extend(contents)
    parts.extend(prefix_xml)
    parts.append("</ListBucketResult>")
    return "".join(parts)
