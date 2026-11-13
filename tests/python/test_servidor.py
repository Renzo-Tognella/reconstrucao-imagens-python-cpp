from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import numpy as np
import pytest
import scipy

from recon_py.infraestrutura.threads_blas import fixar_threads_blas
from tests import referencia as ref
from tests.conformidade.conftest import Servidor

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture
def novo_servidor(tmp_path):
    criados = []

    def criar(**opcoes) -> Servidor:
        instancia = Servidor("python", tmp_path / f"s{len(criados)}", **opcoes)
        criados.append(instancia)
        return instancia

    yield criar
    for instancia in criados:
        instancia.encerrar()


@pytest.fixture(scope="module")
def sinal() -> np.ndarray:
    return ref.carregar_sinal("g1")


def test_importar_o_modulo_nao_carrega_numpy_antes_de_fixar_as_threads():
    roteiro = "import sys, recon_py.servidor; sys.exit(int('numpy' in sys.modules or 'scipy' in sys.modules))"
    assert subprocess.run([sys.executable, "-c", roteiro], cwd=RAIZ).returncode == 0


def test_fixa_as_tres_variaveis_de_threads(monkeypatch):
    for nome in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        monkeypatch.setenv(nome, "99")
    fixar_threads_blas(3)
    assert os.environ["OPENBLAS_NUM_THREADS"] == "3"
    assert os.environ["OMP_NUM_THREADS"] == "3"
    assert os.environ["VECLIB_MAXIMUM_THREADS"] == "3"


def test_info_reporta_blas_da_configuracao_do_scipy(novo_servidor):
    s = novo_servidor(workers=1, blas_threads=2)
    info = s.http.get("/info").json()
    esperado = scipy.show_config(mode="dicts")["Build Dependencies"]["blas"]["name"]
    assert esperado.lower() in info["blas"].lower()
    assert info["blas_threads"] == 2
    assert info["language_version"].startswith("3.12")


def test_sigterm_com_fila_nao_vazia_encerra_limpo_sem_iniciar_novas(novo_servidor, sinal):
    # Com ganho cada tarefa faz 10 iterações, então a fila não esvazia durante os envios.
    modelo, _ = ref.carregar_modelo()
    corpo = ref.ganho(sinal, modelo["S"], modelo["N"]).tobytes()
    s = novo_servidor(workers=1)
    ids = [uuid.uuid4().hex for _ in range(60)]
    for job in ids:
        assert s.enviar(job, corpo).status_code == 202
    inicio = time.monotonic()
    s.encerrar()
    assert time.monotonic() - inicio < 15
    assert s.processo.returncode == 0
    eventos = [json.loads(linha) for linha in (s.saida / "events.jsonl").read_text().splitlines()]
    iniciadas = {e["job_id"] for e in eventos if e["event"] == "started"}
    terminadas = {e["job_id"] for e in eventos if e["event"] == "finished"}
    assert iniciadas == terminadas
    assert len(iniciadas) < len(ids)


def test_rota_inexistente_responde_erro_em_json(novo_servidor):
    s = novo_servidor()
    resposta = s.http.get("/nao-existe")
    assert resposta.status_code == 404
    assert resposta.json()["error"] == "not_found"
    assert "detail" in resposta.json()


def test_metodo_nao_permitido_responde_erro_em_json(novo_servidor):
    s = novo_servidor()
    resposta = s.http.delete("/metrics")
    assert resposta.status_code == 405
    assert resposta.json()["error"] == "http_error"


def test_corpo_maior_que_o_sinal_mas_dentro_do_limite_e_invalid_length(novo_servidor, sinal):
    s = novo_servidor()
    resposta = s.enviar(uuid.uuid4().hex, np.concatenate((sinal, sinal)).tobytes())
    assert resposta.status_code == 400
    assert resposta.json()["error"] == "invalid_length"


def test_corpo_no_limite_exato_ainda_e_invalid_length_e_um_byte_a_mais_e_413(novo_servidor, sinal):
    s = novo_servidor()
    maior = max(m["linhas"] for m in ref.manifesto()["modelos"].values())
    limite = 8 * maior + (1 << 20)
    assert s.enviar(uuid.uuid4().hex, bytes(limite)).json()["error"] == "invalid_length"
    resposta = s.enviar(uuid.uuid4().hex, bytes(limite + 1))
    assert resposta.status_code == 413
    assert resposta.json()["error"] == "payload_too_large"


def test_parametro_invalido_vem_antes_do_limite_do_corpo(novo_servidor, sinal):
    s = novo_servidor()
    resposta = s.enviar(uuid.uuid4().hex, bytes(8 * max(m["linhas"] for m in ref.manifesto()["modelos"].values()) + (1 << 20) + 1), algorithm="fista")
    assert resposta.status_code == 400
    assert resposta.json()["error"] == "unknown_algorithm"


def test_mesmo_corpo_com_metadados_diferentes_conflita(novo_servidor, sinal):
    s = novo_servidor()
    job = uuid.uuid4().hex
    assert s.enviar(job, sinal.tobytes()).status_code == 202
    resposta = s.enviar(job, sinal.tobytes(), client_id="outro")
    assert resposta.status_code == 409
    assert resposta.json()["error"] == "job_conflict"


def test_aquecer_lista_com_modelo_desconhecido_encerra_com_erro(tmp_path):
    comando = [sys.executable, "-m", "recon_py.servidor", "--porta", "0", "--dados", "dados",
               "--saida", str(tmp_path), "--aquecer", "30x30,99x99"]
    execucao = subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True, timeout=30)
    assert execucao.returncode != 0
    assert "99x99" in execucao.stderr


def test_workers_invalido_nao_sobe():
    comando = [sys.executable, "-m", "recon_py.servidor", "--porta", "1", "--dados", "dados", "--saida", "x", "--workers", "0"]
    execucao = subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True)
    assert execucao.returncode != 0
    assert "workers" in execucao.stderr
