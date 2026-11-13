from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Modelo:
    nome: str
    linhas: int
    colunas: int
    largura: int
    altura: int
    arquivo: Path
