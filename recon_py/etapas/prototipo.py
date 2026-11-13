from __future__ import annotations

import argparse
import sys
from pathlib import Path

from recon_py.infraestrutura.threads_blas import fixar_threads_blas

SAIDA_FALHA_NUMERICA = 1
SAIDA_ERRO = 2


def _inteiro_positivo(texto: str) -> int:
    valor = int(texto)
    if valor < 1:
        raise argparse.ArgumentTypeError("precisa ser >= 1")
    return valor


def ler_argumentos(argv: list[str] | None) -> argparse.Namespace:
    leitor = argparse.ArgumentParser(prog="python -m recon_py.prototipo", description="Etapa 3: reconstruções repetidas sem servidor.")
    leitor.add_argument("--dados", type=Path, required=True)
    leitor.add_argument("--modelo", required=True)
    leitor.add_argument("--sinal", type=Path, required=True)
    leitor.add_argument("--algoritmo", choices=("cgnr", "cgne"), required=True)
    leitor.add_argument("--repeticoes", type=_inteiro_positivo, default=1)
    leitor.add_argument("--blas-threads", type=_inteiro_positivo, default=1)
    leitor.add_argument("--saida", type=Path)
    return leitor.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = ler_argumentos(argv)
    fixar_threads_blas(args.blas_threads)

    from recon_py.dominio.algoritmos.resultado import FalhaNumerica
    from recon_py.etapas.medicao import executar

    try:
        executar(args.dados, args.modelo, args.sinal, args.algoritmo, args.repeticoes, args.saida)
    except FalhaNumerica as erro:
        print(f"falha numérica: {erro}", file=sys.stderr)
        return SAIDA_FALHA_NUMERICA
    except (ValueError, OSError) as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return SAIDA_ERRO
    return 0


if __name__ == "__main__":
    sys.exit(main())
