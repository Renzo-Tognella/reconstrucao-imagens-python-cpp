import numpy as np
import pytest

from cliente.carga.ganho import aplicar_ganho, fatores_ganho


def formula_em_laco(g, S, N):
    saida = np.array(g, dtype=float)
    for c in range(N):
        for l in range(1, S + 1):
            saida[c * S + (l - 1)] *= 100 + (1 / 20) * l * l ** 0.5
    return saida


def test_ganho_coincide_com_a_formula_em_laco():
    S, N = 7, 5
    g = np.random.default_rng(1).normal(size=S * N)
    np.testing.assert_allclose(aplicar_ganho(g, S, N), formula_em_laco(g, S, N), rtol=1e-15)


def test_fatores_nos_extremos_da_amostra():
    fatores = fatores_ganho(436)
    assert fatores[0] == pytest.approx(100.05)
    assert fatores[-1] == pytest.approx(100 + 436 * 436 ** 0.5 / 20)


def test_cada_sensor_reinicia_a_contagem_de_amostras():
    S, N = 4, 3
    saida = aplicar_ganho(np.ones(S * N), S, N)
    np.testing.assert_array_equal(saida[:S], saida[S:2 * S])
    np.testing.assert_array_equal(saida[:S], saida[2 * S:])
    assert saida[0] < saida[S - 1]


def test_nao_altera_o_sinal_de_entrada():
    g = np.ones(6)
    aplicar_ganho(g, 3, 2)
    np.testing.assert_array_equal(g, np.ones(6))


def test_tamanho_incompativel_e_erro():
    with pytest.raises(ValueError, match="12"):
        aplicar_ganho(np.ones(11), 4, 3)
