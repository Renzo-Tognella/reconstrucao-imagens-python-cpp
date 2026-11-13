from __future__ import annotations

import argparse
import json
import queue
import re
import signal
import sys
import threading
import time
import zlib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import numpy as np

ID_VALIDO = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def agora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class Estado:
    def __init__(self, dados: Path, saida: Path, *, workers: int = 1, blas_threads: int = 1, fila_max: int = 256,
                 duracao_s: float = 0.02, atraso_post_s: float = 0.0, atraso_metrics_s: float = 0.0,
                 implementacao: str = "python", sinais_com_falha: tuple[str, ...] = (), aquecimento_s: float = 0.0):
        self.modelos = json.loads((dados / "manifesto.json").read_text())["modelos"]
        self.saida = saida
        (saida / "jobs").mkdir(parents=True, exist_ok=True)
        self.workers, self.blas_threads, self.fila_max = workers, blas_threads, fila_max
        self.duracao_s, self.atraso_post_s, self.atraso_metrics_s = duracao_s, atraso_post_s, atraso_metrics_s
        self.implementacao, self.sinais_com_falha = implementacao, sinais_com_falha
        self.metrics_ligado = True
        self.aquecimento_s = aquecimento_s
        self.trava = threading.Lock()
        self.fila: queue.Queue = queue.Queue()
        self.jobs: dict[str, dict] = {}
        self.crcs: dict[str, int] = {}
        self.vetores: dict[str, bytes] = {}
        self.imagens: dict[str, bytes] = {}
        self.em_execucao = 0
        self.contagem = dict(accepted=0, completed=0, failed=0, rejected=0)
        self.inicio = time.monotonic()
        self.parar = threading.Event()
        self.posts_recebidos: list[dict] = []
        self.max_pedidos_por_conexao = 0
        self.cabecalhos_connection: list[str | None] = []
        self.eventos_arquivo = (saida / "events.jsonl").open("a", encoding="utf-8")
        self.threads = [threading.Thread(target=self._trabalhar, daemon=True) for _ in range(workers)]
        for thread in self.threads:
            thread.start()

    def evento(self, nome: str, job_id: str) -> None:
        linha = {"t_wall": agora_iso(), "t_mono": time.monotonic(), "event": nome, "job_id": job_id,
                 "queue_depth": self.fila.qsize(), "running": self.em_execucao}
        self.eventos_arquivo.write(json.dumps(linha) + "\n")
        self.eventos_arquivo.flush()

    def _trabalhar(self) -> None:
        while not self.parar.is_set():
            try:
                job_id = self.fila.get(timeout=0.02)
            except queue.Empty:
                continue
            with self.trava:
                job = self.jobs[job_id]
                self.em_execucao += 1
                job["status"], job["started_at"] = "running", agora_iso()
                job["queue_wait_s"] = time.monotonic() - job.pop("_recebido")
                self.evento("started", job_id)
            inicio = time.monotonic()
            self.parar.wait(self.duracao_s)
            with self.trava:
                self.em_execucao -= 1
                job.update(finished_at=agora_iso(), duration_s=time.monotonic() - inicio)
                if job["signal_id"] in self.sinais_com_falha:
                    job.update(status="failed", error="numerical_failure", duration_s=None)
                    self.contagem["failed"] += 1
                    self.evento("failed", job_id)
                else:
                    self._concluir(job)
                    self.contagem["completed"] += 1
                    self.evento("finished", job_id)
                (self.saida / "jobs" / f"{job_id}.json").write_text(json.dumps(job))

    def _concluir(self, job: dict) -> None:
        modelo = self.modelos[job["model"]]
        job.update(status="done", iterations=10, stop_reason="max_iterations", residual_norms=[1.0, 0.5])
        pixels = bytes(i * 7 % 256 for i in range(modelo["colunas"]))
        cabecalho = f"P5\n{modelo['largura']} {modelo['altura']}\n255\n".encode()
        self.imagens[job["job_id"]] = cabecalho + pixels
        self.vetores[job["job_id"]] = np.ones(modelo["colunas"], dtype="<f8").tobytes()
        (self.saida / "jobs" / f"{job['job_id']}.pgm").write_bytes(self.imagens[job["job_id"]])
        (self.saida / "jobs" / f"{job['job_id']}.f64").write_bytes(self.vetores[job["job_id"]])

    def encerrar(self) -> None:
        self.parar.set()
        for thread in self.threads:
            thread.join(timeout=5)
        self.eventos_arquivo.close()


