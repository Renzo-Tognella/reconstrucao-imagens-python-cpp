"""Decide se a tarefa da frente cabe na RAM, quanto ela reserva e quando desistir de esperar."""
from __future__ import annotations

import time
from collections.abc import Callable

from recon_py.dominio.modelo import Modelo


def custo_bytes(modelo: Modelo) -> int:
    return 8 * (2 * modelo.linhas + 3 * modelo.colunas)


class ControleDeMemoria:
    """Quem chama segura a trava da fila: nada aqui é protegido por conta própria."""

    def __init__(
        self,
        reserva_bytes: int,
        espera_max_s: float,
        memoria_livre: Callable[[], int],
        memoria_fisica: Callable[[], int],
    ) -> None:
        self._reserva_bytes = reserva_bytes
        self._espera_max_s = espera_max_s
        self._memoria_livre = memoria_livre
        self._memoria_fisica = memoria_fisica
        self._reservado = 0
        self._parada_desde: float | None = None
        self.aguardando = False

    def h_nunca_cabera(self, modelo: Modelo, ja_mapeada: bool) -> bool:
        tamanho_h = 8 * modelo.linhas * modelo.colunas
        return not ja_mapeada and tamanho_h > self._memoria_fisica() - self._reserva_bytes

    def cabe(self, custo: int) -> bool:
        return self._memoria_livre() - self._reservado >= custo + self._reserva_bytes

    def esperar(self, em_execucao: int) -> bool:
        """Marca a espera por memória. Devolve True quando o prazo acabou e a tarefa deve falhar."""
        self.aguardando = True
        # Enquanto algo roda, a memória ainda pode voltar: só conta o tempo contínuo sem nada em execução.
        if em_execucao > 0:
            self._parada_desde = None
            return False
        agora = time.monotonic()
        if self._parada_desde is None:
            self._parada_desde = agora
        return agora - self._parada_desde > self._espera_max_s

    def encerrar_espera(self) -> None:
        self.aguardando = False
        self._parada_desde = None

    def reservar(self, custo: int) -> None:
        self._reservado += custo

    def liberar(self, custo: int) -> None:
        self._reservado -= custo
