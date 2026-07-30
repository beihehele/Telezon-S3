from app.storage.storage import PutFileResult


def test_put_file_result_fields():
    result = PutFileResult(file_id="abc", message_id=42)
    assert result.file_id == "abc"
    assert result.message_id == 42


def test_put_file_result_message_id_optional():
    result = PutFileResult(file_id="abc")
    assert result.message_id is None
