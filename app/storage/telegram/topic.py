"""Map bucket telegram_topic_id to client-specific send kwargs."""


def pyrogram_document_topic_kwargs(topic_id: int | None) -> dict:
    """Pyrogram 2.0.x send_document: use reply_to_message_id for forum topics."""
    if topic_id is None:
        return {}
    return {"reply_to_message_id": topic_id}


def bot_api_document_topic_kwargs(topic_id: int | None) -> dict:
    """python-telegram-bot: message_thread_id for forum topics."""
    if topic_id is None:
        return {}
    return {"message_thread_id": topic_id}
