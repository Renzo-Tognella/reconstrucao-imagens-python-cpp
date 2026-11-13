from __future__ import annotations

import signal
import subprocess
import sys
import time

import httpx
import pytest

from tests.conformidade.conftest import RAIZ, Servidor, porta_livre

SINAL = RAIZ / "dados" / "sinais" / "30x30" / "g1.f64"


@pytest.fixture
def servidor(tmp_path):
    if not SINAL.exists():
        pytest.fail(f"{SINAL} não existe: preparar os dados antes (ver README)")
    instancia = Servidor("python", tmp_path / "saida", workers=1)
    yield instancia
    instancia.encerrar()


@pytest.fixture
def monitor(servidor):
    porta = porta_livre()
    processo = subprocess.Popen(
        [sys.executable, "-m", "monitor", "--servidor", f"http://127.0.0.1:{servidor.porta}",
         "--saida", str(servidor.saida), "--porta", str(porta)],
        cwd=RAIZ,
    )
    http = httpx.Client(base_url=f"http://127.0.0.1:{porta}", timeout=5, trust_env=False)
    limite = time.monotonic() + 20
    while True:
        try:
            http.get("/api/estado").raise_for_status()
            break
        except httpx.TransportError:
            if processo.poll() is not None or time.monotonic() > limite:
                processo.kill()
                pytest.fail("monitor não subiu")
            time.sleep(0.1)
    yield processo, http
    http.close()
    if processo.poll() is None:
        processo.kill()
        processo.wait(5)


def _esperar(http: httpx.Client, condicao, limite_s: float = 60) -> dict:
    fim = time.monotonic() + limite_s
    while time.monotonic() < fim:
        estado = http.get("/api/estado").json()
        if condicao(estado):
            return estado
        time.sleep(0.25)
    pytest.fail(f"condição não atingida em {limite_s}s; último estado: {estado.get('cartoes')}")


def test_monitor_mostra_os_tres_clientes(servidor, monitor):
    processo, http = monitor
    corpo = SINAL.read_bytes()
    for cliente in ("c1", "c2", "c3"):
        resposta = servidor.enviar(f"{cliente}-0001", corpo, client_id=cliente)
        assert resposta.status_code == 202, resposta.text

    estado = _esperar(http, lambda e: e.get("cartoes", {}).get("concluidas") == 3)

    assert [f["cliente"] for f in estado["faixas"]] == ["c1", "c2", "c3"]
    assert estado["info"]["implementation"] == "python"
    assert estado["conexao"]["estado"] == "conectado"
    assert estado["processo"]["pid"] == servidor.processo.pid
    cartoes = estado["cartoes"]
    assert cartoes["recusadas"] == 0 and cartoes["falhas"] == 0
    assert cartoes["tempo_total_s"] > 0 and cartoes["imagens_por_s"] > 0
    for pedido in estado["pedidos"]:
        assert pedido["signal_id"] == "g1" and pedido["model"] == "30x30"
        assert pedido["iteracoes"] >= 1
        assert pedido["total_s"] == pytest.approx(pedido["espera_s"] + pedido["reconstrucao_s"], abs=0.05)

    http.post("/api/nova-rodada").raise_for_status()
    estado = _esperar(http, lambda e: e["rodada"]["numero"] >= 2 and not e["pedidos"], limite_s=5)
    assert estado["cartoes"]["concluidas"] == 0
    assert list((servidor.saida / "jobs").glob("*.json")), "nova rodada não pode apagar arquivos"

    processo.send_signal(signal.SIGINT)
    assert processo.wait(10) == 0
