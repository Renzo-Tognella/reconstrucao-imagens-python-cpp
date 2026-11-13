from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

from monitor.coleta.coletor import Coletor
from monitor.web.app import criar_app


def ler_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    leitor = argparse.ArgumentParser(prog="python -m monitor", description="Monitor ao vivo do servidor de reconstrução.")
    leitor.add_argument("--servidor", required=True, help="URL do servidor, ex.: http://127.0.0.1:8000")
    leitor.add_argument("--saida", type=Path, default=None,
                        help="a mesma pasta passada ao servidor em --saida; se o processo do servidor for achado, "
                             "vale a pasta da linha de comando dele")
    leitor.add_argument("--porta", type=int, default=8050, help="porta da página do monitor (padrão 8050)")
    leitor.add_argument("--pid", type=int, default=None, help="PID do servidor; sem ele, procura por --porta")
    return leitor.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = ler_argumentos(argv)
    coletor = Coletor(args.servidor.rstrip("/"), args.saida, args.pid)
    print(f"monitor em http://127.0.0.1:{args.porta}  (servidor {args.servidor}; Ctrl+C encerra)", flush=True)
    uvicorn.run(criar_app(coletor), host="127.0.0.1", port=args.porta, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
