from __future__ import annotations

import zlib
from pathlib import Path

import numpy as np

from cliente.carga.ganho import aplicar_ganho
from cliente.comum.registros import ler_json


def ler_manifesto_dados(dados: Path) -> dict:
    return ler_json(dados / "manifesto.json")["modelos"]


def montar_corpo(dados: Path, modelo: dict, sinal: str, ganho: bool) -> bytes:
    valores = np.fromfile(dados / modelo["sinais"][sinal]["arquivo"], dtype="<f8")
    if ganho:
        valores = aplicar_ganho(valores, modelo["S"], modelo["N"])
    return valores.astype("<f8").tobytes()


def corpo_do_pedido(dados: Path, pedido: dict) -> bytes:
    return montar_corpo(dados, ler_manifesto_dados(dados)[pedido["modelo"]], pedido["sinal"], pedido["ganho"])


def crc32_hex(conteudo: bytes) -> str:
    return f"{zlib.crc32(conteudo):08x}"


def crc32_arquivo(caminho: Path) -> str:
    return crc32_hex(caminho.read_bytes())
