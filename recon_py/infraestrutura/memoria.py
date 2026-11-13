"""Quanto de RAM o sistema operacional informa: livre agora e total da máquina."""
from __future__ import annotations

import psutil


def memoria_disponivel() -> int:
    return psutil.virtual_memory().available


def memoria_fisica_total() -> int:
    return psutil.virtual_memory().total
