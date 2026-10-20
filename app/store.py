"""JSON-file persistence. One lock guards every read-modify-write."""

import json
import os
import threading
from pathlib import Path

from app.models import Release
from app.releases import DomainError


class Store:
    def __init__(self, path: str):
        self.path = Path(path)
        self.lock = threading.RLock()

    def all(self) -> list[Release]:
        with self.lock:
            return list(self._load().values())

    def get(self, release_id: str) -> Release:
        with self.lock:
            release = self._load().get(release_id)
        if release is None:
            raise DomainError("not_found", "Release not found.", 404)
        return release

    def save(self, release: Release) -> None:
        with self.lock:
            releases = self._load()
            releases[release.id] = release
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps([r.model_dump() for r in releases.values()], indent=2))
            os.replace(tmp, self.path)

    def _load(self) -> dict[str, Release]:
        if not self.path.exists():
            return {}
        return {r["id"]: Release.model_validate(r) for r in json.loads(self.path.read_text())}
