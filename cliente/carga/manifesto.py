"""Sorteia uma vez a sequência de pedidos e grava o arquivo de carga usado pelas duas versões."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from cliente.carga.sinais import crc32_arquivo, crc32_hex, ler_manifesto_dados, montar_corpo
from cliente.comum.caminhos import DADOS_PADRAO

ALGORITMOS = ("cgnr", "cgne")
MODOS_GANHO = ("sorteado", "sim", "nao")
MINIMO_CLIENTES = 3
MINIMO_SINAIS = 15


def _resumo_modelos(dados: Path, modelos: dict) -> dict:
    return {
        nome: {
            "linhas": modelo["linhas"], "colunas": modelo["colunas"], "S": modelo["S"], "N": modelo["N"],
            "largura": modelo["largura"], "altura": modelo["altura"], "sha256": modelo["sha256"],
            "sinais": {sinal: crc32_arquivo(dados / info["arquivo"]) for sinal, info in sorted(modelo["sinais"].items())},
        }
        for nome, modelo in sorted(modelos.items())
    }


def _validar_algoritmos(algoritmos: list[str] | None) -> list[str]:
    algoritmos = list(algoritmos) if algoritmos else list(ALGORITMOS)
    desconhecidos = sorted(set(algoritmos) - set(ALGORITMOS))
    if desconhecidos:
        raise ValueError(f"algoritmo desconhecido: {', '.join(desconhecidos)}")
    return algoritmos


def _escolher_modelos(dados: Path, modelos: list[str] | None) -> dict:
    disponiveis = ler_manifesto_dados(dados)
    desconhecidos = sorted(set(modelos or []) - set(disponiveis))
    if desconhecidos:
        raise ValueError(f"modelo desconhecido: {', '.join(desconhecidos)}")
    return {nome: disponiveis[nome] for nome in (modelos or disponiveis)}


def _sortear_pedido(rng: np.random.Generator, modelos: dict, algoritmos: list[str], ganho: str,
                    intervalo_max_s: float) -> dict:
    # A ordem dos sorteios faz parte do formato: mudá-la muda toda carga já gravada.
    nomes_modelos = sorted(modelos)
    nome_modelo = nomes_modelos[rng.integers(len(nomes_modelos))]
    sinais = sorted(modelos[nome_modelo]["sinais"])
    sinal = sinais[rng.integers(len(sinais))]
    sorteado = bool(rng.integers(2))
    com_ganho = sorteado if ganho == "sorteado" else ganho == "sim"
    algoritmo = algoritmos[rng.integers(len(algoritmos))]
    atraso = round(float(rng.uniform(0, intervalo_max_s)), 6)
    return {"modelo": nome_modelo, "sinal": sinal, "ganho": com_ganho, "algoritmo": algoritmo, "atraso_s": atraso}


def _crc_e_tamanho(dados: Path, modelos: dict, sorteio: dict, cache: dict[tuple[str, str, bool], tuple[str, int]]
                   ) -> tuple[str, int]:
    chave = (sorteio["modelo"], sorteio["sinal"], sorteio["ganho"])
    if chave not in cache:
        corpo = montar_corpo(dados, modelos[sorteio["modelo"]], sorteio["sinal"], sorteio["ganho"])
        cache[chave] = (crc32_hex(corpo), len(corpo))
    return cache[chave]


def gerar_carga(dados: Path, *, semente: int, clientes: int, sinais_por_cliente: int,
                algoritmos: list[str] | None, intervalo_max_s: float, modelos: list[str] | None = None,
                ganho: str = "sorteado") -> dict:
    """Mesmos argumentos e mesmos dados produzem exatamente o mesmo dicionário.

    `ganho` fixo ("sim" ou "nao") ainda consome o sorteio do ganho: modelo, sinal, algoritmo e atrasos
    ficam iguais aos da carga sorteada com a mesma semente; só ganho, CRC e corpo mudam.
    """
    algoritmos = _validar_algoritmos(algoritmos)
    if ganho not in MODOS_GANHO:
        raise ValueError(f"ganho deve ser {', '.join(MODOS_GANHO)}; recebido: {ganho}")
    if intervalo_max_s < 0:
        raise ValueError("intervalo máximo negativo")
    modelos = _escolher_modelos(dados, modelos)
    rng = np.random.default_rng(semente)
    cache_crc: dict[tuple[str, str, bool], tuple[str, int]] = {}
    pedidos = []
    for c in range(1, clientes + 1):
        instante = 0.0
        for s in range(1, sinais_por_cliente + 1):
            sorteio = _sortear_pedido(rng, modelos, algoritmos, ganho, intervalo_max_s)
            instante = round(instante + sorteio["atraso_s"], 6)
            crc, tamanho = _crc_e_tamanho(dados, modelos, sorteio, cache_crc)
            pedidos.append({"job_id": f"c{c:03d}-s{s:04d}", "client_id": f"cliente-{c:03d}", **sorteio,
                            "instante_planejado_s": instante, "crc32": crc, "tamanho_bytes": tamanho})
    parametros = {"clientes": clientes, "sinais_por_cliente": sinais_por_cliente,
                  "algoritmos": algoritmos, "intervalo_max_s": intervalo_max_s}
    if ganho != "sorteado":
        # Só aparece quando fixado: cargas sorteadas continuam iguais byte a byte às já gravadas.
        parametros["ganho"] = ganho
    return {
        "versao_formato": 1,
        "semente": semente,
        "gerador": "numpy.random.default_rng (PCG64)",
        "versao_numpy": np.__version__,
        "parametros": parametros,
        "atende_minimo_enunciado": clientes >= MINIMO_CLIENTES and sinais_por_cliente >= MINIMO_SINAIS,
        "modelos": _resumo_modelos(dados, modelos),
        "pedidos": pedidos,
    }


def gravar_carga(carga: dict, saida: Path) -> None:
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(carga, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semente", type=int, required=True)
    parser.add_argument("--clientes", type=int, required=True)
    parser.add_argument("--sinais-por-cliente", type=int, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--algoritmos", default=",".join(ALGORITMOS), help="lista separada por vírgula")
    parser.add_argument("--intervalo-max", type=float, default=5.0, help="atraso máximo antes de cada envio, em s")
    parser.add_argument("--modelos", help="lista separada por vírgula; padrão: todos os do manifesto")
    parser.add_argument("--ganho", choices=MODOS_GANHO, default="sorteado",
                        help="sorteado (padrão) ou fixo em todos os pedidos; o resto da sequência não muda")
    parser.add_argument("--dados", type=Path, default=DADOS_PADRAO)
    args = parser.parse_args(argv)
    carga = gerar_carga(args.dados, semente=args.semente, clientes=args.clientes,
                        sinais_por_cliente=args.sinais_por_cliente,
                        algoritmos=args.algoritmos.split(","), intervalo_max_s=args.intervalo_max,
                        modelos=args.modelos.split(",") if args.modelos else None, ganho=args.ganho)
    gravar_carga(carga, args.saida)
    if not carga["atende_minimo_enunciado"]:
        print(f"aviso: abaixo do mínimo do enunciado ({MINIMO_CLIENTES} clientes, {MINIMO_SINAIS} sinais por cliente)",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
