from __future__ import annotations

from datetime import datetime, timezone

import pytest

from monitor.estado import montar_estado

BASE = 1_800_000_000.0
MONO = 5_000.0


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def ev(evento, job, t, fila, rodando):
    return {"t_wall": _iso(BASE + t), "t_mono": MONO + t, "event": evento, "job_id": job,
            "queue_depth": fila, "running": rodando}


def meta(job, cliente, status, espera=None, duracao=None, iteracoes=None, erro=None):
    return {"job_id": job, "client_id": cliente, "signal_id": "g1", "model": "30x30", "algorithm": "cgnr",
            "gain": True, "status": status, "queue_wait_s": espera, "duration_s": duracao,
            "iterations": iteracoes, "stop_reason": "tolerance" if status == "done" else None, "error": erro}


EVENTOS = [
    ev("accepted", "A", 0.0, 1, 0),
    ev("started", "A", 0.1, 0, 1),
    ev("accepted", "B", 0.5, 1, 1),
    ev("accepted", "C", 0.6, 2, 1),
    ev("rejected", "D", 0.7, 2, 1),
    ev("finished", "A", 2.1, 2, 0),
    ev("started", "B", 2.1, 1, 1),
    ev("finished", "B", 4.1, 1, 0),
    ev("started", "C", 4.1, 0, 1),
    ev("failed", "C", 5.0, 0, 0),
]
METADADOS = {
    "A": meta("A", "c1", "done", 0.1, 2.0, 3),
    "B": meta("B", "c2", "done", 1.6, 2.0, 2),
    "C": meta("C", "c3", "failed", 3.5, None, None, "numerical_failure"),
}


def _pedido(estado, job):
    return next(p for p in estado["pedidos"] if p["job_id"] == job)


def test_contagens_da_rodada():
    estado = montar_estado(EVENTOS, METADADOS, [], agora_wall=BASE + 6)
    cartoes = estado["cartoes"]
    assert (cartoes["aceitas"], cartoes["concluidas"], cartoes["falhas"], cartoes["recusadas"]) == (3, 2, 1, 1)
    assert cartoes["pendentes"] == 0


def test_tempo_total_vai_da_primeira_chegada_a_ultima_conclusao():
    cartoes = montar_estado(EVENTOS, METADADOS, [], agora_wall=BASE + 60)["cartoes"]
    assert cartoes["tempo_total_s"] == pytest.approx(5.0)
    assert cartoes["em_andamento"] is False
    assert cartoes["imagens_por_s"] == pytest.approx(2 / 5.0)
    assert cartoes["reconstrucao_media_s"] == pytest.approx(2.0)


def test_latencias_por_pedido_usam_o_json_da_tarefa():
    estado = montar_estado(EVENTOS, METADADOS, [], agora_wall=BASE + 6)
    a = _pedido(estado, "A")
    assert a["client_id"] == "c1" and a["estado"] == "concluido" and a["iteracoes"] == 3
    assert a["espera_s"] == pytest.approx(0.1)
    assert a["reconstrucao_s"] == pytest.approx(2.0)
    assert a["total_s"] == pytest.approx(2.1)
    assert (a["t_recebido"], a["t_inicio"], a["t_fim"]) == pytest.approx((0.0, 0.1, 2.1))
    c = _pedido(estado, "C")
    assert c["estado"] == "falhou" and c["erro"] == "numerical_failure"
    assert c["total_s"] == pytest.approx(4.4)


def test_recusado_aparece_sem_cliente_conhecido():
    d = _pedido(montar_estado(EVENTOS, METADADOS, [], agora_wall=BASE + 6), "D")
    assert d["estado"] == "recusado" and d["client_id"] is None
    assert d["t_recebido"] == pytest.approx(0.7)


def test_uma_faixa_por_cliente_em_ordem_e_recusados_a_parte():
    faixas = montar_estado(EVENTOS, METADADOS, [], agora_wall=BASE + 6)["faixas"]
    assert [f["cliente"] for f in faixas] == ["c1", "c2", "c3", None]
    assert [f["job_ids"] for f in faixas] == [["A"], ["B"], ["C"], ["D"]]


def test_pedido_em_andamento_mede_ate_agora():
    eventos = [ev("accepted", "A", 0.0, 1, 0), ev("started", "A", 0.2, 0, 1), ev("accepted", "B", 0.3, 1, 1)]
    estado = montar_estado(eventos, {"A": meta("A", "c1", "running")}, [], agora_wall=BASE + 1.5)
    a, b = _pedido(estado, "A"), _pedido(estado, "B")
    assert a["estado"] == "reconstruindo"
    assert a["espera_s"] == pytest.approx(0.2)
    assert a["reconstrucao_s"] == pytest.approx(1.3)
    assert a["t_fim"] is None
    assert b["estado"] == "fila" and b["client_id"] is None
    assert b["espera_s"] == pytest.approx(1.2)
    cartoes = estado["cartoes"]
    assert cartoes["em_andamento"] is True
    assert cartoes["tempo_total_s"] == pytest.approx(1.5)
    assert cartoes["pendentes"] == 2


def test_fila_media_temporal_e_moda_seguem_os_indicadores_do_cliente():
    amostras = [(BASE - 1, 9), (BASE + 0.5, 1), (BASE + 1.5, 2), (BASE + 2.5, 2), (BASE + 3.5, 1), (BASE + 4.5, 2), (BASE + 99, 5)]
    cartoes = montar_estado(EVENTOS, METADADOS, amostras, agora_wall=BASE + 120)["cartoes"]
    assert cartoes["fila_media"] == pytest.approx(5.2 / 5.0)
    assert cartoes["fila_moda"] == [2]
    assert cartoes["fila_amostras"] == 5


def test_tabela_traz_os_mais_recentes_primeiro():
    tabela = montar_estado(EVENTOS, METADADOS, [], agora_wall=BASE + 6, limite_tabela=2)["tabela"]
    assert tabela == ["D", "C"]


def test_eventos_de_tarefas_aceitas_antes_da_rodada_sao_ignorados():
    eventos = [ev("started", "velho", 0.0, 0, 1), ev("finished", "velho", 1.0, 0, 0), ev("accepted", "A", 1.5, 1, 0)]
    estado = montar_estado(eventos, {}, [], agora_wall=BASE + 2)
    assert [p["job_id"] for p in estado["pedidos"]] == ["A"]
    assert estado["cartoes"]["concluidas"] == 0


def test_sem_eventos_nao_inventa_numeros():
    cartoes = montar_estado([], {}, [], agora_wall=BASE)["cartoes"]
    assert cartoes["tempo_total_s"] is None
    assert cartoes["imagens_por_s"] is None
    assert cartoes["fila_media"] is None
    assert cartoes["fila_moda"] == []
