"""Formato `{"error", "detail"}` de toda resposta de erro, inclusive rota inexistente e falha interna."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

CODIGOS_DE_STATUS = {404: "not_found"}


class ErroHttp(Exception):
    def __init__(self, status: int, codigo: str, detalhe: str) -> None:
        super().__init__(detalhe)
        self.status = status
        self.codigo = codigo
        self.detalhe = detalhe


def resposta_de_erro(status: int, codigo: str, detalhe: str) -> JSONResponse:
    return JSONResponse({"error": codigo, "detail": detalhe}, status_code=status)


def registrar_tratadores_de_erro(app: FastAPI) -> None:
    @app.exception_handler(ErroHttp)
    async def tratar_erro_http(_: Request, erro: ErroHttp) -> JSONResponse:
        return resposta_de_erro(erro.status, erro.codigo, erro.detalhe)

    @app.exception_handler(StarletteHTTPException)
    async def tratar_erro_de_rota(_: Request, erro: StarletteHTTPException) -> JSONResponse:
        codigo = CODIGOS_DE_STATUS.get(erro.status_code, "http_error")
        return resposta_de_erro(erro.status_code, codigo, str(erro.detail))

    @app.exception_handler(Exception)
    async def tratar_erro_inesperado(_: Request, __: Exception) -> JSONResponse:
        return resposta_de_erro(500, "internal_error", "erro interno do servidor")
