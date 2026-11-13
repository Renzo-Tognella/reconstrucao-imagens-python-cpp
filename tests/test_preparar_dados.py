from __future__ import annotations

import zipfile

import numpy as np
import pytest

from preparar_dados import converter_matriz


def _zip_csv(pasta, matriz):
    csv = pasta / "H.csv"
    np.savetxt(csv, matriz, delimiter=",", fmt="%.17g")
    arquivo = pasta / "H.csv.zip"
    with zipfile.ZipFile(arquivo, "w") as z:
        z.write(csv, "H.csv")
    return arquivo


def test_converte_por_colunas_lendo_em_fluxo(tmp_path):
    matriz = np.arange(12, dtype=np.float64).reshape(4, 3) / 7
    destino = tmp_path / "H.f64"
    converter_matriz(_zip_csv(tmp_path, matriz), destino, 4, 3)
    assert destino.read_bytes() == matriz.astype("<f8").tobytes(order="F")


def test_ignora_metadados_do_macos_no_zip(tmp_path):
    matriz = np.ones((2, 2))
    arquivo = _zip_csv(tmp_path, matriz)
    with zipfile.ZipFile(arquivo) as z:
        conteudo = z.read("H.csv")
    with zipfile.ZipFile(arquivo, "w") as z:
        z.writestr("__MACOSX/._H.csv", b"binario")
        z.writestr("H.csv", conteudo)
    destino = tmp_path / "H.f64"
    converter_matriz(arquivo, destino, 2, 2)
    assert destino.read_bytes() == matriz.astype("<f8").tobytes(order="F")


@pytest.mark.parametrize("linhas,colunas", [(5, 3), (3, 3), (4, 2)])
def test_dimensoes_inesperadas_sao_erro_sem_deixar_arquivo(tmp_path, linhas, colunas):
    matriz = np.ones((4, 3))
    destino = tmp_path / "H.f64"
    with pytest.raises(ValueError):
        converter_matriz(_zip_csv(tmp_path, matriz), destino, linhas, colunas)
    assert not destino.exists()
