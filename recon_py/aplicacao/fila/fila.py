"""Fila FIFO do contrato: um despachante escolhe a próxima tarefa e um pool de workers reconstrói."""
from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from recon_py.aplicacao.fila.controle_memoria import ControleDeMemoria, custo_bytes
from recon_py.aplicacao.fila.recursos_externos import RecursosExternos
from recon_py.aplicacao.fila.tarefa import (
    INSUFFICIENT_MEMORY,
    INTERNAL_ERROR,
    NUMERICAL_FAILURE,
    OUTPUT_WRITE_FAILED,
    TERMINAIS,
    Pedido,
    Tarefa,
)
from recon_py.aplicacao.metricas import Contadores
from recon_py.aplicacao.relogio import agora_iso
from recon_py.dominio.algoritmos.catalogo import ALGORITMOS
from recon_py.dominio.algoritmos.produtos import aquecer_produtos
from recon_py.dominio.algoritmos.resultado import FalhaNumerica, Resultado
from recon_py.dominio.imagem import pgm
from recon_py.dominio.modelo import Modelo

REAVALIACAO_MEMORIA_S = 0.1


class Conflito(Exception):
    """Mesmo job_id com corpo ou metadados diferentes."""


class FilaCheia(Exception):
    """Limite de --fila-max ou --fila-max-bytes atingido."""


@dataclass(frozen=True)
class OpcoesFila:
    workers: int
    fila_max: int
    fila_max_bytes: int
    reserva_bytes: int
    espera_max_s: float


