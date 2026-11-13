from __future__ import annotations

import httpx

TEMPO_MAXIMO_S = 1.5


class ConsultaServidor:
    def __init__(self, url: str) -> None:
        self.url = url
        self.ultimo_erro: str | None = None
        self._http = httpx.Client(base_url=url, timeout=TEMPO_MAXIMO_S, trust_env=False)

    def _get(self, caminho: str) -> dict | None:
        try:
            resposta = self._http.get(caminho)
        except httpx.HTTPError as erro:
            self.ultimo_erro = f"{type(erro).__name__}: {erro}"
            return None
        if resposta.status_code != 200:
            self.ultimo_erro = f"{caminho}: HTTP {resposta.status_code}"
            return None
        try:
            return resposta.json()
        except ValueError:
            self.ultimo_erro = f"{caminho}: resposta não é JSON"
            return None

    def metrics(self) -> dict | None:
        corpo = self._get("/metrics")
        if corpo is not None:
            self.ultimo_erro = None
        return corpo

    def info(self) -> dict | None:
        return self._get("/info")

    def tarefa(self, job_id: str) -> dict | None:
        return self._get(f"/jobs/{job_id}")

    def fechar(self) -> None:
        self._http.close()
