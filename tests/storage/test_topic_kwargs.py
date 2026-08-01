from app.storage.telegram.topic import (
    bot_api_document_topic_kwargs,
    pyrogram_document_topic_kwargs,
)


def test_pyrogram_topic_uses_reply_to_message_id():
    assert pyrogram_document_topic_kwargs(None) == {}
    assert pyrogram_document_topic_kwargs(7) == {"reply_to_message_id": 7}


def test_bot_api_topic_uses_message_thread_id():
    assert bot_api_document_topic_kwargs(None) == {}
    assert bot_api_document_topic_kwargs(7) == {"message_thread_id": 7}
