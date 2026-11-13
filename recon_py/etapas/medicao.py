from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

from recon_py.dominio.algoritmos.catalogo import ALGORITMOS
from recon_py.dominio.algoritmos.resultado import Resultado
from recon_py.dominio.imagem import pgm
from recon_py.dominio.modelo import Modelo
from recon_py.infraestrutura.matriz import carregar_manifesto, mapear_h

BYTES_POR_MIB = 1024 * 1024
BYTES_POR_UNIDADE_RSS = 1 if sys.platform == "darwin" else 1024


def _pico_rss_e_cpu() -> tuple[float, float]:
    uso = resource.getrusage(resource.RUSAGE_SELF)
    return uso.ru_maxrss * BYTES_POR_UNIDADE_RSS / BYTES_POR_MIB, uso.ru_utime + uso.ru_stime


def carregar_sinal(caminho: Path, modelo: Modelo) -> np.ndarray:
    sinal = np.fromfile(caminho, dtype="<f8")
    if sinal.size != modelo.linhas:
        raise ValueError(f"sinal com {sinal.size} amostras; o modelo {modelo.nome} exige {modelo.linhas}")
    if not np.isfinite(sinal).all():
        raise ValueError("sinal com NaN ou infinito")
    return sinal


def _medir(H: np.ndarray, sinal: np.ndarray, algoritmo: str, carga_h_s: float) -> tuple[Resultado, dict]:
    _, cpu_antes = _pico_rss_e_cpu()
    inicio = time.perf_counter()
    resultado = ALGORITMOS[algoritmo](H, sinal)
    duracao = time.perf_counter() - inicio
    pico_rss, cpu_depois = _pico_rss_e_cpu()
    return resultado, {
        "iterations": resultado.iterations,
        "stop_reason": resultado.stop_reason,
        "residual_norms": resultado.residual_norms,
        "duration_s": duracao,
        "rss_mb": pico_rss,
        "cpu_s": cpu_depois - cpu_antes,
        "carga_h_s": carga_h_s,
    }


def executar(dados: Path, nome_modelo: str, caminho_sinal: Path, algoritmo: str, repeticoes: int, saida: Path | None) -> None:
    modelos = carregar_manifesto(dados)
    if nome_modelo not in modelos:
        raise ValueError(f"modelo desconhecido: {nome_modelo}")
    modelo = modelos[nome_modelo]
    sinal = carregar_sinal(caminho_sinal, modelo)
    inicio_carga = time.perf_counter()
    H = mapear_h(modelo)
    carga_h_s = time.perf_counter() - inicio_carga
    for _ in range(repeticoes):
        resultado, medicao = _medir(H, sinal, algoritmo, carga_h_s)
        print(json.dumps(medicao), flush=True)
    if saida is not None:
        saida.write_bytes(pgm(resultado.f, modelo.largura, modelo.altura))
