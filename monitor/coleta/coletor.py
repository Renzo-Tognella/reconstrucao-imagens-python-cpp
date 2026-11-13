from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from collections import deque
from pathlib import Path
from urllib.parse import urlparse

import psutil

from cliente.comum.registros import instante_epoch
from monitor.medicao.indicadores import EVENTOS_CONCLUSAO
from monitor.coleta.consulta_servidor import ConsultaServidor
from monitor.coleta.eventos import LeitorEventos
from monitor.coleta.processo import descobrir_pid, saida_do_processo
from monitor.coleta.recursos import AmostradorRecursos
from monitor.estado import montar_estado

INTERVALO_S = 0.5
PONTOS_NA_SERIE = 1200
CONSULTAS_POR_CICLO = 20
BUSCA_PID_A_CADA_S = 2.0
FOLGA_INICIO_SERVIDOR_S = 1.0


class Coletor:
    def __init__(self, url: str, saida: Path | None, pid: int | None, intervalo_s: float = INTERVALO_S) -> None:
        self.url = url
        self.intervalo_s = intervalo_s
        self._porta = urlparse(url).port or 80
        self._consulta = ConsultaServidor(url)
        self._recursos = AmostradorRecursos()
        self._pid_informado = pid
        self._pid: int | None = None
        self._ultima_busca_pid = 0.0
        self._saida: Path | None = None
        self._leitor: LeitorEventos | None = None
        self._info: dict | None = None
        self._metrics: dict | None = None
        self._ultimo_uptime: float | None = None
        self._corte: float | None = None
        self._rodada = 0
        self._pedido_nova_rodada: float | None = None
        self._eventos: list[dict] = []
        self._metadados: dict[str, dict] = {}
        self._com_json_final: set[str] = set()
        self._series: deque[dict] = deque(maxlen=PONTOS_NA_SERIE)
        self._fila_1s: list[tuple[float, int]] = []
        self._proxima_amostra_1s = 0.0
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self.retrato: dict = {"conexao": {"estado": "iniciando", "erro": None, "servidor": url}}
        if saida is not None:
            self._trocar_saida(saida.resolve())


    def iniciar(self) -> None:
        self._thread = threading.Thread(target=self._laco, name="coletor", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._consulta.fechar()

    def nova_rodada(self) -> None:
        self._pedido_nova_rodada = time.time()

    def _laco(self) -> None:
        while not self._parar.is_set():
            inicio = time.monotonic()
            try:
                self.ciclo()
            except Exception:
                traceback.print_exc(file=sys.stderr)
            self._parar.wait(max(0.0, self.intervalo_s - (time.monotonic() - inicio)))


    def ciclo(self) -> None:
        agora = time.time()
        if self._pedido_nova_rodada is not None:
            self._iniciar_rodada(self._pedido_nova_rodada)
            self._pedido_nova_rodada = None
        metrics = self._consulta.metrics()
        reiniciou = self._detectar_reinicio(metrics)
        if self._atualizar_processo(reiniciou, agora):
            reiniciou = True
        if metrics is not None:
            if self._info is None or reiniciou:
                self._info = self._consulta.info()
            inicio_servidor = agora - metrics["uptime_s"] - FOLGA_INICIO_SERVIDOR_S
            if self._corte is None or reiniciou:
                self._iniciar_rodada(inicio_servidor)
        self._ler_eventos()
        self._buscar_metadados()
        self._amostrar(metrics, agora)
        self.retrato = self._montar_retrato(metrics, agora)

    def _detectar_reinicio(self, metrics: dict | None) -> bool:
        if metrics is None:
            return False
        anterior, self._ultimo_uptime = self._ultimo_uptime, metrics["uptime_s"]
        self._metrics = metrics
        return anterior is not None and metrics["uptime_s"] + INTERVALO_S < anterior

    def _atualizar_processo(self, reiniciou: bool, agora: float) -> bool:
        if self._recursos.processo_vivo() and not reiniciou:
            return False
        if agora - self._ultima_busca_pid < BUSCA_PID_A_CADA_S and not reiniciou:
            return False
        self._ultima_busca_pid = agora
        pid = self._pid_informado if self._pid_informado and psutil.pid_exists(self._pid_informado) else None
        pid = pid or descobrir_pid(self._porta)
        if pid is None:
            return False
        anterior, self._pid = self._pid, pid
        self._recursos.trocar_pid(pid)
        saida = saida_do_processo(pid)
        if saida is not None and saida != self._saida:
            self._trocar_saida(saida)
        return anterior is not None and anterior != pid

    def _trocar_saida(self, saida: Path) -> None:
        self._saida = saida
        self._leitor = LeitorEventos(saida / "events.jsonl")
        self._eventos = []
        self._metadados.clear()
        self._com_json_final.clear()

    def _iniciar_rodada(self, corte: float) -> None:
        self._corte = corte
        self._rodada += 1
        self._eventos = [e for e in self._eventos if e["t_epoch"] >= corte]
        self._metadados.clear()
        self._com_json_final.clear()
        self._series.clear()
        self._fila_1s = []

    def _ler_eventos(self) -> None:
        if self._leitor is None:
            return
        for evento in self._leitor.ler_novos():
            try:
                evento["t_epoch"] = instante_epoch(evento["t_wall"])
                float(evento["t_mono"]), evento["event"], evento["job_id"], int(evento["queue_depth"])
            except (KeyError, TypeError, ValueError):
                self._leitor.linhas_invalidas += 1
                continue
            if self._corte is None or evento["t_epoch"] >= self._corte:
                self._eventos.append(evento)

    def _buscar_metadados(self) -> None:
        terminais = {e["job_id"] for e in self._eventos if e["event"] in EVENTOS_CONCLUSAO}
        aceitos = list(dict.fromkeys(e["job_id"] for e in self._eventos if e["event"] == "accepted"))
        consultas = 0
        for job_id in aceitos:
            if job_id in self._com_json_final:
                continue
            if job_id in terminais and self._saida is not None:
                corpo = _ler_json(self._saida / "jobs" / f"{job_id}.json")
                if corpo is not None:
                    self._metadados[job_id] = corpo
                    self._com_json_final.add(job_id)
                    continue
            if job_id not in self._metadados and consultas < CONSULTAS_POR_CICLO:
                consultas += 1
                corpo = self._consulta.tarefa(job_id)
                if corpo is not None:
                    self._metadados[job_id] = corpo

    def _amostrar(self, metrics: dict | None, agora: float) -> None:
        amostra = self._recursos.amostrar()
        amostra["queue_depth"] = metrics["queue_depth"] if metrics else None
        amostra["running"] = metrics["running"] if metrics else None
        self._series.append(amostra)
        if metrics is not None and agora >= self._proxima_amostra_1s:
            self._fila_1s.append((agora, int(metrics["queue_depth"])))
            self._proxima_amostra_1s = max(self._proxima_amostra_1s + 1.0, agora + 0.5)

    def _montar_retrato(self, metrics: dict | None, agora: float) -> dict:
        estado = montar_estado(self._eventos, self._metadados, self._fila_1s, agora)
        conectado = metrics is not None
        estado.update(
            agora=agora,
            conexao={"estado": "conectado" if conectado else "sem_resposta",
                     "erro": None if conectado else self._consulta.ultimo_erro, "servidor": self.url},
            info=self._info,
            metrics=metrics,
            processo={"pid": self._pid if self._recursos.processo_vivo() else None,
                      "saida": str(self._saida) if self._saida else None,
                      "linhas_invalidas": self._leitor.linhas_invalidas if self._leitor else 0},
            rodada={"numero": self._rodada, "inicio": self._corte},
            recursos=self._series[-1] if self._series else None,
            series=list(self._series),
        )
        return estado


def _ler_json(caminho: Path) -> dict | None:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
