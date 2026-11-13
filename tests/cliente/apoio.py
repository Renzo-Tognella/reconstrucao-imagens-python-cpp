"""Dados sintéticos pequenos, no formato do manifesto real, para os testes do cliente."""
from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[2]
STUB = Path(__file__).with_name("stub_servidor.py")

COLUNAS_RECURSOS = [
    "t_wall", "t_s", "cpu_sistema_pct", "mem_usada_mb", "mem_disponivel_mb", "swap_usado_mb",
    "cpu_processo_pct", "rss_mb", "queue_depth", "running", "waiting_memory",
    "metrics_latencia_s", "metrics_pendente_s",
]


def binario_stub(pasta: Path, *extras: str, codigo: str | None = None) -> Path:
    """Executável com a linha de comando do protocolo, no lugar do binário C++."""
    caminho = pasta / "servidor_falso.sh"
    if codigo is None:
        conteudo = f'#!/bin/sh\ncd "{RAIZ}" && exec "{sys.executable}" "{STUB}" "$@" {" ".join(extras)}\n'
    else:
        conteudo = f"#!/bin/sh\necho falhou de proposito >&2\nexit {codigo}\n"
    caminho.write_text(conteudo)
    caminho.chmod(caminho.stat().st_mode | stat.S_IEXEC)
    return caminho


def criar_dados(raiz: Path, modelos: dict[str, tuple[int, int, int, int]] | None = None) -> Path:
    """`modelos` mapeia nome para (S, N, largura, altura); cria sinais g1 e g2 por modelo."""
    modelos = modelos or {"30x30": (4, 3, 2, 2)}
    manifesto: dict = {"modelos": {}}
    for nome, (S, N, largura, altura) in modelos.items():
        sinais = {}
        pasta = raiz / "sinais" / nome
        pasta.mkdir(parents=True, exist_ok=True)
        for indice, sinal in enumerate(("g1", "g2")):
            valores = np.arange(1.0, S * N + 1.0) * (indice + 1)
            valores.astype("<f8").tofile(pasta / f"{sinal}.f64")
            sinais[sinal] = {"arquivo": f"sinais/{nome}/{sinal}.f64", "referencia": None}
        manifesto["modelos"][nome] = {
            "linhas": S * N, "colunas": largura * altura, "S": S, "N": N,
            "largura": largura, "altura": altura, "arquivo": f"modelos/{nome}/H.f64",
            "sha256": "0" * 64, "sinais": sinais,
        }
    (raiz / "manifesto.json").write_text(json.dumps(manifesto))
    return raiz


def evento(t: float, nome: str, job: str, fila: int, execucao: int = 0, t_base: float = 1000.0) -> dict:
    return {"t_wall": t_base + t, "t_mono": 50.0 + t, "event": nome, "job_id": job,
            "queue_depth": fila, "running": execucao}


def criar_execucao(pasta: Path, *, impl: str = "python", workers: int = 1, blas_threads: int = 1,
                   blas: str = "accelerate", carga_crc: str = "aaaaaaaa", eventos: list[dict] | None = None,
                   recursos: list[dict] | None = None, jobs: list[dict] | None = None,
                   envios: list[dict] | None = None, desfechos: list[dict] | None = None,
                   atende_minimo: bool = True, estado: str = "concluida", planejados: list[float] | None = None,
                   aquecimento_s: float | None = None, aquecer: list[str] | None = None) -> Path:
    """Monta uma execução no formato que o cliente grava, sem servidor."""
    (pasta / "servidor" / "jobs").mkdir(parents=True)
    (pasta / "cliente" / "jobs").mkdir(parents=True)
    (pasta / "execucao.json").write_text(json.dumps({
        "estado": estado, "implementacao": impl, "workers": workers, "blas_threads": blas_threads,
        "info": {"implementation": impl, "workers": workers, "blas_threads": blas_threads, "blas": blas},
        "carga": {"crc32": carga_crc, "semente": 42, "atende_minimo_enunciado": atende_minimo, "pedidos": len(envios or [])},
        "memoria_inicial": {"disponivel_mb": 3000.0, "swap_usado_mb": 100.0},
        "maquina": {"host": "teste"}, "aquecimento_s": aquecimento_s, "aquecer": aquecer,
    }))
    if planejados is not None:
        (pasta / "carga.json").write_text(json.dumps({"pedidos": [{"instante_planejado_s": t} for t in planejados]}))
    eventos = eventos or []
    (pasta / "servidor" / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in eventos))
    for job in jobs or []:
        (pasta / "servidor" / "jobs" / f"{job['job_id']}.json").write_text(json.dumps(job))
    (pasta / "cliente" / "envios.jsonl").write_text("".join(json.dumps(e) + "\n" for e in envios or []))
    (pasta / "cliente" / "desfechos.jsonl").write_text("".join(json.dumps(e) + "\n" for e in desfechos or []))
    linhas = [",".join(COLUNAS_RECURSOS)]
    for amostra in recursos or []:
        linhas.append(",".join("" if amostra.get(c) is None else str(amostra.get(c)) for c in COLUNAS_RECURSOS))
    (pasta / "recursos.csv").write_text("\n".join(linhas) + "\n")
    return pasta


def amostra(t: float, fila: int | None, *, cpu: float = 90.0, rss: float = 400.0, t_base: float = 1000.0) -> dict:
    return {"t_wall": t_base + t, "t_s": t, "cpu_sistema_pct": 30.0, "mem_usada_mb": 5000.0,
            "mem_disponivel_mb": 2500.0, "swap_usado_mb": 150.0, "cpu_processo_pct": cpu, "rss_mb": rss,
            "queue_depth": fila, "running": None if fila is None else 1, "waiting_memory": None,
            "metrics_latencia_s": None if fila is None else 0.01, "metrics_pendente_s": None}


def job(job_id: str, *, status: str = "done", duracao: float | None = 1.0, fila: float | None = 0.5) -> dict:
    return {"job_id": job_id, "client_id": "c", "signal_id": "g1", "model": "30x30", "algorithm": "cgnr",
            "gain": True, "status": status, "received_at": "2026-11-04T12:00:00.000Z",
            "started_at": "2026-11-04T12:00:00.500Z", "finished_at": "2026-11-04T12:00:01.500Z",
            "queue_wait_s": fila, "duration_s": duracao, "iterations": 10, "stop_reason": "max_iterations",
            "residual_norms": [1.0], "error": None if status == "done" else "numerical_failure"}


def envio(job_id: str, *, status: int | None = 202, desfecho: str = "aceito", atraso: float | None = 0.002) -> dict:
    return {"job_id": job_id, "client_id": "c", "planejado_s": 1.0, "efetivo_s": None if atraso is None else 1.0 + atraso, "atraso_s": atraso,
            "duracao_post_s": 0.01, "status_http": status, "desfecho": desfecho, "erro": None}
