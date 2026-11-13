from __future__ import annotations

import numpy as np

from recon_py.dominio import imagem


def test_pgm_com_vetor_nulo_e_todo_zero():
    conteudo = imagem.pgm(np.zeros(6), largura=3, altura=2)
    assert conteudo == b"P5\n3 2\n255\n" + bytes(6)


def test_pgm_usa_valor_absoluto_e_ordem_por_colunas():
    # f[col*altura + lin]: a primeira coluna é (0, -255) e a saída sai linha a linha.
    conteudo = imagem.pgm(np.array([0.0, -255.0, 255.0, 127.5, 51.0, 102.0]), largura=3, altura=2)
    assert conteudo == b"P5\n3 2\n255\n" + bytes([0, 255, 51, 255, 128, 102])


def test_pgm_nao_altera_o_vetor():
    f = np.array([-1.0, 2.0])
    imagem.pgm(f, largura=1, altura=2)
    np.testing.assert_array_equal(f, [-1.0, 2.0])
