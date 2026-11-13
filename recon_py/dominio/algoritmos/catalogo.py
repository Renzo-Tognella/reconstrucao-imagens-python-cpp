"""Nome do algoritmo no pedido HTTP -> função que reconstrói."""
from __future__ import annotations

from recon_py.dominio.algoritmos.cgne import cgne
from recon_py.dominio.algoritmos.cgnr import cgnr

ALGORITMOS = {"cgnr": cgnr, "cgne": cgne}
