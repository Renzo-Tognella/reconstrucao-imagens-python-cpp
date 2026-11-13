"""Saída no terminal da demonstração: tabela de envios, tabela de imagens prontas e resumo final."""
from __future__ import annotations

import statistics
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

ESTILOS = {"negrito": "1", "fraco": "2", "vermelho": "31", "verde": "32", "amarelo": "33", "ciano": "36"}
NOMES_SERVIDOR = {"python": "Python", "cpp": "C++"}
PARADAS = {"tolerance": "convergiu", "max_iterations": "limite"}

# (título, largura, alinhado à direita)
COLUNAS_ENVIO = (("hora", 8, False), ("pedido", 6, True), ("saiu aos", 8, True), ("sinal", 5, False),
                 ("modelo", 6, False), ("algoritmo", 9, False), ("ganho", 5, False), ("resposta", 18, False),
                 ("envio", 8, True))
COLUNAS_IMAGEM = (("hora", 8, False), ("pedido", 6, True), ("espera na fila", 14, True),
                  ("reconstrução", 12, True), ("iterações", 15, False))


class Pintor:
    def __init__(self, ligado: bool):
        self.ligado = ligado

    def __call__(self, texto: str, *estilos: str) -> str:
        if not self.ligado or not estilos:
            return texto
        return f"\x1b[{';'.join(ESTILOS[e] for e in estilos)}m{texto}\x1b[0m"


def cor_ativa(modo: str, fluxo: TextIO, ambiente: Mapping[str, str]) -> bool:
    if modo != "auto":
        return modo == "sim"
    eh_terminal = hasattr(fluxo, "isatty") and fluxo.isatty()
    return eh_terminal and "NO_COLOR" not in ambiente and ambiente.get("TERM", "") != "dumb"


def hora(instante: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(instante))


def numero(valor: float, casas: int) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def segundos(valor: float | None, casas: int = 3) -> str:
    return "—" if valor is None else f"{numero(valor, casas)} s"


def nome_servidor(implementacao: str | None) -> str:
    return NOMES_SERVIDOR.get(implementacao or "", implementacao or "desconhecido")


def _linha(colunas: Sequence[tuple[str, int, bool]], valores: Sequence[tuple[str, tuple[str, ...]]],
           pintar: Pintor) -> str:
    # Alinha antes de pintar: os códigos de cor contam caracteres e desalinhariam as colunas.
    partes = []
    for (_, largura, direita), (texto, estilos) in zip(colunas, valores):
        alinhado = texto.rjust(largura) if direita else texto.ljust(largura)
        partes.append(pintar(alinhado, *estilos))
    return ("  " + "  ".join(partes)).rstrip()


def cabecalho_tabela(colunas: Sequence[tuple[str, int, bool]], pintar: Pintor) -> str:
    return _linha(colunas, [(titulo, ("fraco",)) for titulo, _, _ in colunas], pintar)


def _resposta(registro: dict) -> tuple[str, tuple[str, ...]]:
    status = registro["status_http"]
    if registro["desfecho"] == "nao_enviado":
        return "não enviado", ("amarelo",)
    if status is None:
        return f"sem resposta ({registro['erro']})", ("vermelho",)
    if status == 202:
        return "aceito (202)", ("verde",)
    if status == 200:
        return "já recebido (200)", ("verde",)
    if status == 503:
        return "fila cheia (503)", ("vermelho",)
    return f"{registro['erro'] or 'recusado'} ({status})", ("vermelho",)


def linha_envio(pedido: dict, registro: dict, rotulo: str, pintar: Pintor) -> str:
    enviado = registro["desfecho"] != "nao_enviado"
    instante = registro["t_envio_wall"] if enviado else time.time()
    duracao = registro.get("duracao_post_s")
    valores = [
        (hora(instante), ()), (rotulo, ()),
        (segundos(registro["efetivo_s"], 1) if enviado else "—", ()),
        (pedido["sinal"], ()), (pedido["modelo"], ()), (pedido["algoritmo"].upper(), ()),
        ("sim" if pedido["ganho"] else "não", ()), _resposta(registro),
        (f"{numero(duracao * 1000, 1)} ms" if enviado and duracao is not None else "—", ()),
    ]
    return _linha(COLUNAS_ENVIO, valores, pintar)


def _iteracoes(job: dict) -> str:
    parada = PARADAS.get(job.get("stop_reason"), job.get("stop_reason") or "")
    return f"{job.get('iterations')} ({parada})" if parada else str(job.get("iterations"))


def linha_desfecho(instante: float, rotulo: str, desfecho: str, job: dict | None, erro: str | None,
                   pintar: Pintor) -> str:
    job = job or {}
    if desfecho == "done":
        fim = (_iteracoes(job), ())
    elif desfecho == "failed":
        fim = (f"falhou: {erro}", ("vermelho", "negrito"))
    elif desfecho == "erro_download":
        fim = (f"erro ao baixar: {erro}", ("vermelho", "negrito"))
    else:
        fim = ("não terminou no limite de espera", ("amarelo", "negrito"))
    estilo_tempo = ("verde",) if desfecho == "done" else ()
    valores = [(hora(instante), ()), (rotulo, ()), (segundos(job.get("queue_wait_s")), ()),
               (segundos(job.get("duration_s")), estilo_tempo), fim]
    return _linha(COLUNAS_IMAGEM, valores, pintar)


