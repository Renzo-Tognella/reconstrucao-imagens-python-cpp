from __future__ import annotations

import json
import re
import subprocess
import uuid

import numpy as np
import pytest

from tests import referencia as ref
from tests.conformidade.conftest import RAIZ, comando

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


@pytest.fixture(scope="module")
def dados():
    modelo, H = ref.carregar_modelo()
    return modelo, H, ref.carregar_sinal("g1")


def novo_id():
    return uuid.uuid4().hex


@pytest.mark.parametrize("algoritmo,funcao", [("cgnr", ref.cgnr), ("cgne", ref.cgne)])
@pytest.mark.parametrize("com_ganho", [False, True])
def test_reconstrucao_coincide_com_referencia(servidor, dados, algoritmo, funcao, com_ganho):
    modelo, H, g = dados
    sinal = ref.ganho(g, modelo["S"], modelo["N"]) if com_ganho else g
    job = novo_id()
    resposta = servidor.enviar(job, sinal.tobytes(), algorithm=algoritmo, gain=str(int(com_ganho)))
    assert resposta.status_code == 202
    assert resposta.json() == {"job_id": job, "status": "queued"}

    final = servidor.aguardar(job)
    esperado, normas, iteracoes, motivo = funcao(H, sinal)
    assert final["status"] == "done"
    assert final["iterations"] == iteracoes
    assert final["stop_reason"] == motivo
    assert final["residual_norms"] == pytest.approx(normas, rel=1e-8)

    vetor = servidor.http.get(f"/jobs/{job}/vector")
    assert vetor.status_code == 200
    obtido = np.frombuffer(vetor.content, dtype="<f8")
    np.testing.assert_allclose(obtido, esperado, rtol=1e-7, atol=1e-12)


def test_g1_sem_ganho_para_por_tolerancia_na_iteracao_2(servidor, dados):
    _, _, g = dados
    job = novo_id()
    servidor.enviar(job, g.tobytes())
    final = servidor.aguardar(job)
    assert (final["iterations"], final["stop_reason"]) == (2, "tolerance")


def test_metadados_exigidos_pelo_enunciado(servidor, dados):
    _, _, g = dados
    job = novo_id()
    servidor.enviar(job, g.tobytes(), client_id="cliente-7", signal_id="g1", algorithm="cgne", gain="0")
    final = servidor.aguardar(job)
    assert final["client_id"] == "cliente-7"
    assert final["signal_id"] == "g1"
    assert final["algorithm"] == "cgne"
    assert final["model"] == "30x30"
    assert final["gain"] is False
    for campo in ("received_at", "started_at", "finished_at"):
        assert ISO.match(final[campo]), final[campo]
    assert final["queue_wait_s"] >= 0
    assert final["duration_s"] > 0
    assert final["error"] is None


def test_imagem_pgm_identica_a_referencia(servidor, dados):
    modelo, H, g = dados
    job = novo_id()
    servidor.enviar(job, g.tobytes())
    servidor.aguardar(job)
    imagem = servidor.http.get(f"/jobs/{job}/image")
    assert imagem.status_code == 200
    assert imagem.headers["content-type"].startswith("image/x-portable-graymap")
    esperado = ref.pgm(ref.cgnr(H, g)[0], modelo["largura"], modelo["altura"])
    cabecalho = b"P5\n30 30\n255\n"
    assert imagem.content.startswith(cabecalho)
    obtido = np.frombuffer(imagem.content[len(cabecalho):], dtype=np.uint8).astype(int)
    alvo = np.frombuffer(esperado[len(cabecalho):], dtype=np.uint8).astype(int)
    assert np.abs(obtido - alvo).max() <= 1


