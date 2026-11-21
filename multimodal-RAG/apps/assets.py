"""Asset storage. Local now; swap the implementation for S3 later."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .config import settings


class LocalStorage:
    """Stores extracted visuals under assets/{document_id}/."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or settings.asset_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def doc_dir(self, document_id: str) -> Path:
        d = self.root / document_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_png(self, document_id: str, name: str, data: bytes) -> tuple[str, str]:
        path = self.doc_dir(document_id) / name
        path.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        return str(Path(document_id) / name), digest

    def resolve(self, rel_path: str) -> Path:
        return self.root / rel_path

    def exists(self, rel_path: str | None) -> bool:
        return bool(rel_path) and self.resolve(rel_path).exists()

    def delete_doc(self, document_id: str) -> None:
        d = self.root / document_id
        if d.exists():
            shutil.rmtree(d)


storage = LocalStorage()
