from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from typing import BinaryIO

import numpy as np

RAIZ_PROJETO = Path(__file__).resolve().parent
DESCRICAO = """Converte os CSVs do enunciado para binários float64 em `dados/`, lidos pelos dois servidores.

Os originais não são alterados. Executar uma vez: `python preparar_dados.py`.
"""
FORNECIDOS = RAIZ_PROJETO / "dados-fornecidos"
DADOS_30 = FORNECIDOS / "30x30"
DADOS_60 = FORNECIDOS / "60x60"

MODELOS = {
    "30x30": {
        "linhas": 27904, "colunas": 900, "S": 436, "N": 64, "largura": 30, "altura": 30,
        "matriz": DADOS_30 / "H-2.csv.zip",
        "sinais": {
            "g1": (DADOS_30 / "g-30x30-1.csv", DADOS_30 / "f-30x30-1.png"),
            "g2": (DADOS_30 / "g-30x30-2.csv", DADOS_30 / "f-30x30-2.png"),
            "g3": (DADOS_30 / "A-30x30-1.csv", None),
        },
    },
    "60x60": {
        "linhas": 50816, "colunas": 3600, "S": 794, "N": 64, "largura": 60, "altura": 60,
        # 152 MB, fora do repositório: baixar de https://nuvem.utfpr.edu.br/index.php/s/GcirTvh7gBDsne6/download
        "matriz": DADOS_60 / "H-1.csv.zip",
        "sinais": {
            "g1": (DADOS_60 / "G-1.csv", DADOS_60 / "F-1.png"),
            "g2": (DADOS_60 / "G-2.csv", DADOS_60 / "F-2.png"),
            "g3": (DADOS_60 / "A-60x60-1.csv", None),
        },
    },
}


def _abrir_csv(caminho: Path) -> BinaryIO:
    if caminho.suffix != ".zip":
        return caminho.open("rb")
    arquivo = zipfile.ZipFile(caminho)
    # O zip do modelo 60x60 foi criado no macOS e traz também metadados em __MACOSX/.
    nomes = [nome for nome in arquivo.namelist() if not nome.startswith("__MACOSX/")]
    if len(nomes) != 1:
        raise ValueError(f"{caminho}: esperado um CSV, encontrados {nomes}")
    return arquivo.open(nomes[0])


def converter_matriz(origem: Path, destino: Path, linhas: int, colunas: int) -> None:
    """Grava a matriz por colunas lendo uma linha do CSV por vez.

    A matriz 60x60 ocupa 1,4 GiB: carregá-la inteira na RAM empurraria uma máquina de 8 GB para o swap.
    As páginas do mapeamento são de arquivo, e o sistema pode devolvê-las ao disco sem usar swap.
    """
    temporario = destino.with_suffix(".parcial")
    try:
        matriz = np.memmap(temporario, dtype="<f8", mode="w+", shape=(linhas, colunas), order="F")
        lidas = 0
        with _abrir_csv(origem) as entrada:
            for texto in entrada:
                linha = np.array(texto.split(b","), dtype=np.float64)
                if lidas >= linhas or linha.size != colunas:
                    raise ValueError(f"{origem}: linha {lidas + 1} com {linha.size} colunas; esperado {linhas}x{colunas}")
                matriz[lidas, :] = linha
                lidas += 1
                if lidas % 2000 == 0:
                    matriz.flush()
        if lidas != linhas:
            raise ValueError(f"{origem}: {lidas} linhas; esperado {linhas}")
        matriz.flush()
        del matriz
        temporario.replace(destino)
    finally:
        temporario.unlink(missing_ok=True)


def sha256(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as entrada:
        while bloco := entrada.read(1 << 20):
            resumo.update(bloco)
    return resumo.hexdigest()


def preparar_modelo(nome: str, modelo: dict, destino: Path) -> dict | None:
    if not modelo["matriz"].exists():
        print(f"{nome}: matriz ausente em {modelo['matriz']}; modelo ignorado")
        return None
    arquivo_h = destino / "modelos" / nome / "H.f64"
    arquivo_h.parent.mkdir(parents=True, exist_ok=True)
    if not arquivo_h.exists():
        converter_matriz(modelo["matriz"], arquivo_h, modelo["linhas"], modelo["colunas"])
    sinais = {}
    for id_sinal, (csv, referencia) in modelo["sinais"].items():
        sinal = np.loadtxt(csv, dtype=np.float64)
        if sinal.shape != (modelo["linhas"],):
            raise ValueError(f"{nome}/{id_sinal}: tamanho {sinal.shape} inesperado")
        arquivo = destino / "sinais" / nome / f"{id_sinal}.f64"
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_bytes(sinal.astype("<f8").tobytes())
        sinais[id_sinal] = {
            "arquivo": str(arquivo.relative_to(destino)),
            "referencia": str(referencia) if referencia else None,
        }
    campos = ("linhas", "colunas", "S", "N", "largura", "altura")
    return {
        **{campo: modelo[campo] for campo in campos},
        "arquivo": str(arquivo_h.relative_to(destino)),
        "sha256": sha256(arquivo_h),
        "sinais": sinais,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=DESCRICAO)
    parser.add_argument("--destino", type=Path, default=RAIZ_PROJETO / "dados")
    args = parser.parse_args()
    preparados = {nome: preparar_modelo(nome, m, args.destino) for nome, m in MODELOS.items()}
    manifesto = {"modelos": {nome: m for nome, m in preparados.items() if m}}
    (args.destino / "manifesto.json").write_text(json.dumps(manifesto, indent=2) + "\n")
    print("modelos prontos:", ", ".join(manifesto["modelos"]))


if __name__ == "__main__":
    main()