def test_resultado_persistido_em_disco(servidor, dados):
    _, _, g = dados
    job = novo_id()
    servidor.enviar(job, g.tobytes())
    final = servidor.aguardar(job)
    pasta = servidor.saida / "jobs"
    for _ in range(100):
        if (pasta / f"{job}.json").exists() and (pasta / f"{job}.pgm").exists() and (pasta / f"{job}.f64").exists():
            break
        import time
        time.sleep(0.05)
    assert json.loads((pasta / f"{job}.json").read_text())["iterations"] == final["iterations"]
    assert (pasta / f"{job}.f64").stat().st_size == 8 * 900
    eventos = [json.loads(l) for l in (servidor.saida / "events.jsonl").read_text().splitlines()]
    tipos = [e["event"] for e in eventos if e["job_id"] == job]
    assert tipos[:3] == ["accepted", "started", "finished"]
    assert {"t_wall", "t_mono", "queue_depth", "running"} <= set(eventos[0])


def test_reenvio_identico_nao_duplica(servidor, dados):
    _, _, g = dados
    job = novo_id()
    assert servidor.enviar(job, g.tobytes()).status_code == 202
    antes = servidor.http.get("/metrics").json()["accepted"]
    repetido = servidor.enviar(job, g.tobytes())
    assert repetido.status_code == 200
    assert repetido.json()["job_id"] == job
    assert servidor.http.get("/metrics").json()["accepted"] == antes
    servidor.aguardar(job)


def test_mesmo_id_com_corpo_diferente_gera_conflito(servidor, dados):
    _, _, g = dados
    job = novo_id()
    servidor.enviar(job, g.tobytes())
    outro = g.copy()
    outro[10] += 1.0
    resposta = servidor.enviar(job, outro.tobytes())
    assert resposta.status_code == 409
    assert resposta.json()["error"] == "job_conflict"
    servidor.aguardar(job)


@pytest.mark.parametrize(
    "ajuste,codigo",
    [
        ({"model": "99x99"}, "unknown_model"),
        ({"algorithm": "fista"}, "unknown_algorithm"),
        ({"client_id": "../fora"}, "invalid_params"),
        ({"gain": "talvez"}, "invalid_params"),
    ],
)
def test_parametros_invalidos(servidor, dados, ajuste, codigo):
    _, _, g = dados
    resposta = servidor.enviar(novo_id(), g.tobytes(), **ajuste)
    assert resposta.status_code == 400
    assert resposta.json()["error"] == codigo


def test_job_id_ausente(servidor, dados):
    _, _, g = dados
    resposta = servidor.http.post("/jobs", params=dict(client_id="c", signal_id="s", model="30x30", algorithm="cgnr", gain="0"), content=g.tobytes())
    assert resposta.status_code == 400
    assert resposta.json()["error"] == "invalid_params"


def test_tamanho_errado(servidor, dados):
    _, _, g = dados
    resposta = servidor.enviar(novo_id(), g[:-1].tobytes())
    assert resposta.status_code == 400
    assert resposta.json()["error"] == "invalid_length"


@pytest.mark.parametrize("valor", [np.nan, np.inf])
def test_sinal_nao_finito(servidor, dados, valor):
    _, _, g = dados
    ruim = g.copy()
    ruim[5] = valor
    resposta = servidor.enviar(novo_id(), ruim.tobytes())
    assert resposta.status_code == 400
    assert resposta.json()["error"] == "non_finite"


def test_sinal_nulo_termina_sem_iteracoes(servidor, dados):
    _, _, g = dados
    job = novo_id()
    servidor.enviar(job, np.zeros_like(g).tobytes())
    final = servidor.aguardar(job)
    assert (final["status"], final["iterations"], final["stop_reason"]) == ("done", 0, "zero_residual")
    imagem = servidor.http.get(f"/jobs/{job}/image").content
    assert set(imagem[len(b"P5\n30 30\n255\n"):]) == {0}


def test_desconhecido_retorna_404(servidor):
    for rota in ("/jobs/nada", "/jobs/nada/image", "/jobs/nada/vector"):
        resposta = servidor.http.get(rota)
        assert resposta.status_code == 404
        assert resposta.json()["error"] == "not_found"