class Manipulador(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    estado: Estado

    def setup(self) -> None:
        super().setup()
        self.pedidos_nesta_conexao = 0

    def log_message(self, *_args) -> None:
        pass

    def _responder(self, status: int, corpo: bytes, tipo: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, status: int, corpo: dict) -> None:
        self._responder(status, json.dumps(corpo).encode())

    def _erro(self, status: int, codigo: str) -> None:
        self._json(status, {"error": codigo, "detail": codigo})

    def _contar_conexao(self) -> None:
        self.pedidos_nesta_conexao += 1
        estado = self.estado
        with estado.trava:
            estado.max_pedidos_por_conexao = max(estado.max_pedidos_por_conexao, self.pedidos_nesta_conexao)
            estado.cabecalhos_connection.append(self.headers.get("Connection"))

    def do_POST(self) -> None:
        self._contar_conexao()
        estado = self.estado
        url = urlsplit(self.path)
        corpo = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if url.path != "/jobs":
            return self._erro(404, "not_found")
        parametros = {k: v[0] for k, v in parse_qs(url.query).items()}
        with estado.trava:
            estado.posts_recebidos.append({"parametros": parametros, "crc": zlib.crc32(corpo), "tamanho": len(corpo)})
        time.sleep(estado.atraso_post_s)
        obrigatorios = ("job_id", "client_id", "signal_id", "model", "algorithm", "gain")
        if any(p not in parametros for p in obrigatorios) or parametros["gain"] not in ("0", "1") \
                or not all(ID_VALIDO.match(parametros[p]) for p in ("job_id", "client_id", "signal_id")):
            return self._erro(400, "invalid_params")
        modelo = estado.modelos.get(parametros["model"])
        if modelo is None:
            return self._erro(400, "unknown_model")
        if parametros["algorithm"] not in ("cgnr", "cgne"):
            return self._erro(400, "unknown_algorithm")
        if len(corpo) != 8 * modelo["linhas"]:
            return self._erro(400, "invalid_length")
        job_id = parametros["job_id"]
        with estado.trava:
            if job_id in estado.jobs:
                if estado.crcs[job_id] != zlib.crc32(corpo):
                    return self._erro(409, "job_conflict")
                return self._json(200, {"job_id": job_id, "status": estado.jobs[job_id]["status"]})
            if estado.fila.qsize() >= estado.fila_max:
                estado.contagem["rejected"] += 1
                estado.evento("rejected", job_id)
                return self._erro(503, "queue_full")
            estado.crcs[job_id] = zlib.crc32(corpo)
            estado.jobs[job_id] = {
                "job_id": job_id, "client_id": parametros["client_id"], "signal_id": parametros["signal_id"],
                "model": parametros["model"], "algorithm": parametros["algorithm"], "gain": parametros["gain"] == "1",
                "status": "queued", "received_at": agora_iso(), "started_at": None, "finished_at": None,
                "queue_wait_s": None, "duration_s": None, "iterations": None, "stop_reason": None,
                "residual_norms": None, "error": None, "_recebido": time.monotonic(),
            }
            estado.contagem["accepted"] += 1
            estado.fila.put(job_id)
            estado.evento("accepted", job_id)
        self._json(202, {"job_id": job_id, "status": "queued"})

    def do_GET(self) -> None:
        self._contar_conexao()
        estado = self.estado
        caminho = urlsplit(self.path).path
        if caminho == "/info":
            return self._json(200, {"implementation": estado.implementacao, "language_version": "stub", "blas": "stub",
                                    "workers": estado.workers, "blas_threads": estado.blas_threads,
                                    "models": sorted(estado.modelos), "aquecimento_s": estado.aquecimento_s})
        if caminho == "/metrics":
            if not estado.metrics_ligado:
                return self._erro(500, "desligado")
            time.sleep(estado.atraso_metrics_s)
            with estado.trava:
                return self._json(200, {"queue_depth": estado.fila.qsize(), "running": estado.em_execucao,
                                        **estado.contagem, "waiting_memory": False,
                                        "uptime_s": time.monotonic() - estado.inicio})
        partes = caminho.strip("/").split("/")
        if len(partes) < 2 or partes[0] != "jobs":
            return self._erro(404, "not_found")
        with estado.trava:
            job = estado.jobs.get(partes[1])
            job = None if job is None else {k: v for k, v in job.items() if not k.startswith("_")}
        if job is None:
            return self._erro(404, "not_found")
        if len(partes) == 2:
            return self._json(200, job)
        if job["status"] == "failed":
            return self._erro(409, "failed")
        if job["status"] != "done":
            return self._erro(409, "not_ready")
        if partes[2] == "image":
            return self._responder(200, estado.imagens[job["job_id"]], "image/x-portable-graymap")
        return self._responder(200, estado.vetores[job["job_id"]], "application/octet-stream")


class Stub:
    def __init__(self, dados: Path, saida: Path, porta: int = 0, **opcoes):
        self.estado = Estado(dados, saida, **opcoes)
        manipulador = type("ManipuladorStub", (Manipulador,), {"estado": self.estado})
        self.http = ThreadingHTTPServer(("127.0.0.1", porta), manipulador)
        self.http.daemon_threads = True
        self.porta = self.http.server_address[1]
        self.url = f"http://127.0.0.1:{self.porta}"
        self.thread = threading.Thread(target=self.http.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()

    def encerrar(self) -> None:
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=5)
        self.estado.encerrar()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--porta", type=int, required=True)
    parser.add_argument("--dados", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--blas-threads", type=int, default=1)
    parser.add_argument("--fila-max", type=int, default=256)
    parser.add_argument("--fila-max-bytes", type=int, default=268435456)
    parser.add_argument("--reserva-mem-mb", type=int, default=512)
    parser.add_argument("--espera-mem-max-s", type=int, default=60)
    parser.add_argument("--aquecer", default="")
    parser.add_argument("--ignorar-aquecer", action="store_true", help="aceita a opção e não aquece, para testar a checagem")
    parser.add_argument("--implementacao", default="cpp")
    parser.add_argument("--duracao-s", type=float, default=0.02)
    parser.add_argument("--workers-informados", type=int, help="mente em /info, para testar a checagem")
    parser.add_argument("--ignorar-sigterm", action="store_true")
    args = parser.parse_args()
    modelos_aquecer = [m for m in args.aquecer.split(",") if m]
    conhecidos = json.loads((args.dados / "manifesto.json").read_text())["modelos"]
    if any(m not in conhecidos for m in modelos_aquecer):
        print("modelo desconhecido em --aquecer", file=sys.stderr)
        return 2
    aquecimento_s = 0.0
    if modelos_aquecer and not args.ignorar_aquecer:
        inicio = time.monotonic()
        time.sleep(0.01)
        aquecimento_s = time.monotonic() - inicio
    stub = Stub(args.dados, args.saida, porta=args.porta, workers=args.workers, blas_threads=args.blas_threads,
                fila_max=args.fila_max, duracao_s=args.duracao_s, implementacao=args.implementacao,
                aquecimento_s=aquecimento_s)
    if args.workers_informados is not None:
        stub.estado.workers = args.workers_informados
    parar = threading.Event()
    if not args.ignorar_sigterm:
        signal.signal(signal.SIGTERM, lambda *_: parar.set())
    else:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    parar.wait()
    stub.encerrar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
