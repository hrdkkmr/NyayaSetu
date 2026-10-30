"""Object storage for uploaded files, encrypted at the application layer.

Files are encrypted with AES-256-GCM before they reach disk or S3, so a leaked
bucket or disk does not expose citizens' documents. Storage keys are random and
never derived from user input; the API never exposes keys or raw storage URLs.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import secrets
from pathlib import Path
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

_MAGIC = b"NSE1"


def _key() -> bytes:
    s = get_settings()
    if s.storage_encryption_key:
        key = base64.b64decode(s.storage_encryption_key)
        if len(key) != 32:
            raise ValueError("STORAGE_ENCRYPTION_KEY must be 32 bytes, base64-encoded")
        return key
    return hashlib.sha256(f"{s.secret_key}:storage".encode()).digest()


def encrypt(data: bytes) -> bytes:
    nonce = os.urandom(12)
    return _MAGIC + nonce + AESGCM(_key()).encrypt(nonce, data, _MAGIC)


def decrypt(blob: bytes) -> bytes:
    if not blob.startswith(_MAGIC):
        raise ValueError("Unrecognised storage format")
    nonce, ciphertext = blob[4:16], blob[16:]
    return AESGCM(_key()).decrypt(nonce, ciphertext, _MAGIC)


class StorageBackend(Protocol):
    name: str

    async def put(self, key: str, data: bytes) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    async def health(self) -> tuple[bool, str]: ...


class LocalStorage:
    name = "local"

    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("Invalid storage key")
        return path

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            await asyncio.to_thread(path.unlink)

    async def health(self) -> tuple[bool, str]:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / ".health"
            probe.write_bytes(b"ok")
            probe.unlink()
            return True, "writable"
        except OSError as exc:
            return False, f"not writable: {exc.strerror}"


class S3Storage:
    name = "s3"

    def __init__(self) -> None:
        import boto3

        s = get_settings()
        self.bucket = s.s3_bucket
        self.client = boto3.client(
            "s3", endpoint_url=s.s3_endpoint_url, region_name=s.s3_region,
            aws_access_key_id=s.s3_access_key_id, aws_secret_access_key=s.s3_secret_access_key,
        )

    async def put(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(self.client.put_object, Bucket=self.bucket, Key=key, Body=data,
                                ServerSideEncryption="AES256")

    async def get(self, key: str) -> bytes:
        obj = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
        return await asyncio.to_thread(obj["Body"].read)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)

    async def health(self) -> tuple[bool, str]:
        try:
            await asyncio.to_thread(self.client.head_bucket, Bucket=self.bucket)
            return True, "bucket reachable"
        except Exception as exc:  # noqa: BLE001
            return False, f"bucket check failed: {type(exc).__name__}"


_backend: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _backend
    if _backend is None:
        s = get_settings()
        _backend = S3Storage() if s.storage_backend == "s3" and s.s3_bucket else LocalStorage(s.local_storage_path)
    return _backend


def new_storage_key(prefix: str) -> str:
    return f"{prefix}/{secrets.token_hex(2)}/{secrets.token_urlsafe(24)}"


async def store_encrypted(prefix: str, data: bytes) -> str:
    key = new_storage_key(prefix)
    await get_storage().put(key, encrypt(data))
    return key


async def load_decrypted(key: str) -> bytes:
    return decrypt(await get_storage().get(key))


async def purge_voice_audio(db: object, user_id: object) -> int:
    """Delete every stored voice recording of a user (consent withdrawal or account deletion)."""
    from sqlalchemy import select

    from app.models import VoiceSession

    removed = 0
    sessions = (await db.scalars(select(VoiceSession).where(VoiceSession.user_id == user_id))).all()  # type: ignore[attr-defined]
    for vs in sessions:
        keys = (vs.stats or {}).get("audio_keys", [])
        for key in keys:
            await get_storage().delete(key)
            removed += 1
        if keys:
            vs.stats = {k: v for k, v in (vs.stats or {}).items() if k != "audio_keys"}
            vs.audio_stored = False
    return removed
