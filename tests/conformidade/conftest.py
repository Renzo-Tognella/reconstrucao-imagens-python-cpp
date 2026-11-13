from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

RAIZ = Path(__file__).resolve().parents[2]
IMPLS = os.environ.get("IMPLS", "python,cpp").split(",")


def comando(impl: str) -> list[str]:
    if impl == "python":
        return [sys.executable, "-m", "recon_py.servidor"]
    binario = RAIZ / "build" / "servidor_cpp"
    if not binario.exists():
        pytest.fail(f"{binario} não existe: compilar antes (ver README)")
    return [str(binario)]


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Servidor:
    def __init__(self, impl: str, saida: Path, **opcoes):
        self.impl = impl
        self.saida = saida
        self.porta = porta_livre()
        args = comando(impl) + [
            "--porta", str(self.porta), "--dados", str(RAIZ / "dados"), "--saida", str(saida),
        ]
        for nome, valor in opcoes.items():
            args += ["--" + nome.replace("_", "-"), str(valor)]
        self.processo = subprocess.Popen(args, cwd=RAIZ)
        self.http = httpx.Client(base_url=f"http://127.0.0.1:{self.porta}", timeout=30)
        limite = time.monotonic() + 20
        while True:
            try:
                self.http.get("/info").raise_for_status()
                return
            except httpx.TransportError:
                if self.processo.poll() is not None or time.monotonic() > limite:
                    self.encerrar()
                    pytest.fail(f"servidor {impl} não subiu")
                time.sleep(0.1)

    def enviar(self, job_id, corpo, *, client_id="c1", signal_id="g1", model="30x30", algorithm="cgnr", gain="0"):
        params = dict(job_id=job_id, client_id=client_id, signal_id=signal_id, model=model, algorithm=algorithm, gain=gain)
        return self.http.post("/jobs", params=params, content=corpo, headers={"content-type": "application/octet-stream"})

    def aguardar(self, job_id, limite_s=60):
        fim = time.monotonic() + limite_s
        while time.monotonic() < fim:
            corpo = self.http.get(f"/jobs/{job_id}").json()
            if corpo["status"] in ("done", "failed"):
                return corpo
            time.sleep(0.05)
        pytest.fail(f"{job_id} não terminou em {limite_s}s")

    def encerrar(self):
        self.http.close()
        if self.processo.poll() is None:
            self.processo.send_signal(signal.SIGTERM)
            try:
                self.processo.wait(15)
            except subprocess.TimeoutExpired:
                self.processo.kill()
                pytest.fail(f"servidor {self.impl} não encerrou com SIGTERM")


@pytest.fixture(params=IMPLS, scope="module")
def impl(request):
    return request.param


@pytest.fixture(scope="module")
def servidor(impl, tmp_path_factory):
    instancia = Servidor(impl, tmp_path_factory.mktemp(f"saida-{impl}"), workers=2)
    yield instancia
    instancia.encerrar()


@pytest.fixture
def novo_servidor(impl, tmp_path):
    criados = []

    def criar(**opcoes):
        instancia = Servidor(impl, tmp_path / f"s{len(criados)}", **opcoes)
        criados.append(instancia)
        return instancia

    yield criar
    for instancia in criados:
        instancia.encerrar()
