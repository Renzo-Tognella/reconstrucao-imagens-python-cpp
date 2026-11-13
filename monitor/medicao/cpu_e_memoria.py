from __future__ import annotations

import psutil

MB = 1024 * 1024


class AcumuladorCpu:
    def __init__(self) -> None:
        self.tempos: dict[tuple[int, float], float] = {}
        self.instante: float | None = None

    def percentual(self, tempos: dict[tuple[int, float], float], agora: float) -> float | None:
        anterior, instante_anterior = self.tempos, self.instante
        self.tempos, self.instante = tempos, agora
        if instante_anterior is None or agora <= instante_anterior or not tempos:
            return None
        variacao = sum(max(0.0, valor - anterior.get(chave, 0.0)) for chave, valor in tempos.items())
        return 100.0 * variacao / (agora - instante_anterior)


def ler_cpu_e_memoria(processo: psutil.Process | None) -> tuple[dict[tuple[int, float], float], float | None]:
    if processo is None:
        return {}, None
    try:
        familia = [processo, *processo.children(recursive=True)]
    except psutil.Error:
        return {}, None
    tempos: dict[tuple[int, float], float] = {}
    rss = 0
    for membro in familia:
        try:
            with membro.oneshot():
                cpu = membro.cpu_times()
                chave = (membro.pid, membro.create_time())
                rss += membro.memory_info().rss
            tempos[chave] = cpu.user + cpu.system
        except psutil.Error:
            continue
    return tempos, (rss / MB if tempos else None)
