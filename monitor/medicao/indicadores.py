"""Janela de tempo, fila média ponderada pelo tempo e moda, a partir dos eventos do servidor."""
from __future__ import annotations

from collections import Counter

EVENTOS_CHEGADA = {"accepted", "rejected"}
EVENTOS_CONCLUSAO = {"finished", "failed"}


def _ordenar(eventos: list[dict]) -> list[dict]:
    return sorted(eventos, key=lambda e: e["t_mono"])


def janela_mono(eventos: list[dict]) -> tuple[float, float] | None:
    """Da primeira chegada à última conclusão; sem conclusão, até o último evento."""
    if not eventos:
        return None
    ordenados = _ordenar(eventos)
    chegadas = [e["t_mono"] for e in ordenados if e["event"] in EVENTOS_CHEGADA]
    conclusoes = [e["t_mono"] for e in ordenados if e["event"] in EVENTOS_CONCLUSAO]
    inicio = chegadas[0] if chegadas else ordenados[0]["t_mono"]
    fim = conclusoes[-1] if conclusoes else ordenados[-1]["t_mono"]
    return inicio, fim


def fila_media_temporal(eventos: list[dict]) -> float | None:
    """∫ fila(t) dt / T, com fila(t) em degraus: cada evento informa o tamanho logo após ele."""
    janela = janela_mono(eventos)
    if janela is None or janela[1] <= janela[0]:
        return None
    inicio, fim = janela
    no_intervalo = [e for e in _ordenar(eventos) if inicio <= e["t_mono"] <= fim]
    area = 0.0
    for atual, proximo in zip(no_intervalo, no_intervalo[1:]):
        area += atual["queue_depth"] * (proximo["t_mono"] - atual["t_mono"])
    return area / (fim - inicio)


def moda(valores: list[int]) -> list[int]:
    contagem = Counter(valores)
    if not contagem:
        return []
    maior = max(contagem.values())
    return sorted(v for v, n in contagem.items() if n == maior)
