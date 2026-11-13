from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

from cliente.comum.registros import ler_json, ler_jsonl

COLUNAS = ["imagem", "situacao", "job_id", "cliente", "sinal", "modelo", "ganho", "algoritmo", "recebido",
           "inicio", "fim", "fila_s", "duracao_s", "iteracoes", "parada", "atraso_envio_s"]


def _situacao(envio: dict | None, desfecho: dict | None, tem_png: bool) -> tuple[str, bool]:
    if envio is None:
        return "sem registro de envio", False
    tipo = envio["desfecho"]
    if tipo == "rejeitado":
        return f"rejeitado (HTTP {envio['status_http']}: {envio['erro']})", False
    if tipo == "nao_enviado":
        return "não enviado (execução interrompida)", False
    if tipo == "erro_transporte":
        return f"erro de transporte ({envio['erro']})", False
    if tipo == "erro_http":
        return f"erro HTTP {envio['status_http']} ({envio['erro']})", False
    if desfecho is None:
        return "aceito, sem desfecho registrado", False
    final = desfecho["desfecho"]
    if final == "failed":
        return f"falhou ({desfecho['erro']})", False
    if final == "sem_conclusao":
        return f"sem conclusão no limite (último status: {desfecho['ultimo_status']})", False
    if final == "erro_download":
        return f"erro ao baixar ({desfecho['erro']})", False
    if not tem_png:
        return "imagem ausente no disco", False
    return "concluída", True


def _hora_local(valor: str | None) -> str:
    if not valor:
        return ""
    return datetime.fromisoformat(valor.replace("Z", "+00:00")).astimezone().isoformat(timespec="milliseconds")


def _num(valor: float | None) -> str:
    return "" if valor is None else f"{valor:.6f}"


def _texto(valor) -> str:
    return "" if valor is None else str(valor)


def _linha(pedido: dict, envio: dict | None, desfecho: dict | None, pasta: Path) -> dict[str, str]:
    job_id = pedido["job_id"]
    caminho_png = pasta / "cliente" / "jobs" / f"{job_id}.png"
    caminho_json = pasta / "cliente" / "jobs" / f"{job_id}.json"
    situacao, sucesso = _situacao(envio, desfecho, caminho_png.exists())
    metadados = ler_json(caminho_json) if caminho_json.exists() else {}
    return {
        "imagem": str(caminho_png.relative_to(pasta)) if sucesso else "",
        "situacao": situacao,
        "job_id": job_id,
        "cliente": pedido["client_id"],
        "sinal": pedido["sinal"],
        "modelo": pedido["modelo"],
        "ganho": "sim" if pedido["ganho"] else "não",
        "algoritmo": pedido["algoritmo"],
        "recebido": _hora_local(metadados.get("received_at")),
        "inicio": _hora_local(metadados.get("started_at")),
        "fim": _hora_local(metadados.get("finished_at")),
        "fila_s": _num(metadados.get("queue_wait_s")),
        "duracao_s": _num(metadados.get("duration_s")),
        "iteracoes": _texto(metadados.get("iterations")),
        "parada": _texto(metadados.get("stop_reason")),
        "atraso_envio_s": _num(envio.get("atraso_s") if envio else None),
    }


def gerar_relatorio(pasta: Path) -> Path:
    carga = ler_json(pasta / "carga.json")
    envios = {e["job_id"]: e for e in ler_jsonl(pasta / "cliente" / "envios.jsonl")[0]}
    desfechos = {d["job_id"]: d for d in ler_jsonl(pasta / "cliente" / "desfechos.jsonl")[0]}
    destino = pasta / "relatorio_cliente.csv"
    with destino.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS)
        escritor.writeheader()
        for pedido in carga["pedidos"]:
            escritor.writerow(_linha(pedido, envios.get(pedido["job_id"]), desfechos.get(pedido["job_id"]), pasta))
    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera o CSV de uma execução do cliente.")
    parser.add_argument("--execucao", type=Path, required=True, help="pasta gravada por cliente.instancia")
    args = parser.parse_args(argv)
    print(gerar_relatorio(args.execucao))
    return 0


if __name__ == "__main__":
    sys.exit(main())
