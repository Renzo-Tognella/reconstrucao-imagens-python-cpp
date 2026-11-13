from __future__ import annotations

import numpy as np
import pytest

from recon_py.etapas import operacoes_basicas as op


@pytest.fixture(scope="module")
def dados():
    return op.carregar_dados(op.DADOS_ZIP)


def test_formatos_lidos_do_zip(dados):
    assert dados.a.shape == (10,)
    assert dados.M.shape == (10, 10)
    assert dados.N.shape == (10, 10)
    assert dados.M.flags.f_contiguous
    assert dados.N.flags.f_contiguous


def test_mn_coincide_exatamente_com_gabarito(dados):
    np.testing.assert_array_equal(op.produto_mn(dados.M, dados.N), dados.MN)


def test_am_coincide_com_gabarito_dentro_do_arredondamento(dados):
    meia_unidade = 5e-3
    obtido = op.produto_am(dados.a, dados.M)
    np.testing.assert_allclose(obtido, dados.aM, rtol=0, atol=meia_unidade)


def test_ma_difere_de_am_porque_m_nao_e_simetrica(dados):
    assert not np.allclose(op.produto_ma(dados.M, dados.a), dados.aM, atol=1.0)


def test_ma_coincide_com_numpy_puro(dados):
    esperado = np.array([np.sum(linha * dados.a) for linha in dados.M])
    np.testing.assert_allclose(op.produto_ma(dados.M, dados.a), esperado, rtol=1e-13)


def test_produtos_nao_alteram_operandos(dados):
    copias = dados.a.copy(), dados.M.copy(), dados.N.copy()
    op.produto_mn(dados.M, dados.N)
    op.produto_am(dados.a, dados.M)
    op.produto_ma(dados.M, dados.a)
    for original, copia in zip((dados.a, dados.M, dados.N), copias):
        np.testing.assert_array_equal(original, copia)


@pytest.mark.parametrize("tamanho", [9, 11])
def test_vetor_de_tamanho_errado_e_recusado(dados, tamanho):
    vetor = np.ones(tamanho)
    with pytest.raises(ValueError):
        op.produto_ma(dados.M, vetor)
    with pytest.raises(ValueError):
        op.produto_am(vetor, dados.M)


def test_matrizes_incompativeis_sao_recusadas():
    with pytest.raises(ValueError):
        op.produto_mn(np.ones((2, 3), order="F"), np.ones((2, 3), order="F"))
