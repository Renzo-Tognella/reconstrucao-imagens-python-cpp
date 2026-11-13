"""Dispara a carga salva: um Task por cliente, agenda aberta por tempos absolutos, sem retry de envio."""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import httpx
from PIL import Image, UnidentifiedImageError

from cliente.carga.sinais import corpo_do_pedido, crc32_hex
from cliente.comum.caminhos import DADOS_PADRAO
from cliente.comum.registros import ler_json

MARGEM_INICIO_S = 0.2
LADO_MINIMO_PNG = 240
DESFECHOS_ENVIO = {202: "aceito", 200: "reenvio", 503: "rejeitado"}


class Observador(Protocol):
    """Recebe cada evento já registrado em disco; usado para mostrar o andamento no terminal."""

    def envio(self, pedido: dict, registro: dict) -> None: ...

    def desfecho(self, job_id: str, desfecho: str, job: dict | None, erro: str | None) -> None: ...

    def rodada(self, numero: int, ultimos: dict[str, str | None], pendentes: list[str]) -> None: ...


class CargaInvalida(Exception):
    """A carga salva não corresponde aos dados locais; enviar invalidaria a comparação."""


def preparar_corpos(carga: dict, dados: Path) -> dict[str, bytes]:
    """Monta tudo antes do instante comum, para o ganho não atrapalhar a agenda. Corpos iguais são o mesmo objeto."""
    por_combinacao: dict[tuple, bytes] = {}
    corpos = {}
    for pedido in carga["pedidos"]:
        chave = (pedido["modelo"], pedido["sinal"], pedido["ganho"])
        if chave not in por_combinacao:
            por_combinacao[chave] = corpo_do_pedido(dados, pedido)
        corpo = por_combinacao[chave]
        if crc32_hex(corpo) != pedido["crc32"]:
            raise CargaInvalida(f"{pedido['job_id']}: corpo com CRC diferente do arquivo de carga")
        corpos[pedido["job_id"]] = corpo
    return corpos


def _codigo_erro(resposta: httpx.Response) -> str | None:
    if resposta.status_code < 400:
        return None
    try:
        return resposta.json().get("error")
    except ValueError:
        return f"http_{resposta.status_code}"


