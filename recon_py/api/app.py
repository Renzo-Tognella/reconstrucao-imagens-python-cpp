from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from recon_py.api.erros import registrar_tratadores_de_erro
from recon_py.api.rotas import baixar_resultado, consultar_pedido, enviar_sinal, metricas
from recon_py.api.rotas.metricas import DescricaoServidor
from recon_py.aplicacao.fila.fila import Fila
from recon_py.dominio.modelo import Modelo


def criar_app(fila: Fila, modelos: dict[str, Modelo], descricao: DescricaoServidor) -> FastAPI:
    @asynccontextmanager
    async def ciclo_de_vida(_: FastAPI):
        fila.iniciar()
        yield
        fila.encerrar()

    app = FastAPI(lifespan=ciclo_de_vida, docs_url=None, redoc_url=None, openapi_url=None)
    registrar_tratadores_de_erro(app)
    app.include_router(enviar_sinal.criar_rota(fila, modelos))
    app.include_router(consultar_pedido.criar_rota(fila))
    app.include_router(baixar_resultado.criar_rota(fila))
    app.include_router(metricas.criar_rota(fila, modelos, descricao))
    return app
