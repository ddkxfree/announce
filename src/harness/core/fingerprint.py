from __future__ import annotations

import hashlib
import json
from typing import Any


def fingerprint(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]