def pgm_para_png(pgm: bytes, destino: Path) -> None:
    with Image.open(io.BytesIO(pgm)) as imagem:
        escala = max(1, LADO_MINIMO_PNG // max(imagem.size))
        ampliada = imagem.resize((imagem.width * escala, imagem.height * escala), Image.Resampling.NEAREST)
        ampliada.save(destino, format="PNG")


class _Registro:
    """Linhas gravadas e descarregadas uma a uma: uma queda não apaga o que já aconteceu."""

    def __init__(self, caminho: Path):
        self.arquivo = caminho.open("w", encoding="utf-8")

    def gravar(self, linha: dict) -> None:
        self.arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")
        self.arquivo.flush()

    def fechar(self) -> None:
        self.arquivo.close()


class _Execucao:
    def __init__(self, carga: dict, http: httpx.AsyncClient, corpos: dict[str, bytes], saida: Path,
                 limite_s: float, intervalo_consulta_s: float, observador: Observador | None = None):
        self.carga, self.http, self.corpos, self.saida = carga, http, corpos, saida
        self.limite_s, self.intervalo_consulta_s = limite_s, intervalo_consulta_s
        self.observador = observador
        self.pasta_jobs = saida / "jobs"
        self.envios = _Registro(saida / "envios.jsonl")
        self.desfechos = _Registro(saida / "desfechos.jsonl")
        self.parar = asyncio.Event()
        self.aceitos: list[dict] = []
        self.contagem_envios: Counter = Counter()
        self.contagem_desfechos: Counter = Counter()
        self.t0_loop = 0.0
        self.t0_wall = 0.0

    def _registrar_envio(self, pedido: dict, **campos) -> None:
        linha = {"job_id": pedido["job_id"], "client_id": pedido["client_id"],
                 "planejado_s": pedido["instante_planejado_s"], "efetivo_s": None, "atraso_s": None,
                 "t_envio_wall": None, "duracao_post_s": None, "status_http": None, "erro": None, **campos}
        self.contagem_envios[linha["desfecho"]] += 1
        self.envios.gravar(linha)
        if self.observador:
            self.observador.envio(pedido, linha)

    async def _enviar(self, pedido: dict) -> None:
        efetivo = asyncio.get_running_loop().time() - self.t0_loop
        t_wall = time.time()
        inicio = time.perf_counter()
        status, erro = None, None
        try:
            resposta = await self.http.post(
                "/jobs", content=self.corpos[pedido["job_id"]],
                headers={"content-type": "application/octet-stream"},
                params={"job_id": pedido["job_id"], "client_id": pedido["client_id"], "signal_id": pedido["sinal"],
                        "model": pedido["modelo"], "algorithm": pedido["algoritmo"],
                        "gain": "1" if pedido["ganho"] else "0"})
            status, erro = resposta.status_code, _codigo_erro(resposta)
            desfecho = DESFECHOS_ENVIO.get(status, "erro_http")
        except httpx.TransportError as falha:
            desfecho, erro = "erro_transporte", type(falha).__name__
        if desfecho in ("aceito", "reenvio"):
            self.aceitos.append(pedido)
        self._registrar_envio(pedido, efetivo_s=efetivo, atraso_s=efetivo - pedido["instante_planejado_s"],
                              t_envio_wall=t_wall, duracao_post_s=time.perf_counter() - inicio,
                              status_http=status, desfecho=desfecho, erro=erro)

    async def _cliente(self, pedidos: list[dict]) -> None:
        # Cada envio é uma tarefa própria: um POST lento não pode empurrar a agenda dos seguintes,
        # senão a saturação do servidor reduziria a carga oferecida e sumiria das medidas.
        laco = asyncio.get_running_loop()
        async with asyncio.TaskGroup() as envios:
            for pedido in pedidos:
                espera = self.t0_loop + pedido["instante_planejado_s"] - laco.time()
                if espera > 0:
                    try:
                        await asyncio.wait_for(self.parar.wait(), espera)
                    except TimeoutError:
                        pass
                if self.parar.is_set():
                    self._registrar_envio(pedido, desfecho="nao_enviado")
                    continue
                envios.create_task(self._enviar(pedido))

    async def enviar_todos(self) -> None:
        por_cliente: dict[str, list[dict]] = {}
        for pedido in self.carga["pedidos"]:
            por_cliente.setdefault(pedido["client_id"], []).append(pedido)
        self.t0_loop = asyncio.get_running_loop().time() + MARGEM_INICIO_S
        self.t0_wall = time.time() + MARGEM_INICIO_S
        async with asyncio.TaskGroup() as clientes:
            for pedidos in por_cliente.values():
                pedidos.sort(key=lambda p: p["instante_planejado_s"])
                clientes.create_task(self._cliente(pedidos))

    async def _baixar(self, job: dict) -> str | None:
        """Devolve a descrição do problema, ou None se imagem e vetor ficaram em disco."""
        job_id = job["job_id"]
        modelo = self.carga["modelos"].get(job["model"], {})
        try:
            imagem = await self.http.get(f"/jobs/{job_id}/image")
            vetor = await self.http.get(f"/jobs/{job_id}/vector")
        except httpx.TransportError as falha:
            return type(falha).__name__
        if imagem.status_code != 200 or vetor.status_code != 200:
            return f"imagem HTTP {imagem.status_code}, vetor HTTP {vetor.status_code}"
        if modelo and len(vetor.content) != 8 * modelo["colunas"]:
            return f"vetor com {len(vetor.content)} bytes"
        (self.pasta_jobs / f"{job_id}.pgm").write_bytes(imagem.content)
        (self.pasta_jobs / f"{job_id}.f64").write_bytes(vetor.content)
        try:
            pgm_para_png(imagem.content, self.pasta_jobs / f"{job_id}.png")
        except (UnidentifiedImageError, OSError) as falha:
            return f"PGM inválido: {falha}"
        return None

    def _concluir(self, job_id: str, desfecho: str, ultimo_status: str | None, erro: str | None,
                  job: dict | None = None) -> None:
        self.contagem_desfechos[desfecho] += 1
        self.desfechos.gravar({"job_id": job_id, "desfecho": desfecho, "ultimo_status": ultimo_status, "erro": erro})
        if self.observador:
            self.observador.desfecho(job_id, desfecho, job, erro)

    async def _consultar(self, job_id: str, ultimos: dict[str, str | None]) -> bool:
        """Devolve True quando a tarefa terminou. Erro de consulta é transitório até o limite."""
        try:
            resposta = await self.http.get(f"/jobs/{job_id}")
        except httpx.TransportError:
            return False
        if resposta.status_code != 200:
            return False
        job = resposta.json()
        ultimos[job_id] = job["status"]
        if job["status"] not in ("done", "failed"):
            return False
        (self.pasta_jobs / f"{job_id}.json").write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        if job["status"] == "failed":
            self._concluir(job_id, "failed", "failed", job.get("error"), job)
            return True
        problema = await self._baixar(job)
        self._concluir(job_id, "erro_download" if problema else "done", "done", problema, job)
        return True

    async def acompanhar(self) -> None:
        laco = asyncio.get_running_loop()
        pendentes = [p["job_id"] for p in self.aceitos]
        ultimos: dict[str, str | None] = dict.fromkeys(pendentes)
        inicio = laco.time()
        limite = inicio + self.limite_s
        rodada = 0
        while pendentes and not self.parar.is_set():
            # Consultas em série: o custo do cliente sobre o servidor não depende de quantas tarefas restam em paralelo.
            pendentes = [j for j in pendentes if not await self._consultar(j, ultimos)]
            rodada += 1
            if self.observador:
                self.observador.rodada(rodada, ultimos, pendentes)
            if not pendentes or laco.time() >= limite:
                break
            proxima = min(inicio + rodada * self.intervalo_consulta_s, limite)
            try:
                await asyncio.wait_for(self.parar.wait(), max(0.0, proxima - laco.time()))
            except TimeoutError:
                pass
        for job_id in pendentes:
            self._concluir(job_id, "sem_conclusao", ultimos.get(job_id), None)

    def fechar(self) -> None:
        self.envios.fechar()
        self.desfechos.fechar()


async def _vigiar(execucao: _Execucao, vigia: Callable[[], str | None], intervalo_s: float, motivo: list[str]) -> None:
    while not execucao.parar.is_set():
        # Vigia quebrado interrompe: seguir sem ele tiraria a proteção da máquina em silêncio.
        try:
            # Em outra thread: o vigia lê disco e sistema, e a agenda de envios não pode esperar por isso.
            resultado = await asyncio.to_thread(vigia)
        except Exception as falha:
            resultado = f"vigia falhou: {falha}"
        if resultado:
            motivo.append(resultado)
            execucao.parar.set()
            return
        await asyncio.sleep(intervalo_s)


def _resumo(execucao: _Execucao, url: str, fim_envios_wall: float, interrompido: str | None) -> dict:
    return {
        "url": url,
        "t0_wall": execucao.t0_wall,
        "fim_envios_wall": fim_envios_wall,
        "fim_wall": time.time(),
        "pedidos": len(execucao.carga["pedidos"]),
        "aceitos": len(execucao.aceitos),
        "rejeitados": execucao.contagem_envios["rejeitado"],
        "erros_transporte": execucao.contagem_envios["erro_transporte"],
        "erros_http": execucao.contagem_envios["erro_http"],
        "nao_enviados": execucao.contagem_envios["nao_enviado"],
        "concluidos": execucao.contagem_desfechos["done"],
        "falhas": execucao.contagem_desfechos["failed"],
        "sem_conclusao": execucao.contagem_desfechos["sem_conclusao"],
        "erros_download": execucao.contagem_desfechos["erro_download"],
        "interrompido": interrompido,
    }


async def executar_carga(carga: dict, *, url: str, dados: Path, saida: Path, limite_s: float = 600.0,
                         intervalo_consulta_s: float = 1.0, vigia: Callable[[], str | None] | None = None,
                         intervalo_vigia_s: float = 1.0, observador: Observador | None = None) -> dict:
    """`limite_s` conta a partir do fim dos envios. `vigia`, se devolver um motivo, interrompe envios e consultas."""
    corpos = preparar_corpos(carga, dados)
    (saida / "jobs").mkdir(parents=True, exist_ok=True)
    # Sem keep-alive e sem proxy do ambiente: conecta, envia, fecha.
    limites = httpx.Limits(max_keepalive_connections=0, max_connections=None)
    tempos = httpx.Timeout(30.0, connect=5.0)
    motivo: list[str] = []
    async with httpx.AsyncClient(base_url=url, limits=limites, timeout=tempos, trust_env=False,
                                 headers={"Connection": "close"}) as http:
        execucao = _Execucao(carga, http, corpos, saida, limite_s, intervalo_consulta_s, observador)
        monitor = asyncio.create_task(_vigiar(execucao, vigia, intervalo_vigia_s, motivo)) if vigia else None
        try:
            await execucao.enviar_todos()
            fim_envios_wall = time.time()
            await execucao.acompanhar()
        finally:
            if monitor:
                monitor.cancel()
            execucao.fechar()
    resumo = _resumo(execucao, url, fim_envios_wall, motivo[0] if motivo else None)
    (saida / "resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    return resumo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--carga", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--dados", type=Path, default=DADOS_PADRAO)
    parser.add_argument("--limite-s", type=float, default=600.0, help="espera máxima depois do último envio")
    args = parser.parse_args(argv)
    carga = ler_json(args.carga)
    resumo = asyncio.run(executar_carga(carga, url=args.url, dados=args.dados, saida=args.saida, limite_s=args.limite_s))
    print(json.dumps(resumo, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
