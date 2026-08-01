from app.s3.list_query import looks_like_list_objects


def test_looks_like_list_objects_detects_s3_browser_query():
    class Q:
        query_params = {
            "delimiter": "/",
            "max-keys": "1000",
            "prefix": "",
        }

    assert looks_like_list_objects(Q()) is True


def test_looks_like_list_objects_empty_query():
    class Q:
        query_params = {}

    assert looks_like_list_objects(Q()) is False
