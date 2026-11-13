from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from recon_py.dominio.modelo import Modelo
from recon_py.infraestrutura.matriz import carregar_manifesto, mapear_h

DADOS = Path(__file__).resolve().parents[3] / "dados"


def test_manifesto_descreve_o_modelo_30x30():
    modelo = carregar_manifesto(DADOS)["30x30"]
    assert (modelo.linhas, modelo.colunas, modelo.largura, modelo.altura) == (27904, 900, 30, 30)
    assert modelo.arquivo == DADOS / "modelos/30x30/H.f64"


def test_h_mapeada_atende_ao_wrapper_sem_copia():
    H = mapear_h(carregar_manifesto(DADOS)["30x30"])
    assert isinstance(H, np.memmap)
    assert H.shape == (27904, 900)
    assert H.flags.f_contiguous
    assert H.dtype == np.float64
    assert not H.flags.writeable


def test_arquivo_de_tamanho_errado_e_recusado(tmp_path):
    arquivo = tmp_path / "H.f64"
    np.zeros(5).tofile(arquivo)
    with pytest.raises(ValueError):
        mapear_h(Modelo("m", linhas=2, colunas=3, largura=3, altura=1, arquivo=arquivo))
