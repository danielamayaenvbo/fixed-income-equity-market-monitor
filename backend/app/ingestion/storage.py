from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path


class RawArchive:
    """Stores immutable provider payloads beneath the repository data/raw directory."""

    def __init__(self, root: Path | None = None) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        self.root = root or Path(os.environ.get("RAW_DATA_DIR", repository_root / "data" / "raw"))

    def store(self, source: str, resource: str, payload: bytes, requested_at: datetime) -> tuple[str, str]:
        digest = hashlib.sha256(payload).hexdigest()
        safe_resource = "".join(character if character.isalnum() or character in "-_." else "_" for character in resource)
        timestamp = requested_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination = self.root / source / f"{timestamp}_{safe_resource}_{digest[:12]}.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        try:
            relative_path = destination.relative_to(Path(__file__).resolve().parents[3])
        except ValueError:
            relative_path = destination
        return str(relative_path), digest
