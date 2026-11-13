import pytest

from cliente.comum.registros import instante_epoch, ler_jsonl
from monitor.medicao.indicadores import fila_media_temporal, moda
from tests.cliente.apoio import evento


def test_media_temporal_pondera_pelo_tempo_entre_eventos():
    eventos = [
        evento(0, "accepted", "a", 1), evento(2, "accepted", "b", 2), evento(3, "started", "a", 1, 1),
        evento(7, "finished", "a", 1), evento(7, "started", "b", 0, 1), evento(8, "finished", "b", 0),
    ]
    assert fila_media_temporal(eventos) == pytest.approx((2 * 1 + 1 * 2 + 4 * 1 + 1 * 0) / 8)


def test_media_temporal_difere_da_media_das_linhas():
    eventos = [evento(0, "accepted", "a", 5), evento(9, "started", "a", 0, 1), evento(10, "finished", "a", 0)]
    assert fila_media_temporal(eventos) == pytest.approx(4.5)


def test_eventos_fora_de_ordem_sao_ordenados_pelo_relogio_monotonico():
    eventos = [evento(10, "finished", "a", 0), evento(0, "accepted", "a", 5), evento(9, "started", "a", 0, 1)]
    assert fila_media_temporal(eventos) == pytest.approx(4.5)


def test_rejeicao_depois_da_ultima_conclusao_nao_estende_a_janela():
    eventos = [evento(0, "accepted", "a", 2), evento(4, "finished", "a", 0), evento(100, "rejected", "z", 0)]
    assert fila_media_temporal(eventos) == pytest.approx(2.0)


def test_media_temporal_sem_conclusao_usa_o_ultimo_evento():
    eventos = [evento(0, "accepted", "a", 1), evento(2, "rejected", "b", 1)]
    assert fila_media_temporal(eventos) == pytest.approx(1.0)


def test_media_temporal_sem_duracao_nao_tem_valor():
    assert fila_media_temporal([]) is None
    assert fila_media_temporal([evento(0, "accepted", "a", 1)]) is None


def test_moda_devolve_todos_os_empatados_em_ordem():
    assert moda([2, 2, 3, 3, 1]) == [2, 3]
    assert moda([0, 0, 1]) == [0]
    assert moda([]) == []


@pytest.mark.parametrize("valor,esperado", [
    (1000.5, 1000.5),
    ("1970-01-01T00:16:40.500Z", 1000.5),
    ("1970-01-01T00:16:40.500+00:00", 1000.5),
])
def test_instante_aceita_epoch_e_iso(valor, esperado):
    assert instante_epoch(valor) == pytest.approx(esperado)


def test_jsonl_ignora_so_a_ultima_linha_truncada(tmp_path):
    caminho = tmp_path / "x.jsonl"
    caminho.write_text('{"a": 1}\n{"a":')
    linhas, truncado = ler_jsonl(caminho)
    assert linhas == [{"a": 1}] and truncado
    caminho.write_text('{"a":\n{"a": 1}\n')
    with pytest.raises(ValueError):
        ler_jsonl(caminho)

