from __future__ import annotations

import hashlib
from collections.abc import AsyncIterable
from pathlib import Path
from typing import Any


class LocalFileBinaryStore:
    """Local filesystem implementation for uploaded file binaries."""

    backend_name = "local"

    def __init__(self, root_dir: str | Path) -> None:
        self._root_dir = Path(root_dir)
        self._root_dir.mkdir(parents=True, exist_ok=True)

    async def save(
        self,
        file_id: str,
        filename: str,
        chunks: AsyncIterable[bytes],
        *,
        max_size_bytes: int,
    ) -> dict[str, Any]:
        storage_path = self._root_dir / f"{file_id}_{filename}"
        digest = hashlib.sha256()
        size_bytes = 0

        try:
            with storage_path.open("wb") as file_pointer:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    size_bytes += len(chunk)
                    if size_bytes > max_size_bytes:
                        file_pointer.close()
                        storage_path.unlink(missing_ok=True)
                        raise ValueError("file_too_large")
                    digest.update(chunk)
                    file_pointer.write(chunk)
        except Exception:
            storage_path.unlink(missing_ok=True)
            raise

        return {
            "storage_backend": self.backend_name,
            "storage_path": str(storage_path),
            "size_bytes": size_bytes,
            "sha256": digest.hexdigest(),
        }

    async def exists(self, storage_path: str) -> bool:
        return Path(storage_path).exists()
