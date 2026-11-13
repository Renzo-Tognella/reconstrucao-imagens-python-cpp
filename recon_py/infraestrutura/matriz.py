"""Lê `dados/manifesto.json` e mapeia o arquivo de H na memória, sem copiá-lo."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from recon_py.dominio.modelo import Modelo


def carregar_manifesto(dados: Path) -> dict[str, Modelo]:
    manifesto = json.loads((dados / "manifesto.json").read_text())
    return {
        nome: Modelo(nome, m["linhas"], m["colunas"], m["largura"], m["altura"], dados / m["arquivo"])
        for nome, m in manifesto["modelos"].items()
    }


def mapear_h(modelo: Modelo) -> np.memmap:
    tamanho_esperado = 8 * modelo.linhas * modelo.colunas
    tamanho = modelo.arquivo.stat().st_size
    if tamanho != tamanho_esperado:
        raise ValueError(f"{modelo.arquivo}: {tamanho} bytes; esperado {tamanho_esperado}")
    return np.memmap(modelo.arquivo, dtype="<f8", mode="r", shape=(modelo.linhas, modelo.colunas), order="F")
