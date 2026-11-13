from __future__ import annotations

from pathlib import Path

from recon_py.aplicacao.fila.fila import Fila, OpcoesFila
from recon_py.aplicacao.fila.recursos_externos import RecursosExternos
from recon_py.dominio.modelo import Modelo
from recon_py.infraestrutura.eventos import RegistroDeEventos
from recon_py.infraestrutura.gravacao import PastaDeResultados
from recon_py.infraestrutura.matriz import mapear_h
from recon_py.infraestrutura.memoria import memoria_disponivel, memoria_fisica_total


def montar_recursos(saida: Path) -> RecursosExternos:
    resultados = PastaDeResultados(saida)
    return RecursosExternos(
        abrir_h=mapear_h,
        memoria_livre=memoria_disponivel,
        memoria_fisica=memoria_fisica_total,
        resultados=resultados,
        eventos=RegistroDeEventos(saida / "events.jsonl"),
    )


def montar_fila(modelos: dict[str, Modelo], opcoes: OpcoesFila, saida: Path) -> Fila:
    return Fila(modelos, opcoes, montar_recursos(saida))
