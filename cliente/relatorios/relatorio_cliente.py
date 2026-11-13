"""Relatório HTML autossuficiente: uma linha por pedido, com a imagem e os dados exigidos no enunciado."""
from __future__ import annotations

import argparse
import base64
import html
import sys
from pathlib import Path

from cliente.comum.registros import ler_json, ler_jsonl

ESTILO = """
:root { --fundo:#fcfcfb; --tinta:#1f1f1d; --tinta2:#5f5e57; --linha:#dedcd3; --destaque:#f4f3ee; --problema:#b3261e; --ok:#1a7f4b; }
@media (prefers-color-scheme: dark) { :root { --fundo:#1a1a19; --tinta:#f0efec; --tinta2:#c3c2b7; --linha:#3a3a37; --destaque:#262624; --problema:#f28b82; --ok:#6fcf97; } }
* { box-sizing: border-box; }
body { margin:0; padding:24px 16px; background:var(--fundo); color:var(--tinta); font:14px/1.45 -apple-system,"Segoe UI",Roboto,sans-serif; }
h1 { font-size:22px; margin:0 0 4px; }
.sub { color:var(--tinta2); margin:0 0 16px; }
.resumo { display:flex; flex-wrap:wrap; gap:12px; margin:0 0 20px; padding:0; list-style:none; }
.resumo li { background:var(--destaque); border-radius:8px; padding:8px 14px; min-width:110px; }
.resumo strong { display:block; font-size:22px; font-variant-numeric:tabular-nums; }
.rolagem { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }
th { text-align:left; font-weight:600; color:var(--tinta2); }
th,td { padding:6px 10px; border-bottom:1px solid var(--linha); vertical-align:middle; white-space:nowrap; }
td.situacao { white-space:normal; min-width:170px; }
img { display:block; width:90px; height:90px; image-rendering:pixelated; border:1px solid var(--linha); }
.sem-imagem { display:flex; align-items:center; justify-content:center; width:90px; height:90px; border:1px dashed var(--linha); color:var(--tinta2); font-size:12px; }
.marca { font-weight:600; }
tr.problema .marca { color:var(--problema); }
tr.sucesso .marca { color:var(--ok); }
"""

CABECALHOS = ["Imagem", "Situação", "Job", "Cliente", "Sinal", "Modelo", "Ganho", "Algoritmo", "Recebido",
              "Início", "Fim", "Fila (s)", "Duração (s)", "Iterações", "Parada", "Atraso de envio (s)"]


def _situacao(envio: dict | None, desfecho: dict | None, tem_png: bool) -> tuple[str, bool]:
    """Só é sucesso a tarefa concluída com a imagem presente."""
    if envio is None:
        return "sem registro de envio", False
    tipo = envio["desfecho"]
    if tipo == "rejeitado":
        return f"✕ rejeitado (HTTP {envio['status_http']}: {envio['erro']})", False
    if tipo == "nao_enviado":
        return "✕ não enviado (execução interrompida)", False
    if tipo == "erro_transporte":
        return f"✕ erro de transporte ({envio['erro']})", False
    if tipo == "erro_http":
        return f"✕ erro HTTP {envio['status_http']} ({envio['erro']})", False
    if desfecho is None:
        return "✕ aceito, sem desfecho registrado", False
    final = desfecho["desfecho"]
    if final == "failed":
        return f"✕ falhou ({desfecho['erro']})", False
    if final == "sem_conclusao":
        return f"✕ sem conclusão no limite (último status: {desfecho['ultimo_status']})", False
    if final == "erro_download":
        return f"✕ erro ao baixar ({desfecho['erro']})", False
    if not tem_png:
        return "✕ imagem ausente no disco", False
    return "✓ concluída", True


def _num(valor: float | None, casas: int = 3) -> str:
    return "—" if valor is None else f"{valor:.{casas}f}"


def _texto(valor) -> str:
    return "—" if valor is None else html.escape(str(valor))


def _imagem(caminho: Path, sucesso: bool, job_id: str) -> str:
    if not sucesso:
        return '<div class="sem-imagem">sem imagem</div>'
    codificada = base64.b64encode(caminho.read_bytes()).decode("ascii")
    return f'<img alt="Reconstrução {html.escape(job_id)}" src="data:image/png;base64,{codificada}">'


