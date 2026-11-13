"""Pedido recebido, tarefa na fila e os estados e erros que ela pode ter."""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from recon_py.aplicacao.relogio import agora_iso

NUMERICAL_FAILURE = "numerical_failure"
INSUFFICIENT_MEMORY = "insufficient_memory"
OUTPUT_WRITE_FAILED = "output_write_failed"
INTERNAL_ERROR = "internal_error"
TERMINAIS = ("done", "failed")


@dataclass(frozen=True)
class Pedido:
    job_id: str
    client_id: str
    signal_id: str
    model: str
    algorithm: str
    gain: bool
    sinal: np.ndarray
    crc: int

    def identidade(self) -> tuple:
        return self.client_id, self.signal_id, self.model, self.algorithm, self.gain, self.crc


class Tarefa:
    def __init__(self, pedido: Pedido) -> None:
        self.job_id = pedido.job_id
        self.identidade = pedido.identidade()
        self.sinal: np.ndarray | None = pedido.sinal
        self.tamanho_bytes = pedido.sinal.nbytes
        self.recebida_mono = time.monotonic()
        self.custo = 0
        self.corpo = {
            "job_id": pedido.job_id,
            "client_id": pedido.client_id,
            "signal_id": pedido.signal_id,
            "model": pedido.model,
            "algorithm": pedido.algorithm,
            "gain": pedido.gain,
            "status": "queued",
            "received_at": agora_iso(),
            "started_at": None,
            "finished_at": None,
            "queue_wait_s": None,
            "duration_s": None,
            "iterations": None,
            "stop_reason": None,
            "residual_norms": None,
            "error": None,
        }
