"""Disk cache for expensive steps (Docling conversions, later LLM responses), keyed by content hashes."""

import hashlib
from pathlib import Path


class DiskCache:
    """Text values stored as `<directory>/<key>.json`."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    @staticmethod
    def key(*parts: str | bytes) -> str:
        """Hash of all parts; each part is hashed separately so part boundaries cannot collide."""
        digest = hashlib.sha256()
        for part in parts:
            digest.update(hashlib.sha256(part.encode("utf-8") if isinstance(part, str) else part).digest())
        return digest.hexdigest()

    def get(self, key: str) -> str | None:
        path = self._path(key)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def put(self, key: str, value: str) -> None:
        """Write atomically, so an interrupted run never leaves a half-written entry."""
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(value, encoding="utf-8")
        temporary.replace(path)

    def _path(self, key: str) -> Path:
        return self._directory / f"{key}.json"
