"""SQLAlchemy ORM tables (single MySQL database)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="", server_default="")
    role: Mapped[str] = mapped_column(String(32), default="user", server_default="user")
    access_key_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    secret_key: Mapped[str] = mapped_column(String(128), default="")
    salt: Mapped[str] = mapped_column(String(64), default="")
    hashed_password: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BucketRow(Base):
    __tablename__ = "buckets"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    owner_username: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.username", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_topic_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BlobRow(Base):
    __tablename__ = "blobs"
    __table_args__ = (
        UniqueConstraint("bucket_name", "path_digest", name="uq_blob_bucket_path"),
        Index(
            "ix_blobs_bucket_path",
            "bucket_name",
            "path",
            # utf8mb4: 255*4 + 512*4 <= 3072 (InnoDB max key length)
            mysql_length={"path": 512},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_name: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("buckets.name", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    path_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    telegram_grouped_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_albums: Mapped[list | None] = mapped_column(JSON, nullable=True)
    file: Mapped[str] = mapped_column(String(512), default="")
    content_type: Mapped[str] = mapped_column(String(255), default="")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    parts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sse_nonce: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sse_tag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CredentialRow(Base):
    __tablename__ = "credentials"

    access_key_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    secret_key: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_username: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.username", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    buckets: Mapped[list] = mapped_column(JSON, default=list)
    label: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ShareRow(Base):
    __tablename__ = "shares"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_downloads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    owner_username: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TrashRow(Base):
    __tablename__ = "trash"

    trash_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bucket_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    storage_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    telegram_grouped_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_albums: Mapped[list | None] = mapped_column(JSON, nullable=True)
    file: Mapped[str] = mapped_column(String(512), default="")
    content_type: Mapped[str] = mapped_column(String(255), default="")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    parts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sse_nonce: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sse_tag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[str] = mapped_column(String(64), default="")
    reason: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MultipartUploadRow(Base):
    __tablename__ = "multipart_uploads"

    upload_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bucket: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), default="")
    owner_access_key: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MultipartPartRow(Base):
    __tablename__ = "multipart_parts"
    __table_args__ = (
        UniqueConstraint("upload_id", "part_number", name="uq_multipart_part"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    upload_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("multipart_uploads.upload_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    part_number: Mapped[int] = mapped_column(Integer, nullable=False)
    etag: Mapped[str] = mapped_column(String(128), default="")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    file_id: Mapped[str] = mapped_column(String(512), default="")
    staging_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class ShareLockoutRow(Base):
    __tablename__ = "share_lockouts"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PendingTgDeleteRow(Base):
    __tablename__ = "pending_tg_deletes"
    __table_args__ = (
        UniqueConstraint("message_id", "chat_id_key", name="uq_pending_tg_msg_chat"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chat_id_key: Mapped[str] = mapped_column(String(64), default="", server_default="")
    reason: Mapped[str] = mapped_column(String(200), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
