"""Acrescenta uma linha JSON por evento da fila em `saida/events.jsonl`."""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path


class RegistroDeEventos:
    def __init__(self, caminho: Path) -> None:
        self.caminho = caminho
        self._arquivo = caminho.open("a", buffering=1)

    def registrar(self, registro: dict) -> None:
        # Falha de disco aqui não pode parar a fila: o evento se perde e o erro vai para o stderr.
        try:
            self._arquivo.write(json.dumps(registro) + "\n")
        except OSError as erro:
            evento, job_id = registro["event"], registro["job_id"]
            print(f"falha ao gravar events.jsonl (evento {evento} de {job_id}): {erro}", file=sys.stderr)

    def fechar(self) -> None:
        try:
            self._arquivo.close()
        except OSError:
            traceback.print_exc(file=sys.stderr)
