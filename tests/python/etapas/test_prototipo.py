from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from tests import referencia as ref

RAIZ = Path(__file__).resolve().parents[3]
CAMPOS = ["iterations", "stop_reason", "residual_norms", "duration_s", "rss_mb", "cpu_s", "carga_h_s"]


def rodar(*args: str) -> subprocess.CompletedProcess:
    comando = [sys.executable, "-m", "recon_py.prototipo", "--dados", "dados", "--modelo", "30x30", *args]
    return subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True)


def test_imprime_uma_linha_json_por_repeticao():
    execucao = rodar("--sinal", "dados/sinais/30x30/g1.f64", "--algoritmo", "cgnr", "--repeticoes", "2")
    assert execucao.returncode == 0, execucao.stderr
    assert execucao.stderr == ""
    linhas = [json.loads(linha) for linha in execucao.stdout.splitlines()]
    assert len(linhas) == 2
    for linha in linhas:
        assert list(linha) == CAMPOS
        assert (linha["iterations"], linha["stop_reason"]) == (2, "tolerance")
        assert len(linha["residual_norms"]) == 3
        assert linha["duration_s"] > 0
        assert linha["cpu_s"] > 0
        assert linha["rss_mb"] > 0
        assert linha["carga_h_s"] >= 0


def test_rss_e_o_pico_do_processo_em_mib_e_inclui_h_mapeada():
    # Mesma convenção do protótipo C++ (ru_maxrss), para os números serem comparáveis.
    execucao = rodar("--sinal", "dados/sinais/30x30/g1.f64", "--algoritmo", "cgnr", "--blas-threads", "1")
    assert execucao.returncode == 0, execucao.stderr
    assert json.loads(execucao.stdout)["rss_mb"] > 150


def test_importar_o_modulo_nao_carrega_numpy_antes_de_fixar_as_threads():
    roteiro = "import sys, recon_py.prototipo; sys.exit(int('numpy' in sys.modules or 'scipy' in sys.modules))"
    assert subprocess.run([sys.executable, "-c", roteiro], cwd=RAIZ).returncode == 0


def test_uma_repeticao_por_padrao_e_grava_pgm(tmp_path):
    destino = tmp_path / "x.pgm"
    execucao = rodar("--sinal", "dados/sinais/30x30/g1.f64", "--algoritmo", "cgne", "--saida", str(destino))
    assert execucao.returncode == 0, execucao.stderr
    assert len(execucao.stdout.splitlines()) == 1
    modelo, H = ref.carregar_modelo()
    esperado = ref.pgm(ref.cgne(H, ref.carregar_sinal("g1"))[0], modelo["largura"], modelo["altura"])
    cabecalho = b"P5\n30 30\n255\n"
    obtido = destino.read_bytes()
    assert obtido.startswith(cabecalho)
    diferenca = np.frombuffer(obtido, np.uint8).astype(int) - np.frombuffer(esperado, np.uint8).astype(int)
    assert np.abs(diferenca).max() <= 1


def test_sinal_de_tamanho_errado_termina_com_erro(tmp_path):
    arquivo = tmp_path / "curto.f64"
    np.zeros(10).tofile(arquivo)
    execucao = rodar("--sinal", str(arquivo), "--algoritmo", "cgnr")
    assert execucao.returncode == 2
    assert execucao.stdout == ""
    assert "sinal" in execucao.stderr


def test_sinal_nao_finito_termina_com_erro(tmp_path):
    arquivo = tmp_path / "nan.f64"
    sinal = ref.carregar_sinal("g1")
    sinal[3] = np.nan
    sinal.tofile(arquivo)
    execucao = rodar("--sinal", str(arquivo), "--algoritmo", "cgnr")
    assert execucao.returncode != 0
    assert execucao.stdout == ""


def test_repeticoes_invalidas_sao_recusadas():
    execucao = rodar("--sinal", "dados/sinais/30x30/g1.f64", "--algoritmo", "cgnr", "--repeticoes", "0")
    assert execucao.returncode != 0
    assert "repeticoes" in execucao.stderr


def test_modelo_desconhecido_termina_com_erro_legivel():
    comando = [sys.executable, "-m", "recon_py.prototipo", "--dados", "dados", "--modelo", "99x99",
               "--sinal", "dados/sinais/30x30/g1.f64", "--algoritmo", "cgnr"]
    execucao = subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True)
    assert execucao.returncode == 2
    assert "modelo desconhecido" in execucao.stderr
