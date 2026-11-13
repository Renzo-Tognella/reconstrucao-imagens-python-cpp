"""Mantém `python -m cliente.manifesto` funcionando; o código está em `cliente/carga/manifesto.py`."""
from __future__ import annotations

import sys

from cliente.carga.manifesto import main

if __name__ == "__main__":
    sys.exit(main())
