"""SIGTERM tratado como Ctrl+C, para os blocos `finally` fecharem as conexões e gravarem o que já chegou."""
from __future__ import annotations


def sair_por_sinal(*_args) -> None:
    raise KeyboardInterrupt