class Fila:
    def __init__(self, modelos: dict[str, Modelo], opcoes: OpcoesFila, recursos: RecursosExternos) -> None:
        self._modelos = modelos
        self._opcoes = opcoes
        self._abrir_h = recursos.abrir_h
        self._resultados = recursos.resultados
        self._eventos = recursos.eventos
        self.caminho_eventos = recursos.eventos.caminho
        self._trava = threading.Condition()
        self._fila: deque[Tarefa] = deque()
        self._tarefas: dict[str, Tarefa] = {}
        self._mapas: dict[str, np.ndarray] = {}
        self._bytes_na_fila = 0
        self._em_execucao = 0
        self._memoria = ControleDeMemoria(
            opcoes.reserva_bytes, opcoes.espera_max_s, recursos.memoria_livre, recursos.memoria_fisica
        )
        self._contadores = Contadores()
        self._encerrando = False
        self._pool = ThreadPoolExecutor(opcoes.workers, thread_name_prefix="reconstrucao")
        self._despachante = threading.Thread(target=self._despachar, name="despachante", daemon=True)

    def iniciar(self) -> None:
        self._despachante.start()

    def aquecer(self, nomes: list[str]) -> None:
        for nome in nomes:
            aquecer_produtos(self._h_do_modelo(self._modelos[nome]))

    def encerrar(self) -> None:
        with self._trava:
            self._encerrando = True
            self._trava.notify_all()
        self._despachante.join()
        self._pool.shutdown(wait=True)
        self._eventos.fechar()

    def submeter(self, pedido: Pedido) -> tuple[bool, str]:
        """Devolve (nova, status). Reenvio idêntico não cria tarefa."""
        with self._trava:
            existente = self._tarefas.get(pedido.job_id)
            if existente is not None:
                if existente.identidade != pedido.identidade():
                    raise Conflito(pedido.job_id)
                return False, existente.corpo["status"]
            if self._fila_cheia(pedido.sinal.nbytes):
                self._contadores.somar("rejected")
                self._registrar_evento("rejected", pedido.job_id)
                raise FilaCheia(pedido.job_id)
            tarefa = Tarefa(pedido)
            self._tarefas[tarefa.job_id] = tarefa
            self._fila.append(tarefa)
            self._bytes_na_fila += tarefa.tamanho_bytes
            self._contadores.somar("accepted")
            self._registrar_evento("accepted", tarefa.job_id)
            self._trava.notify_all()
            return True, tarefa.corpo["status"]

    def consultar(self, job_id: str) -> dict | None:
        with self._trava:
            tarefa = self._tarefas.get(job_id)
            return None if tarefa is None else dict(tarefa.corpo)

    def metricas(self) -> dict:
        with self._trava:
            return self._contadores.resumo(len(self._fila), self._em_execucao, self._memoria.aguardando)

    def caminho_resultado(self, job_id: str, extensao: str) -> Path:
        return self._resultados.caminho(job_id, extensao)

    def _fila_cheia(self, tamanho_bytes: int) -> bool:
        return (
            len(self._fila) >= self._opcoes.fila_max
            or self._bytes_na_fila + tamanho_bytes > self._opcoes.fila_max_bytes
        )

    def _registrar_evento(self, evento: str, job_id: str) -> None:
        self._eventos.registrar(
            {
                "t_wall": agora_iso(),
                "t_mono": time.monotonic(),
                "event": evento,
                "job_id": job_id,
                "queue_depth": len(self._fila),
                "running": self._em_execucao,
            },
            self._tarefas[job_id].corpo if job_id in self._tarefas else None,
        )

    def _despachar(self) -> None:
        while True:
            with self._trava:
                while not self._encerrando and not (self._fila and self._em_execucao < self._opcoes.workers):
                    self._trava.wait()
                if self._encerrando:
                    return
                sem_memoria = self._avaliar_cabeca()
            if sem_memoria is not None:
                self._falhar(sem_memoria, INSUFFICIENT_MEMORY)

    def _avaliar_cabeca(self) -> Tarefa | None:
        """Inicia a cabeça se couber. Devolve a cabeça se ela precisa falhar por falta de memória."""
        modelo = self._modelos[self._fila[0].corpo["model"]]
        if self._memoria.h_nunca_cabera(modelo, modelo.nome in self._mapas):
            return self._retirar_cabeca()
        custo = custo_bytes(modelo)
        if self._memoria.cabe(custo):
            self._iniciar_cabeca(custo)
            return None
        if self._memoria.esperar(self._em_execucao):
            return self._retirar_cabeca()
        self._trava.wait(REAVALIACAO_MEMORIA_S)
        return None

    def _retirar_cabeca(self) -> Tarefa:
        tarefa = self._fila.popleft()
        self._bytes_na_fila -= tarefa.tamanho_bytes
        self._memoria.encerrar_espera()
        return tarefa

    def _iniciar_cabeca(self, custo: int) -> None:
        tarefa = self._retirar_cabeca()
        tarefa.custo = custo
        self._memoria.reservar(custo)
        self._em_execucao += 1
        tarefa.corpo["status"] = "running"
        tarefa.corpo["started_at"] = agora_iso()
        tarefa.corpo["queue_wait_s"] = time.monotonic() - tarefa.recebida_mono
        self._registrar_evento("started", tarefa.job_id)
        self._pool.submit(self._executar, tarefa)

    def _executar(self, tarefa: Tarefa) -> None:
        try:
            self._reconstruir(tarefa)
        except FalhaNumerica:
            self._falhar(tarefa, NUMERICAL_FAILURE)
        except MemoryError:
            self._falhar(tarefa, INSUFFICIENT_MEMORY)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            self._falhar(tarefa, INTERNAL_ERROR)

    def _reconstruir(self, tarefa: Tarefa) -> None:
        modelo = self._modelos[tarefa.corpo["model"]]
        H = self._h_do_modelo(modelo)
        inicio = time.perf_counter()
        resultado = ALGORITMOS[tarefa.corpo["algorithm"]](H, tarefa.sinal)
        duracao = time.perf_counter() - inicio
        medidas = {
            "finished_at": agora_iso(),
            "duration_s": duracao,
            "iterations": resultado.iterations,
            "stop_reason": resultado.stop_reason,
            "residual_norms": resultado.residual_norms,
        }
        finais = {"status": "done"} | medidas
        try:
            self._gravar_imagem_e_vetor(tarefa, resultado, modelo)
            self._gravar_corpo(tarefa, finais)
        except OSError:
            traceback.print_exc(file=sys.stderr)
            self._falhar(tarefa, OUTPUT_WRITE_FAILED, medidas)
            return
        self._finalizar(tarefa, finais, "finished", "completed")

    def _h_do_modelo(self, modelo: Modelo) -> np.ndarray:
        with self._trava:
            if modelo.nome not in self._mapas:
                self._mapas[modelo.nome] = self._abrir_h(modelo)
            return self._mapas[modelo.nome]

    def _gravar_imagem_e_vetor(self, tarefa: Tarefa, resultado: Resultado, modelo: Modelo) -> None:
        self._resultados.gravar(tarefa.job_id, "pgm", pgm(resultado.f, modelo.largura, modelo.altura))
        self._resultados.gravar(tarefa.job_id, "f64", resultado.f.tobytes())

    def _gravar_corpo(self, tarefa: Tarefa, finais: dict) -> None:
        self._resultados.gravar(tarefa.job_id, "json", json.dumps(tarefa.corpo | finais).encode())

    def _falhar(self, tarefa: Tarefa, codigo: str, medidas: dict | None = None) -> None:
        with self._trava:
            # Um erro depois da conclusão não pode reescrever o resultado nem contar a tarefa duas vezes.
            if tarefa.corpo["status"] in TERMINAIS:
                return
        finais = {"finished_at": agora_iso()} | (medidas or {}) | {"status": "failed", "error": codigo}
        try:
            self._gravar_corpo(tarefa, finais)
        except OSError:
            traceback.print_exc(file=sys.stderr)
        self._finalizar(tarefa, finais, "failed", "failed")

    def _finalizar(self, tarefa: Tarefa, finais: dict, evento: str, contador: str) -> None:
        # O status só muda aqui, depois da gravação: quem lê `done` encontra os arquivos prontos.
        with self._trava:
            if tarefa.corpo["status"] == "running":
                self._em_execucao -= 1
                self._memoria.liberar(tarefa.custo)
            tarefa.corpo.update(finais)
            tarefa.sinal = None
            self._contadores.somar(contador)
            self._trava.notify_all()
            self._registrar_evento(evento, tarefa.job_id)
