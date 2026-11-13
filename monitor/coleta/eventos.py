"""Leitura incremental de events.jsonl, como `tail -f`."""
from __future__ import annotations

import json
import os
from pathlib import Path


class LeitorEventos:
    """Guarda a posição já lida. Uma linha sem `\\n` no fim ainda está sendo escrita: fica para a próxima leitura."""

    def __init__(self, caminho: Path) -> None:
        self.caminho = caminho
        self.linhas_invalidas = 0
        self._posicao = 0
        self._resto = b""
        self._inode: int | None = None

    def ler_novos(self) -> list[dict]:
        try:
            info = os.stat(self.caminho)
        except FileNotFoundError:
            return []
        if info.st_ino != self._inode or info.st_size < self._posicao:
            # Arquivo novo ou truncado: o que foi lido antes não vale mais.
            self._inode, self._posicao, self._resto = info.st_ino, 0, b""
        if info.st_size == self._posicao:
            return []
        with open(self.caminho, "rb") as arquivo:
            arquivo.seek(self._posicao)
            bloco = arquivo.read(info.st_size - self._posicao)
        self._posicao += len(bloco)
        *completas, self._resto = (self._resto + bloco).split(b"\n")
        return [registro for linha in completas if (registro := self._decodificar(linha)) is not None]

    def _decodificar(self, linha: bytes) -> dict | None:
        if not linha.strip():
            return None
        try:
            registro = json.loads(linha)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.linhas_invalidas += 1
            return None
        return registro if isinstance(registro, dict) else None
