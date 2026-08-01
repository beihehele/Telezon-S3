"""Count DB references to a Telegram message_id before delete."""

from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import BlobRow, MultipartPartRow, TrashRow


def _parts_list(raw: list | None) -> list[dict]:
    if not raw:
        return []
    out: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
    return out


def _count_mid_in_parts_json(parts: list | None, message_id: int) -> int:
    n = 0
    for part in _parts_list(parts):
        if part.get("message_id") == message_id:
            n += 1
    return n


async def count_message_id_refs(db: AsyncSession, message_id: int) -> int:
    if message_id is None:
        return 0
    mid = int(message_id)
    total = 0

    result = await db.execute(
        select(func.count()).select_from(BlobRow).where(BlobRow.message_id == mid)
    )
    total += int(result.scalar_one() or 0)

    result = await db.execute(
        select(func.count()).select_from(TrashRow).where(TrashRow.message_id == mid)
    )
    total += int(result.scalar_one() or 0)

    result = await db.execute(
        select(func.count())
        .select_from(MultipartPartRow)
        .where(MultipartPartRow.message_id == mid)
    )
    total += int(result.scalar_one() or 0)

    bind = db.get_bind()
    dialect = bind.dialect.name if bind is not None else "mysql"
    if dialect == "mysql":
        try:
            result = await db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM (
                        SELECT j.mid AS mid FROM blobs b,
                        JSON_TABLE(b.parts, '$[*]' COLUMNS (mid BIGINT PATH '$.message_id')) j
                        WHERE b.parts IS NOT NULL
                        UNION ALL
                        SELECT j.mid FROM trash t,
                        JSON_TABLE(t.parts, '$[*]' COLUMNS (mid BIGINT PATH '$.message_id')) j
                        WHERE t.parts IS NOT NULL
                    ) x WHERE x.mid = :mid
                    """
                ),
                {"mid": mid},
            )
            total += int(result.scalar_one() or 0)
            return total
        except Exception:
            pass

    result = await db.execute(
        select(BlobRow.parts).where(BlobRow.parts.isnot(None))
    )
    for (parts,) in result.all():
        total += _count_mid_in_parts_json(parts, mid)

    result = await db.execute(
        select(TrashRow.parts).where(TrashRow.parts.isnot(None))
    )
    for (parts,) in result.all():
        total += _count_mid_in_parts_json(parts, mid)

    return total