def test_fila_cheia_rejeita_e_contabiliza(novo_servidor, dados):
    _, _, g = dados
    s = novo_servidor(workers=1, fila_max=1)
    codigos = [s.enviar(novo_id(), g.tobytes()).status_code for _ in range(12)]
    assert 503 in codigos
    assert 202 in codigos
    metricas = s.http.get("/metrics").json()
    assert metricas["rejected"] == codigos.count(503)
    assert metricas["accepted"] == codigos.count(202)


def test_imagem_antes_de_concluir_retorna_not_ready(novo_servidor, dados):
    _, _, g = dados
    s = novo_servidor(workers=1)
    ids = [novo_id() for _ in range(6)]
    for job in ids:
        s.enviar(job, g.tobytes())
    ultima = s.http.get(f"/jobs/{ids[-1]}/image")
    if s.http.get(f"/jobs/{ids[-1]}").json()["status"] != "done":
        assert ultima.status_code == 409
        assert ultima.json()["error"] == "not_ready"
    for job in ids:
        assert s.aguardar(job)["status"] == "done"


def test_workers_limita_execucao_simultanea(novo_servidor, dados):
    _, _, g = dados
    s = novo_servidor(workers=2)
    ids = [novo_id() for _ in range(8)]
    for job in ids:
        s.enviar(job, g.tobytes())
    for job in ids:
        s.aguardar(job)
    eventos = [json.loads(l) for l in (s.saida / "events.jsonl").read_text().splitlines()]
    assert max(e["running"] for e in eventos) == 2


def test_sem_memoria_falha_explicita(novo_servidor, dados):
    _, _, g = dados
    s = novo_servidor(workers=1, reserva_mem_mb=100_000_000, espera_mem_max_s=1)
    job = novo_id()
    s.enviar(job, g.tobytes())
    final = s.aguardar(job, limite_s=15)
    assert (final["status"], final["error"]) == ("failed", "insufficient_memory")
    resposta = s.http.get(f"/jobs/{job}/image")
    assert resposta.status_code == 409
    assert resposta.json()["error"] == "failed"
    assert s.http.get("/metrics").json()["failed"] == 1


def test_info_e_metrics(servidor, impl):
    info = servidor.http.get("/info").json()
    assert info["implementation"] == impl
    assert info["workers"] == 2
    assert info["blas_threads"] == 1
    assert "30x30" in info["models"]
    assert info["blas"]
    assert info["aquecimento_s"] == 0
    metricas = servidor.http.get("/metrics").json()
    assert {"queue_depth", "running", "accepted", "completed", "failed", "rejected", "waiting_memory", "uptime_s"} <= set(metricas)


def test_aquecimento_acontece_antes_de_aceitar_conexoes(novo_servidor, dados):
    _, _, g = dados
    s = novo_servidor(workers=1, aquecer="30x30")
    assert s.http.get("/info").json()["aquecimento_s"] > 0
    job = novo_id()
    s.enviar(job, g.tobytes())
    assert s.aguardar(job)["status"] == "done"


def test_aquecer_modelo_desconhecido_encerra_com_erro(impl, tmp_path):
    processo = subprocess.run(
        comando(impl) + ["--porta", "0", "--dados", str(RAIZ / "dados"), "--saida", str(tmp_path), "--aquecer", "99x99"],
        cwd=RAIZ, capture_output=True, timeout=30,
    )
    assert processo.returncode != 0


def test_corpo_acima_do_limite_retorna_413(servidor):
    maior = max(m["linhas"] for m in ref.manifesto()["modelos"].values())
    resposta = servidor.enviar(novo_id(), bytes(8 * maior + (1 << 20) + 8))
    assert resposta.status_code == 413
    assert resposta.json()["error"] == "payload_too_large"
