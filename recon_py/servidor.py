from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

from recon_py.infraestrutura.threads_blas import fixar_threads_blas

BYTES_POR_MIB = 1024 * 1024


def _inteiro(minimo: int):
    def converter(texto: str) -> int:
        valor = int(texto)
        if valor < minimo:
            raise argparse.ArgumentTypeError(f"precisa ser >= {minimo}")
        return valor

    return converter


def ler_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    leitor = argparse.ArgumentParser(prog="python -m recon_py.servidor", description="Servidor de reconstrução em Python.")
    leitor.add_argument("--porta", type=_inteiro(0), required=True)
    leitor.add_argument("--dados", type=Path, required=True)
    leitor.add_argument("--saida", type=Path, required=True)
    leitor.add_argument("--workers", type=_inteiro(1), default=1)
    leitor.add_argument("--blas-threads", type=_inteiro(1), default=1)
    leitor.add_argument("--fila-max", type=_inteiro(1), default=256)
    leitor.add_argument("--fila-max-bytes", type=_inteiro(1), default=268435456)
    leitor.add_argument("--reserva-mem-mb", type=_inteiro(0), default=512)
    leitor.add_argument("--espera-mem-max-s", type=_inteiro(0), default=60)
    leitor.add_argument("--aquecer", default="", help="modelos separados por vírgula")
    return leitor.parse_args(argv)


def _medir_aquecimento(fila, modelos: list[str]) -> float:
    if not modelos:
        return 0.0
    inicio = time.perf_counter()
    fila.aquecer(modelos)
    return time.perf_counter() - inicio


def main(argv: list[str] | None = None) -> None:
    args = ler_argumentos(argv)
    fixar_threads_blas(args.blas_threads)

    import uvicorn

    from recon_py.api.app import criar_app
    from recon_py.api.rotas.metricas import DescricaoServidor
    from recon_py.aplicacao.fila.fila import OpcoesFila
    from recon_py.infraestrutura.matriz import carregar_manifesto
    from recon_py.montagem import montar_fila

    modelos = carregar_manifesto(args.dados)
    a_aquecer = [nome for nome in args.aquecer.split(",") if nome]
    desconhecidos = sorted(set(a_aquecer) - set(modelos))
    if desconhecidos:
        sys.exit(f"modelo desconhecido em --aquecer: {', '.join(desconhecidos)}")
    opcoes = OpcoesFila(
        workers=args.workers,
        fila_max=args.fila_max,
        fila_max_bytes=args.fila_max_bytes,
        reserva_bytes=args.reserva_mem_mb * BYTES_POR_MIB,
        espera_max_s=args.espera_mem_max_s,
    )
    fila = montar_fila(modelos, opcoes, args.saida)
    aquecimento_s = _medir_aquecimento(fila, a_aquecer)
    app = criar_app(fila, modelos, DescricaoServidor(args.workers, args.blas_threads, aquecimento_s))
    _anunciar(args, sorted(modelos), a_aquecer, aquecimento_s)
    config = uvicorn.Config(
        app, host="127.0.0.1", port=args.porta, log_level="warning", access_log=False, timeout_graceful_shutdown=5
    )
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    uvicorn.Server(config).run()


def _anunciar(args, modelos: list[str], aquecidos: list[str], aquecimento_s: float) -> None:
    from recon_py.api.rotas.metricas import descrever_blas
    from recon_py.infraestrutura.log_terminal import cabecalho, escrever

    aquecidos_txt = f"; aquecido: {', '.join(aquecidos)} em {aquecimento_s:.2f} s".replace(".", ",") if aquecidos else ""
    for linha in (
        f"Servidor Python em http://127.0.0.1:{args.porta} (Ctrl+C para parar)",
        f"  {args.workers} reconstruções ao mesmo tempo, {args.blas_threads} thread BLAS em cada uma, BLAS {descrever_blas()}",
        f"  Modelos: {', '.join(modelos)}{aquecidos_txt}",
        f"  Eventos também em {args.saida / 'events.jsonl'}",
        "",
        cabecalho(),
    ):
        escrever(linha)


if __name__ == "__main__":
    main()
