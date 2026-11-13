from __future__ import annotations

import time


class Contadores:
    def __init__(self) -> None:
        self._contagem = {"accepted": 0, "completed": 0, "failed": 0, "rejected": 0}
        self._inicio_mono = time.monotonic()

    def somar(self, nome: str) -> None:
        self._contagem[nome] += 1

    def resumo(self, profundidade_da_fila: int, em_execucao: int, aguardando_memoria: bool) -> dict:
        return {
            "queue_depth": profundidade_da_fila,
            "running": em_execucao,
            **self._contagem,
            "waiting_memory": aguardando_memoria,
            "uptime_s": time.monotonic() - self._inicio_mono,
        }
