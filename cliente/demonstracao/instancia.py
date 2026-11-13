"""Um cliente por terminal: envia só os pedidos do cliente N da carga, na agenda contada do início deste processo.

Uso: python -m cliente.instancia --carga <carga.json> --cliente 1 --servidor http://127.0.0.1:8000 [--saida <pasta>]

A agenda (`instante_planejado_s`) vem da carga, então a sequência é a mesma contra o servidor Python e o C++.
O t0 é o início da agenda nesta instância, depois de ler a carga e conferir o servidor; cada terminal tem o seu.
Código de saída: 0 se todas as imagens ficaram prontas, 1 se alguma não ficou, 2 se o servidor não respondeu.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import TextIO

import httpx

from cliente.carga.sinais import crc32_arquivo
from cliente.comum.caminhos import DADOS_PADRAO, PASTA_DEMO
from cliente.comum.interrupcao import sair_por_sinal
from cliente.comum.registros import ler_json
from cliente.demonstracao.terminal import Pintor, Terminal, cor_ativa, linhas_resumo, nome_servidor, numero
from cliente.envio.enviar_sinais import CargaInvalida, executar_carga
from cliente.relatorios.relatorio_cliente import gerar_relatorio

URL_PADRAO = "http://127.0.0.1:8000"


class ServidorIndisponivel(RuntimeError):
    pass


def id_cliente(numero: int) -> str:
    return f"cliente-{numero:03d}"


def pedidos_do_cliente(carga: dict, numero: int) -> dict:
    """Cópia da carga com só os pedidos do cliente N, na ordem do arquivo."""
    alvo = id_cliente(numero)
    pedidos = [p for p in carga["pedidos"] if p["client_id"] == alvo]
    if not pedidos:
        disponiveis = ", ".join(sorted({p["client_id"] for p in carga["pedidos"]}))
        raise ValueError(f"{alvo} não está na carga; disponíveis: {disponiveis}")
    return {**carga, "pedidos": pedidos}


def com_ids_da_execucao(carga: dict, carimbo: str) -> dict:
    """Acrescenta o carimbo da execução a cada job_id.

    O servidor guarda as tarefas enquanto está ligado. Sem o carimbo, rodar a mesma carga de novo cairia em
    "já recebido" (200, nenhuma reconstrução nova) ou, se outra carga usou o mesmo id, em job_conflict (409).
    """
    return {**carga, "pedidos": [{**p, "job_id": f"{p['job_id']}-{carimbo}"} for p in carga["pedidos"]]}


def consultar_info(url: str) -> dict:
    try:
        resposta = httpx.get(f"{url}/info", timeout=5.0, trust_env=False, headers={"Connection": "close"})
    except httpx.TransportError as falha:
        raise ServidorIndisponivel(f"servidor não respondeu em {url}/info ({type(falha).__name__})") from falha
    if resposta.status_code != 200:
        raise ServidorIndisponivel(f"servidor não respondeu em {url}/info (HTTP {resposta.status_code})")
    return resposta.json()


def pasta_padrao(carga: Path, implementacao: str, cliente: str, momento: time.struct_time | None = None) -> Path:
    data_hora = time.strftime("%Y%m%d-%H%M%S", momento or time.localtime())
    return PASTA_DEMO / carga.stem / implementacao / cliente / data_hora


def _gravar_execucao(saida: Path, registro: dict) -> None:
    (saida / "execucao.json").write_text(json.dumps(registro, ensure_ascii=False, indent=1), encoding="utf-8")


def _relatorio(saida: Path, tela: Terminal) -> Path | None:
    if not (saida / "cliente" / "envios.jsonl").exists():
        return None
    # Falha no relatório não pode esconder o erro original nem os registros já gravados.
    try:
        return gerar_relatorio(saida)
    except (OSError, ValueError, KeyError) as erro:
        tela.escrever(f"relatório não gerado: {type(erro).__name__}: {erro}")
        return None


def _conferir_modelos(propria: dict, info: dict) -> None:
    faltando = sorted({p["modelo"] for p in propria["pedidos"]} - set(info.get("models", [])))
    if faltando:
        raise ServidorIndisponivel(f"modelos ausentes no servidor: {', '.join(faltando)}")


def _preparar_saida(saida: Path, propria: dict) -> None:
    if (saida / "cliente" / "envios.jsonl").exists():
        raise FileExistsError(f"{saida} já tem uma execução; escolha outra pasta")
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "carga.json").write_text(json.dumps(propria, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                      encoding="utf-8")


def _registro_inicial(cliente: str, url: str, info: dict, carga_caminho: Path, propria: dict) -> dict:
    return {"origem": "cliente.instancia", "cliente": cliente, "servidor": url,
            "implementacao": info.get("implementation"), "workers": info.get("workers"),
            "blas_threads": info.get("blas_threads"), "info": info,
            "carga": {"arquivo": str(carga_caminho), "crc32": crc32_arquivo(carga_caminho),
                      "semente": propria.get("semente"), "pedidos": len(propria["pedidos"])}}


def _cabecalho(cliente: str, propria: dict, info: dict, url: str, saida: Path, intervalo_consulta_s: float,
               pintar: Pintor) -> list[str]:
    instantes = [p["instante_planejado_s"] for p in propria["pedidos"]]
    numero_cliente = int(cliente.rsplit("-", 1)[1])
    threads = info.get("blas_threads")
    return [
        pintar(f"Cliente {numero_cliente} → servidor {nome_servidor(info.get('implementation'))} em {url}", "negrito"),
        f"  {info.get('workers')} reconstruções ao mesmo tempo, {threads} thread BLAS em cada uma",
        f"  {len(instantes)} sinais, enviados entre {numero(min(instantes), 1)} s e {numero(max(instantes), 1)} s "
        "depois do início",
        f"  Depois do último envio, pergunta ao servidor a cada {numero(intervalo_consulta_s, 1)} s "
        "se as imagens ficaram prontas",
        f"  Resultados em {saida}",
    ]


def executar_instancia(carga_caminho: Path, numero: int, url: str = URL_PADRAO, *, saida: Path | None = None,
                       dados: Path = DADOS_PADRAO, intervalo_consulta_s: float = 1.0, limite_s: float = 600.0,
                       terminal: TextIO = sys.stdout, cor: bool = False, carimbo: str | None = None) -> dict:
    url = url.rstrip("/")
    cliente = id_cliente(numero)
    momento = time.localtime()
    propria = com_ids_da_execucao(pedidos_do_cliente(ler_json(carga_caminho), numero),
                                  carimbo or time.strftime("%H%M%S", momento))
    info = consultar_info(url)
    _conferir_modelos(propria, info)
    saida = saida or pasta_padrao(carga_caminho, info.get("implementation", "servidor"), cliente, momento)
    _preparar_saida(saida, propria)
    registro = _registro_inicial(cliente, url, info, carga_caminho, propria)
    _gravar_execucao(saida, registro)

    pintar = Pintor(cor)
    tela = Terminal(terminal, pintar, propria["pedidos"], intervalo_consulta_s)
    for linha in _cabecalho(cliente, propria, info, url, saida, intervalo_consulta_s, pintar):
        tela.escrever(linha)
    tela.abrir_envios()
    try:
        resumo = asyncio.run(executar_carga(propria, url=url, dados=dados, saida=saida / "cliente", limite_s=limite_s,
                                            intervalo_consulta_s=intervalo_consulta_s, observador=tela))
    finally:
        # Mesmo interrompido, o relatório mostra o que chegou a acontecer.
        relatorio = _relatorio(saida, tela)
    registro["resumo_carga"] = resumo
    _gravar_execucao(saida, registro)
    for linha in linhas_resumo(cliente, resumo, tela.prontos, relatorio, pintar):
        tela.escrever(linha)
    return {"resumo": resumo, "saida": saida, "relatorio": relatorio}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--carga", type=Path, required=True, help="arquivo gerado por cliente.manifesto")
    parser.add_argument("--cliente", type=int, required=True, help="número do cliente na carga (1 = cliente-001)")
    parser.add_argument("--servidor", default=URL_PADRAO)
    parser.add_argument("--saida", type=Path, help=f"padrão: {PASTA_DEMO}/<carga>/<implementação>/cliente-00N/<data-hora>")
    parser.add_argument("--dados", type=Path, default=DADOS_PADRAO)
    parser.add_argument("--intervalo-consulta", type=float, default=1.0, help="segundos entre consultas GET /jobs/{id}")
    parser.add_argument("--limite-s", type=float, default=600.0, help="espera máxima pelas imagens depois do último envio")
    parser.add_argument("--cor", choices=("auto", "sim", "nao"), default="auto")
    args = parser.parse_args(argv)
    signal.signal(signal.SIGTERM, sair_por_sinal)
    try:
        resultado = executar_instancia(
            args.carga.resolve(), args.cliente, args.servidor, saida=args.saida.resolve() if args.saida else None,
            dados=args.dados.resolve(), intervalo_consulta_s=args.intervalo_consulta, limite_s=args.limite_s,
            cor=cor_ativa(args.cor, sys.stdout, os.environ))
    except (ServidorIndisponivel, CargaInvalida, ValueError, FileExistsError) as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrompido; registros e relatório parciais ficaram na pasta de saída", file=sys.stderr)
        return 130
    resumo = resultado["resumo"]
    return 0 if resumo["concluidos"] == resumo["pedidos"] else 1


if __name__ == "__main__":
    sys.exit(main())
