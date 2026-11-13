from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

from recon_py.infraestrutura import log_terminal


class RegistroDeEventos:
    def __init__(self, caminho: Path) -> None:
        self.caminho = caminho
        self._arquivo = caminho.open("a", buffering=1)

    def registrar(self, registro: dict, tarefa: dict | None = None) -> None:
        log_terminal.escrever(log_terminal.linha_evento(
            registro["event"], registro["job_id"], tarefa, registro["queue_depth"], registro["running"]))
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
