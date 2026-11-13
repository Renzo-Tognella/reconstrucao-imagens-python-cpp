"""Hora UTC no formato dos campos `*_at` e de `t_wall`."""
from __future__ import annotations

from datetime import datetime, timezone


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
