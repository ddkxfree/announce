from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def fingerprint(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def fingerprint_dir(root: Path) -> str:
    """Hash of every file path and content under ``root``."""
    h = hashlib.sha256()
    root = Path(root)
    for file in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(file.relative_to(root).as_posix().encode())
        h.update(b"\0")
        h.update(file.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:16]