def linha_progresso(instante: float, rodada: int, estado: Mapping[str, int], total: int, pintar: Pintor) -> str:
    partes = [f"{estado['prontas']} de {total} prontas"]
    if estado.get("na_fila"):
        partes.append(f"{estado['na_fila']} na fila")
    if estado.get("reconstruindo"):
        partes.append(f"{estado['reconstruindo']} reconstruindo")
    if estado.get("falhas"):
        partes.append(pintar(f"{estado['falhas']} com falha", "vermelho"))
    if estado.get("sem_resposta"):
        partes.append(pintar(f"{estado['sem_resposta']} sem resposta", "amarelo"))
    return f"  {hora(instante)}  " + pintar(f"consulta {rodada}: " + ", ".join(partes), "fraco")


def linhas_resumo(cliente: str, resumo: dict, jobs_prontos: list[dict], relatorio: Path | None,
                  pintar: Pintor) -> list[str]:
    linhas = [("Imagens prontas", f"{resumo['concluidos']} de {resumo['pedidos']}"),
              ("Recusadas pelo servidor", str(resumo["rejeitados"] + resumo["erros_http"]))]
    for chave, rotulo in (("falhas", "Com falha"), ("sem_conclusao", "Sem conclusão"),
                          ("erros_download", "Erro ao baixar"), ("erros_transporte", "Sem resposta ao envio"),
                          ("nao_enviados", "Não enviadas")):
        if resumo[chave]:
            linhas.append((rotulo, str(resumo[chave])))
    linhas.append(("Tempo do cliente", segundos(resumo["fim_wall"] - resumo["t0_wall"], 2)))
    filas = [j["queue_wait_s"] for j in jobs_prontos if j.get("queue_wait_s") is not None]
    duracoes = [j["duration_s"] for j in jobs_prontos if j.get("duration_s") is not None]
    if filas and duracoes:
        fila, reconstrucao = statistics.fmean(filas), statistics.fmean(duracoes)
        linhas.append(("Média por imagem", f"{segundos(fila + reconstrucao)} "
                                           f"({segundos(fila)} na fila + {segundos(reconstrucao)} reconstruindo)"))
    if relatorio is not None:
        linhas.append(("Relatório", str(relatorio)))
    largura = max(len(rotulo) for rotulo, _ in linhas)
    return ["", pintar(f"RESUMO DO CLIENTE {int(cliente.rsplit('-', 1)[1])}", "negrito")] + [
        f"  {rotulo.ljust(largura)}  {valor}" for rotulo, valor in linhas]


def rotulos_dos_pedidos(pedidos: Sequence[dict]) -> dict[str, str]:
    total = len(pedidos)
    return {p["job_id"]: f"{i}/{total}" for i, p in enumerate(pedidos, start=1)}


class Terminal:
    """Observador da carga: uma linha por evento, já descarregada, para o professor acompanhar ao vivo."""

    def __init__(self, fluxo: TextIO, pintar: Pintor, pedidos: Sequence[dict] = (), intervalo_consulta_s: float = 1.0):
        self.fluxo, self.pintar = fluxo, pintar
        self.rotulos = rotulos_dos_pedidos(pedidos)
        self.intervalo_consulta_s = intervalo_consulta_s
        self.prontos: list[dict] = []
        self.falhas = 0
        self.envios_vistos = 0

    def escrever(self, linha: str) -> None:
        print(linha, file=self.fluxo, flush=True)

    def _rotulo(self, job_id: str) -> str:
        return self.rotulos.get(job_id, job_id)

    def abrir_envios(self) -> None:
        self.escrever("")
        self.escrever(self.pintar("ENVIOS", "negrito", "ciano"))
        self.escrever(cabecalho_tabela(COLUNAS_ENVIO, self.pintar))

    def _abrir_imagens(self) -> None:
        total = len(self.rotulos) or self.envios_vistos
        self.escrever("")
        self.escrever(f"Os {total} envios terminaram. Agora o cliente pergunta ao servidor a cada "
                      f"{numero(self.intervalo_consulta_s, 1)} s se as imagens ficaram prontas.")
        self.escrever("")
        self.escrever(self.pintar("IMAGENS", "negrito", "verde"))
        self.escrever(cabecalho_tabela(COLUNAS_IMAGEM, self.pintar))

    def envio(self, pedido: dict, registro: dict) -> None:
        self.escrever(linha_envio(pedido, registro, self._rotulo(pedido["job_id"]), self.pintar))
        self.envios_vistos += 1
        if self.envios_vistos == len(self.rotulos):
            self._abrir_imagens()

    def desfecho(self, job_id: str, desfecho: str, job: dict | None, erro: str | None) -> None:
        if desfecho == "done":
            self.prontos.append(job)
        elif desfecho == "failed":
            self.falhas += 1
        self.escrever(linha_desfecho(time.time(), self._rotulo(job_id), desfecho, job, erro, self.pintar))

    def rodada(self, numero_rodada: int, ultimos: dict[str, str | None], pendentes: list[str]) -> None:
        estados = [ultimos.get(j) for j in pendentes]
        estado = {"prontas": len(self.prontos), "falhas": self.falhas, "na_fila": estados.count("queued"),
                  "reconstruindo": estados.count("running"),
                  "sem_resposta": sum(e not in ("queued", "running") for e in estados)}
        self.escrever(linha_progresso(time.time(), numero_rodada, estado, len(ultimos), self.pintar))
