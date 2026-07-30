from app.models.blob import BlobInDb
from app.s3.xml import build_list_buckets_xml, build_list_objects_v2_xml, object_etag
from app.models.bucket import Bucket
from app.models.user import User


def test_object_etag_stable():
    blob = BlobInDb(path="a.txt", file="fid", size=3, bucket_name="b")
    assert object_etag(blob) == '"fid-3"'


def test_list_objects_xml_contains_keys():
    blobs = [
        BlobInDb(path="a.txt", file="f1", size=1, bucket_name="bucket"),
        BlobInDb(path="b.txt", file="f2", size=2, bucket_name="bucket"),
    ]
    xml = build_list_objects_v2_xml(
        bucket_name="bucket",
        prefix="",
        max_keys=1000,
        blobs=blobs,
        is_truncated=False,
        next_continuation_token=None,
        continuation_token=None,
        start_after=None,
    )
    assert "<Key>a.txt</Key>" in xml
    assert "<Key>b.txt</Key>" in xml
    assert "<IsTruncated>false</IsTruncated>" in xml


def test_list_buckets_xml():
    owner = User(username="alice", email="a@b.c", access_key_id="AK", secret_key="SK")
    bucket = Bucket(name="alice", owner=owner, size=0)
    xml = build_list_buckets_xml([bucket], owner_id="AK", owner_display="alice")
    assert "<Name>alice</Name>" in xml
    assert "<DisplayName>alice</DisplayName>" in xml
