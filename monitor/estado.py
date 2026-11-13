"""Estado da rodada a partir dos eventos, dos JSONs das tarefas e das amostras de fila. Sem E/S."""
from __future__ import annotations

from statistics import mean

from cliente.comum.registros import instante_epoch
from monitor.medicao.indicadores import EVENTOS_CHEGADA, EVENTOS_CONCLUSAO, fila_media_temporal, janela_mono, moda

ESTADO_DO_EVENTO = {"accepted": "fila", "started": "reconstruindo", "finished": "concluido", "failed": "falhou"}
CAMPOS_DO_JSON = {"client_id": "client_id", "signal_id": "signal_id", "model": "model", "algorithm": "algorithm",
                  "gain": "gain", "iterations": "iteracoes", "stop_reason": "parada", "error": "erro"}


def _novo_pedido(evento: dict, estado: str) -> dict:
    return {"job_id": evento["job_id"], "estado": estado, **{campo: None for campo in CAMPOS_DO_JSON.values()},
            "recebido": evento, "inicio": None, "fim": None}


def _pedidos_da_rodada(eventos: list[dict]) -> tuple[list[dict], list[dict]]:
    """Pedidos na ordem de chegada e os eventos que pertencem a eles.

    Tarefa aceita antes do início da rodada não entra: seus `started`/`finished` são da rodada anterior.
    """
    aceitos: dict[str, dict] = {}
    pedidos: list[dict] = []
    da_rodada: list[dict] = []
    for evento in sorted(eventos, key=lambda e: e["t_mono"]):
        tipo, job_id = evento["event"], evento["job_id"]
        if tipo == "rejected":
            pedidos.append({**_novo_pedido(evento, "recusado"), "fim": evento})
        elif tipo == "accepted":
            aceitos[job_id] = _novo_pedido(evento, "fila")
            pedidos.append(aceitos[job_id])
        elif job_id in aceitos:
            pedido = aceitos[job_id]
            pedido["estado"] = ESTADO_DO_EVENTO.get(tipo, pedido["estado"])
            pedido["inicio" if tipo == "started" else "fim"] = evento
        else:
            continue
        da_rodada.append(evento)
    return pedidos, da_rodada


def _diferenca(fim: dict | None, inicio: dict | None) -> float | None:
    return fim["t_mono"] - inicio["t_mono"] if fim and inicio else None


def _completar(pedido: dict, metadados: dict, origem: dict, agora_wall: float) -> dict:
    meta = metadados.get(pedido["job_id"], {})
    for campo_json, campo in CAMPOS_DO_JSON.items():
        pedido[campo] = meta.get(campo_json)
    recebido, inicio, fim = pedido.pop("recebido"), pedido.pop("inicio"), pedido.pop("fim")
    agora_rel = agora_wall - instante_epoch(origem["t_wall"])
    pedido["t_recebido"] = _diferenca(recebido, origem)
    pedido["t_inicio"] = _diferenca(inicio, origem)
    pedido["t_fim"] = _diferenca(fim, origem)

    espera = meta.get("queue_wait_s")
    if espera is None and pedido["estado"] != "recusado":
        # Sem JSON ainda: mede pelos eventos; quem segue na fila conta até agora.
        espera = _diferenca(inicio or fim, recebido) if (inicio or fim) else agora_rel - pedido["t_recebido"]
    reconstrucao = meta.get("duration_s")
    if reconstrucao is None and inicio is not None:
        reconstrucao = _diferenca(fim, inicio) if fim else agora_rel - pedido["t_inicio"]
    if pedido["estado"] == "recusado":
        total = None
    else:
        total = _diferenca(fim, recebido) if fim else agora_rel - pedido["t_recebido"]
    pedido.update(espera_s=espera, reconstrucao_s=reconstrucao, total_s=total)
    return pedido


def _faixas(pedidos: list[dict]) -> list[dict]:
    por_cliente: dict[str | None, list[str]] = {}
    for pedido in pedidos:
        por_cliente.setdefault(pedido["client_id"], []).append(pedido["job_id"])
    ordem = sorted((c for c in por_cliente if c is not None)) + ([None] if None in por_cliente else [])
    return [{"cliente": cliente, "job_ids": por_cliente[cliente]} for cliente in ordem]


def _media(valores: list[float]) -> float | None:
    return mean(valores) if valores else None


def _cartoes(pedidos: list[dict], eventos: list[dict], fila_1s: list[tuple[float, int]],
             agora_wall: float) -> dict:
    contagem = {estado: sum(1 for p in pedidos if p["estado"] == estado)
                for estado in ("fila", "reconstruindo", "concluido", "falhou", "recusado")}
    pendentes = contagem["fila"] + contagem["reconstruindo"]
    janela = janela_mono(eventos)
    concluiu = any(e["event"] in EVENTOS_CONCLUSAO for e in eventos)
    chegadas = [e for e in eventos if e["event"] in EVENTOS_CHEGADA]
    inicio_wall = instante_epoch(chegadas[0]["t_wall"]) if chegadas else None

    if inicio_wall is not None and pendentes:
        tempo_total, fim_wall = agora_wall - inicio_wall, agora_wall
    elif janela and concluiu:
        tempo_total = janela[1] - janela[0]
        fim_wall = inicio_wall + tempo_total if inicio_wall is not None else None
    else:
        tempo_total, fim_wall = None, None

    # Moda sobre amostras de 1 s da primeira chegada à última conclusão, como em monitor/medicao/indicadores.py.
    filas = [q for t, q in fila_1s if inicio_wall is not None and fim_wall is not None and inicio_wall <= t <= fim_wall]
    duracoes = [p["reconstrucao_s"] for p in pedidos if p["estado"] == "concluido" and p["reconstrucao_s"] is not None]
    esperas = [p["espera_s"] for p in pedidos if p["t_inicio"] is not None and p["espera_s"] is not None]
    return {
        "aceitas": sum(1 for p in pedidos if p["estado"] != "recusado"),
        "pendentes": pendentes,
        "concluidas": contagem["concluido"],
        "falhas": contagem["falhou"],
        "recusadas": contagem["recusado"],
        "tempo_total_s": tempo_total,
        "em_andamento": bool(pendentes),
        "imagens_por_s": contagem["concluido"] / tempo_total if tempo_total else None,
        "reconstrucao_media_s": _media(duracoes),
        "espera_media_s": _media(esperas),
        "fila_media": fila_media_temporal(eventos),
        "fila_moda": moda(filas),
        "fila_amostras": len(filas),
    }


def montar_estado(eventos: list[dict], metadados: dict[str, dict], fila_1s: list[tuple[float, int]],
                  agora_wall: float, limite_tabela: int = 20) -> dict:
    """`fila_1s`: pares (epoch, queue_depth) lidos de /metrics uma vez por segundo."""
    pedidos, da_rodada = _pedidos_da_rodada(eventos)
    origem = pedidos[0]["recebido"] if pedidos else None
    pedidos = [_completar(p, metadados, origem, agora_wall) for p in pedidos]
    recentes = sorted(pedidos, key=lambda p: p["t_recebido"], reverse=True)[:limite_tabela]
    return {
        "origem_wall": instante_epoch(origem["t_wall"]) if origem else None,
        "agora_rel": agora_wall - instante_epoch(origem["t_wall"]) if origem else None,
        "cartoes": _cartoes(pedidos, da_rodada, fila_1s, agora_wall),
        "pedidos": pedidos,
        "faixas": _faixas(pedidos),
        "tabela": [p["job_id"] for p in recentes],
    }
