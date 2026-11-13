"""Implementação de referência só com NumPy puro, usada para conferir os dois servidores."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

DADOS = Path(__file__).resolve().parents[1] / "dados"
TOL = 1e-4


def manifesto() -> dict:
    return json.loads((DADOS / "manifesto.json").read_text())


def carregar_modelo(nome: str = "30x30") -> tuple[dict, np.ndarray]:
    modelo = manifesto()["modelos"][nome]
    forma = (modelo["linhas"], modelo["colunas"])
    return modelo, np.memmap(DADOS / modelo["arquivo"], dtype="<f8", mode="r", shape=forma, order="F")


def carregar_sinal(id_sinal: str, nome: str = "30x30") -> np.ndarray:
    return np.fromfile(DADOS / "sinais" / nome / f"{id_sinal}.f64", dtype="<f8")


def cgnr(H, g, max_iter=10):
    f = np.zeros(H.shape[1])
    r = g.copy()
    normas = [np.linalg.norm(r)]
    z = H.T @ r
    p = z.copy()
    zz = z @ z
    if zz == 0:
        return f, normas, 0, "zero_residual"
    for i in range(1, max_iter + 1):
        w = H @ p
        alpha = zz / (w @ w)
        f += alpha * p
        r -= alpha * w
        normas.append(np.linalg.norm(r))
        if abs(normas[-1] - normas[-2]) < TOL:
            return f, normas, i, "tolerance"
        z = H.T @ r
        novo = z @ z
        if novo == 0:
            return f, normas, i, "zero_residual"
        p = z + (novo / zz) * p
        zz = novo
    return f, normas, max_iter, "max_iterations"


def cgne(H, g, max_iter=10):
    f = np.zeros(H.shape[1])
    r = g.copy()
    normas = [np.linalg.norm(r)]
    rr = r @ r
    if rr == 0:
        return f, normas, 0, "zero_residual"
    p = H.T @ r
    for i in range(1, max_iter + 1):
        alpha = rr / (p @ p)
        f += alpha * p
        r -= alpha * (H @ p)
        normas.append(np.linalg.norm(r))
        if abs(normas[-1] - normas[-2]) < TOL:
            return f, normas, i, "tolerance"
        novo = r @ r
        if novo == 0:
            return f, normas, i, "zero_residual"
        p = H.T @ r + (novo / rr) * p
        rr = novo
    return f, normas, max_iter, "max_iterations"


def ganho(g: np.ndarray, S: int, N: int) -> np.ndarray:
    amostras = np.arange(1, S + 1, dtype=np.float64)
    return g * np.tile(100 + amostras * np.sqrt(amostras) / 20, N)


def pgm(f: np.ndarray, largura: int, altura: int) -> bytes:
    absoluto = np.abs(f)
    maximo = absoluto.max()
    pixels = np.zeros_like(absoluto) if maximo == 0 else np.floor(absoluto / maximo * 255 + 0.5)
    imagem = pixels.astype(np.uint8).reshape((altura, largura), order="F")
    return f"P5\n{largura} {altura}\n255\n".encode() + imagem.tobytes()