def _linha(pedido: dict, envio: dict | None, desfecho: dict | None, pasta_jobs: Path) -> tuple[str, bool]:
    job_id = pedido["job_id"]
    caminho_png = pasta_jobs / f"{job_id}.png"
    caminho_json = pasta_jobs / f"{job_id}.json"
    situacao, sucesso = _situacao(envio, desfecho, caminho_png.exists())
    metadados = ler_json(caminho_json) if caminho_json.exists() else {}
    celulas = [
        _imagem(caminho_png, sucesso, job_id),
        f'<span class="marca">{html.escape(situacao)}</span>',
        _texto(job_id), _texto(pedido["client_id"]), _texto(pedido["sinal"]), _texto(pedido["modelo"]),
        "sim" if pedido["ganho"] else "não", _texto(pedido["algoritmo"]),
        _texto(metadados.get("received_at")), _texto(metadados.get("started_at")), _texto(metadados.get("finished_at")),
        _num(metadados.get("queue_wait_s")), _num(metadados.get("duration_s")),
        _texto(metadados.get("iterations")), _texto(metadados.get("stop_reason")),
        _num(envio.get("atraso_s") if envio else None),
    ]
    classes = "sucesso" if sucesso else "problema"
    corpo = "".join(f'<td class="situacao">{c}</td>' if i == 1 else f"<td>{c}</td>" for i, c in enumerate(celulas))
    return f'<tr data-job="{html.escape(job_id)}" class="{classes}">{corpo}</tr>', sucesso


def _categoria(envio: dict | None, desfecho: dict | None, sucesso: bool) -> str:
    if sucesso:
        return "concluidas"
    if envio is not None and envio["desfecho"] == "rejeitado":
        return "rejeitadas"
    if desfecho is not None and desfecho["desfecho"] == "failed":
        return "falhas"
    return "outras"


def _configuracao(execucao: dict, carga: dict) -> str:
    return " · ".join(html.escape(str(p)) for p in (
        execucao.get("cliente"),
        execucao.get("implementacao") and f"implementação {execucao['implementacao']}",
        execucao.get("workers") and f"W={execucao['workers']}",
        execucao.get("blas_threads") and f"B={execucao['blas_threads']}",
        f"semente {carga.get('semente')}",
        f"{len(carga['pedidos'])} pedidos",
    ) if p)


def _resumo(contagem: dict[str, int]) -> str:
    return "".join(
        f'<li><strong data-indicador="{chave}">{contagem[chave]}</strong>{rotulo}</li>'
        for chave, rotulo in (
            ("concluidas", "imagens concluídas"), ("rejeitadas", "rejeitadas (503)"),
            ("falhas", "com falha"), ("outras", "outros desfechos")))


def gerar_relatorio(pasta: Path) -> Path:
    carga = ler_json(pasta / "carga.json")
    envios = {e["job_id"]: e for e in ler_jsonl(pasta / "cliente" / "envios.jsonl")[0]}
    desfechos = {d["job_id"]: d for d in ler_jsonl(pasta / "cliente" / "desfechos.jsonl")[0]}
    caminho_execucao = pasta / "execucao.json"
    execucao = ler_json(caminho_execucao) if caminho_execucao.exists() else {}

    contagem = dict.fromkeys(("concluidas", "rejeitadas", "falhas", "outras"), 0)
    linhas = []
    for pedido in carga["pedidos"]:
        envio, desfecho = envios.get(pedido["job_id"]), desfechos.get(pedido["job_id"])
        linha, sucesso = _linha(pedido, envio, desfecho, pasta / "cliente" / "jobs")
        linhas.append(linha)
        contagem[_categoria(envio, desfecho, sucesso)] += 1

    cabecalho = "".join(f"<th>{c}</th>" for c in CABECALHOS)
    documento = (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Relatório do cliente</title><style>{ESTILO}</style></head><body>"
        f'<h1>Relatório do cliente</h1><p class="sub">{_configuracao(execucao, carga)}</p>'
        f'<ul class="resumo">{_resumo(contagem)}</ul>'
        f'<div class="rolagem"><table><thead><tr>{cabecalho}</tr></thead><tbody>{"".join(linhas)}</tbody></table></div>'
        "</body></html>\n"
    )
    destino = pasta / "relatorio_cliente.html"
    destino.write_text(documento, encoding="utf-8")
    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execucao", type=Path, required=True, help="pasta gravada por cliente.instancia")
    args = parser.parse_args(argv)
    print(gerar_relatorio(args.execucao))
    return 0


if __name__ == "__main__":
    sys.exit(main())
