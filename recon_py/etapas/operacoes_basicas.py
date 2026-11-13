from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.linalg.blas import dgemm, dgemv

DADOS_ZIP = Path(__file__).resolve().parents[2] / "dados-fornecidos" / "Dados.zip"


@dataclass(frozen=True)
class DadosEtapa2:
    a: np.ndarray
    M: np.ndarray
    N: np.ndarray
    MN: np.ndarray
    aM: np.ndarray


def _ler_csv(arquivo: zipfile.ZipFile, nome: str) -> np.ndarray:
    return np.loadtxt(io.BytesIO(arquivo.read(nome)), delimiter=";", ndmin=2)


def carregar_dados(caminho_zip: Path) -> DadosEtapa2:
    with zipfile.ZipFile(caminho_zip) as arquivo:
        return DadosEtapa2(
            a=_ler_csv(arquivo, "a.csv").ravel(),
            M=np.asfortranarray(_ler_csv(arquivo, "M.csv")),
            N=np.asfortranarray(_ler_csv(arquivo, "N.csv")),
            MN=_ler_csv(arquivo, "MN.csv"),
            aM=_ler_csv(arquivo, "aM.csv").ravel(),
        )


def _exigir_compativeis(tamanho_a: int, tamanho_b: int) -> None:
    if tamanho_a != tamanho_b:
        raise ValueError(f"dimensões incompatíveis: {tamanho_a} e {tamanho_b}")


def produto_mn(M: np.ndarray, N: np.ndarray) -> np.ndarray:
    _exigir_compativeis(M.shape[1], N.shape[0])
    return dgemm(1.0, M, N)


def produto_am(a: np.ndarray, M: np.ndarray) -> np.ndarray:
    _exigir_compativeis(a.size, M.shape[0])
    return dgemv(1.0, M, a, trans=1)


def produto_ma(M: np.ndarray, a: np.ndarray) -> np.ndarray:
    _exigir_compativeis(M.shape[1], a.size)
    return dgemv(1.0, M, a)
