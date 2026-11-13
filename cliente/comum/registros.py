"""Leitura dos arquivos gravados numa execução: JSON e JSONL."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def ler_json(caminho: Path):
    return json.loads(caminho.read_text(encoding="utf-8"))


def instante_epoch(valor: float | str) -> float:
    # O protocolo não fixa o formato de t_wall; aceita-se número (epoch) e o ISO usado nos demais campos.
    if isinstance(valor, (int, float)):
        return float(valor)
    return datetime.fromisoformat(valor.replace("Z", "+00:00")).timestamp()


def ler_jsonl(caminho: Path) -> tuple[list[dict], bool]:
    """Devolve as linhas e se a última estava truncada; um processo morto só pode truncar a última."""
    if not caminho.exists():
        return [], False
    linhas = [l for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]
    registros = []
    for indice, linha in enumerate(linhas):
        try:
            registros.append(json.loads(linha))
        except json.JSONDecodeError as erro:
            if indice == len(linhas) - 1:
                return registros, True
            raise ValueError(f"{caminho}: linha {indice + 1} inválida") from erro
    return registros, False
