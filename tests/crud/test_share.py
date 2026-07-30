from datetime import datetime, timedelta, timezone

import pytest

from app.crud.share import (
    crud_claim_share_download,
    crud_create_share,
    crud_get_share,
    crud_release_share_download,
    share_is_usable,
    share_password_ok,
)
from app.db.tables import ShareRow
from app.models.share import ShareInCreate


@pytest.mark.asyncio
async def test_share_create_and_password(mock_db):
    share = await crud_create_share(
        mock_db,
        ShareInCreate(
            bucket="alice",
            key="a.txt",
            password="secret",
            expires_in=3600,
            max_downloads=2,
        ),
        owner_username="alice",
    )
    loaded = await crud_get_share(mock_db, share.token)
    assert loaded is not None
    assert share_is_usable(loaded) is True
    assert share_password_ok(loaded, "secret") is True
    assert share_password_ok(loaded, "wrong") is False


@pytest.mark.asyncio
async def test_share_max_downloads(mock_db):
    share = await crud_create_share(
        mock_db,
        ShareInCreate(bucket="alice", key="a.txt", expires_in=3600, max_downloads=1),
        owner_username="alice",
    )
    claimed = await crud_claim_share_download(mock_db, share.token)
    assert claimed is not None
    again = await crud_claim_share_download(mock_db, share.token)
    assert again is None


@pytest.mark.asyncio
async def test_share_release_download_quota(mock_db):
    share = await crud_create_share(
        mock_db,
        ShareInCreate(bucket="alice", key="a.txt", expires_in=3600, max_downloads=2),
        owner_username="alice",
    )
    claimed = await crud_claim_share_download(mock_db, share.token)
    assert claimed is not None
    assert claimed.download_count == 1
    released = await crud_release_share_download(mock_db, share.token)
    assert released is True
    loaded = await crud_get_share(mock_db, share.token)
    assert loaded is not None
    assert loaded.download_count == 0


@pytest.mark.asyncio
async def test_share_expiry(mock_db):
    share = await crud_create_share(
        mock_db,
        ShareInCreate(bucket="alice", key="a.txt", expires_in=60),
        owner_username="alice",
    )
    row = await mock_db.get(ShareRow, share.token)
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await mock_db.flush()
    loaded = await crud_get_share(mock_db, share.token)
    assert share_is_usable(loaded) is False
