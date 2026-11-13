"""Servidor HTTP do monitor: a página e o estado em JSON."""
from __future__ import annotations

import math
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from monitor.coleta.coletor import Coletor

PAGINA = Path(__file__).with_name("pagina.html")


def _sem_nao_finitos(valor):
    # JSON não tem NaN nem infinito; o navegador recusaria a resposta inteira.
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    if isinstance(valor, dict):
        return {k: _sem_nao_finitos(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_sem_nao_finitos(v) for v in valor]
    return valor


def criar_app(coletor: Coletor) -> FastAPI:
    @asynccontextmanager
    async def ciclo_de_vida(_app: FastAPI):
        coletor.iniciar()
        try:
            yield
        finally:
            coletor.parar()

    app = FastAPI(title="Monitor de reconstrução", lifespan=ciclo_de_vida, docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def pagina() -> HTMLResponse:
        return HTMLResponse(PAGINA.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})

    @app.get("/api/estado")
    def estado() -> JSONResponse:
        return JSONResponse(_sem_nao_finitos(coletor.retrato), headers={"Cache-Control": "no-store"})

    @app.post("/api/nova-rodada")
    def nova_rodada() -> dict:
        coletor.nova_rodada()
        return {"ok": True}

    return app
