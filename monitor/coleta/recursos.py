"""CPU e memória do servidor (com filhos) e do sistema, na mesma convenção do coletor do relatório."""
from __future__ import annotations

import time

import psutil

from monitor.medicao.cpu_e_memoria import MB, AcumuladorCpu, ler_cpu_e_memoria


class AmostradorRecursos:
    def __init__(self) -> None:
        self._pid: int | None = None
        self._processo: psutil.Process | None = None
        self._acumulador = AcumuladorCpu()
        psutil.cpu_percent(interval=None)

    def trocar_pid(self, pid: int | None) -> None:
        if pid == self._pid:
            return
        self._pid, self._acumulador = pid, AcumuladorCpu()
        try:
            self._processo = psutil.Process(pid) if pid is not None else None
        except psutil.Error:
            self._processo = None

    def processo_vivo(self) -> bool:
        return self._processo is not None and self._processo.is_running()

    def amostrar(self) -> dict:
        tempos, rss = ler_cpu_e_memoria(self._processo)
        memoria = psutil.virtual_memory()
        return {
            "t": time.time(),
            "cpu_servidor_pct": self._acumulador.percentual(tempos, time.monotonic()),
            "mem_servidor_mb": rss,
            "cpu_sistema_pct": psutil.cpu_percent(interval=None),
            "mem_sistema_pct": memoria.percent,
            "mem_sistema_usada_mb": (memoria.total - memoria.available) / MB,
            "mem_sistema_total_mb": memoria.total / MB,
        }
