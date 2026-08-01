from uuid import uuid4


def new_storage_id() -> str:
    return uuid4().hex


def tg_document_label(storage_id: str, *, part_number: int | None = None) -> str:
    if part_number is not None:
        return f"{storage_id}.part{part_number}"
    return f"{storage_id}.bin"
