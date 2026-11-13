from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from recon_py.dominio.modelo import Modelo


class Resultados(Protocol):
    def caminho(self, job_id: str, extensao: str) -> Path: ...

    def gravar(self, job_id: str, extensao: str, conteudo: bytes) -> None: ...


class Eventos(Protocol):
    caminho: Path

    def registrar(self, registro: dict, tarefa: dict | None = None) -> None: ...

    def fechar(self) -> None: ...


@dataclass(frozen=True)
class RecursosExternos:
    abrir_h: Callable[[Modelo], np.ndarray]
    memoria_livre: Callable[[], int]
    memoria_fisica: Callable[[], int]
    resultados: Resultados
    eventos: Eventos
