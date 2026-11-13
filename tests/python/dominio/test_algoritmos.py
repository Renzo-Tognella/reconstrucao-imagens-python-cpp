from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import threading
import tracemalloc
from pathlib import Path

import numpy as np
import pytest
from scipy.linalg.blas import daxpy, dgemv

from recon_py.dominio.algoritmos.catalogo import ALGORITMOS as CATALOGO
from recon_py.dominio.algoritmos.cgne import cgne
from recon_py.dominio.algoritmos.cgnr import cgnr
from recon_py.dominio.algoritmos.produtos import h_vezes, ht_vezes
from recon_py.dominio.algoritmos.resultado import FalhaNumerica
from tests import referencia as ref

RAIZ = Path(__file__).resolve().parents[3]
REFERENCIAS = [("cgnr", ref.cgnr), ("cgne", ref.cgne)]
ALGORITMOS = [cgnr, cgne]


@pytest.fixture(scope="module")
def modelo_h():
    return ref.carregar_modelo()


def matriz(linhas) -> np.ndarray:
    return np.array(linhas, dtype=np.float64, order="F")


@pytest.mark.parametrize("nome,referencia", REFERENCIAS)
@pytest.mark.parametrize("id_sinal", ["g1", "g2", "g3"])
@pytest.mark.parametrize("com_ganho", [False, True])
def test_coincide_com_referencia(modelo_h, nome, referencia, id_sinal, com_ganho):
    modelo, H = modelo_h
    g = ref.carregar_sinal(id_sinal)
    sinal = ref.ganho(g, modelo["S"], modelo["N"]) if com_ganho else g
    esperado, normas, iteracoes, motivo = referencia(H, sinal)

    obtido = CATALOGO[nome](H, sinal)

    assert obtido.iterations == iteracoes
    assert obtido.stop_reason == motivo
    assert obtido.residual_norms == pytest.approx(normas, rel=1e-8)
    np.testing.assert_allclose(obtido.f, esperado, rtol=1e-7, atol=1e-12)


@pytest.mark.parametrize("algoritmo", ALGORITMOS)
def test_sinal_nulo_para_sem_iteracoes(algoritmo):
    resultado = algoritmo(matriz([[1, 0], [0, 1], [1, 1]]), np.zeros(3))
    assert resultado.iterations == 0
    assert resultado.stop_reason == "zero_residual"
    assert resultado.residual_norms == [0.0]
    np.testing.assert_array_equal(resultado.f, np.zeros(2))


def test_cgnr_com_sinal_ortogonal_a_h_para_sem_iteracoes():
    resultado = cgnr(matriz([[1.0], [1.0]]), np.array([1.0, -1.0]))
    assert (resultado.iterations, resultado.stop_reason) == (0, "zero_residual")
    assert resultado.residual_norms == [pytest.approx(np.sqrt(2))]


def test_cgnr_para_com_residuo_zero_dentro_do_laco():
    # A diferença entre normas é grande e o gradiente seguinte zera exatamente.
    resultado = cgnr(matriz([[1.0, 0.0], [0.0, 1.0]]), np.array([3.0, 0.0]))
    assert (resultado.iterations, resultado.stop_reason) == (1, "zero_residual")
    np.testing.assert_array_equal(resultado.f, [3.0, 0.0])


def test_cgne_para_com_residuo_zero_dentro_do_laco():
    resultado = cgne(matriz([[1.0, 0.0], [0.0, 1.0]]), np.array([3.0, 0.0]))
    assert (resultado.iterations, resultado.stop_reason) == (1, "zero_residual")


def test_cgne_com_h_nula_e_falha_numerica():
    with pytest.raises(FalhaNumerica):
        cgne(np.zeros((2, 2), order="F"), np.array([1.0, 1.0]))


@pytest.mark.parametrize("algoritmo", ALGORITMOS)
@pytest.mark.parametrize("invalido", [np.nan, np.inf])
def test_valor_nao_finito_em_h_vira_falha_numerica(algoritmo, invalido):
    H = matriz([[1.0, invalido], [0.5, 2.0], [1.0, 1.0]])
    with pytest.raises(FalhaNumerica):
        algoritmo(H, np.array([1.0, 2.0, 3.0]))


@pytest.mark.parametrize("algoritmo", ALGORITMOS)
def test_estouro_durante_o_calculo_vira_falha_numerica(algoritmo):
    H = matriz([[1e200, 1e-200], [1e-200, 1e200]])
    with pytest.raises(FalhaNumerica):
        algoritmo(H, np.array([1e200, 1e200]))


@pytest.mark.parametrize("algoritmo", ALGORITMOS)
def test_entradas_nao_sao_alteradas(modelo_h, algoritmo):
    _, H = modelo_h
    g = ref.carregar_sinal("g1")
    copia = g.copy()
    resultado = algoritmo(H, g)
    np.testing.assert_array_equal(g, copia)
    assert not H.flags.writeable
    assert not np.shares_memory(resultado.f, g)


@pytest.mark.parametrize("algoritmo", ALGORITMOS)
def test_h_em_ordem_c_e_recusada_em_vez_de_copiada(algoritmo):
    with pytest.raises(ValueError):
        algoritmo(np.ones((3, 2), order="C"), np.ones(3))


@pytest.mark.parametrize("algoritmo", ALGORITMOS)
def test_sinal_de_tamanho_errado_e_recusado(algoritmo):
    with pytest.raises(ValueError):
        algoritmo(np.ones((3, 2), order="F"), np.ones(4))


@pytest.mark.parametrize("algoritmo", ALGORITMOS)
def test_sinal_que_nao_e_float64_nativo_e_recusado(algoritmo):
    # O wrapper converteria r numa cópia e daxpy atualizaria só a cópia: o resíduo ficaria errado sem erro.
    with pytest.raises(ValueError):
        algoritmo(np.ones((3, 2), order="F"), np.ones(3, dtype=np.float32))


def test_controle_tracemalloc_detecta_copia_do_wrapper():
    # Sem este controle, um pico baixo no teste seguinte não provaria ausência de cópia.
    ordem_c = np.ones((1000, 1000), order="C")
    tracemalloc.start()
    dgemv(1.0, ordem_c, np.ones(1000))
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert pico >= ordem_c.nbytes


@pytest.mark.parametrize("algoritmo", ALGORITMOS)
def test_pico_de_alocacao_fica_nos_buffers_de_trabalho(modelo_h, algoritmo):
    modelo, H = modelo_h
    g = ref.ganho(ref.carregar_sinal("g1"), modelo["S"], modelo["N"])
    custo = 8 * (2 * modelo["linhas"] + 3 * modelo["colunas"])
    tracemalloc.start()
    algoritmo(H, g)
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert pico < custo + 64 * 1024


def test_wrappers_escrevem_nos_buffers_entregues(modelo_h):
    modelo, H = modelo_h
    y = np.empty(modelo["linhas"])
    z = np.empty(modelo["colunas"])
    assert dgemv(1.0, H, np.ones(modelo["colunas"]), beta=0.0, y=y, overwrite_y=1) is y
    assert dgemv(1.0, H, y, beta=0.0, y=z, overwrite_y=1, trans=1) is z
    assert daxpy(np.ones(3), (destino := np.zeros(3)), a=2.0) is destino


def test_reconstrucao_nao_causa_salto_de_rss():
    # Roda em processo novo: ru_maxrss só cresce, e testes anteriores mascarariam uma cópia de H (192 MiB).
    roteiro = textwrap.dedent(
        """
        import json, resource
        import numpy as np
        from recon_py.dominio.algoritmos.cgne import cgne
        from recon_py.dominio.algoritmos.cgnr import cgnr
        from tests import referencia as ref
        modelo, H = ref.carregar_modelo()
        g = ref.ganho(ref.carregar_sinal("g1"), modelo["S"], modelo["N"])
        np.add.reduce(H, axis=None)
        antes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        for algoritmo in (cgnr, cgne):
            algoritmo(H, g)
        depois = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        print(json.dumps({"salto": depois - antes, "h": int(H.nbytes)}))
        """
    )
    saida = subprocess.run([sys.executable, "-c", roteiro], cwd=RAIZ, capture_output=True, text=True, check=True)
    medicao = json.loads(saida.stdout)
    assert medicao["salto"] < medicao["h"] / 4


def _chamadas_em_que_outra_thread_avancou(chamada, repeticoes=10) -> int:
    # O intervalo longo impede a troca forçada de thread: a outra só avança se a chamada soltar o GIL.
    contador = [0]
    parar = threading.Event()

    def contar():
        while not parar.is_set():
            contador[0] += 1

    intervalo = sys.getswitchinterval()
    sys.setswitchinterval(0.05)
    thread = threading.Thread(target=contar)
    thread.start()
    try:
        avancos = 0
        for _ in range(repeticoes):
            antes = contador[0]
            chamada()
            avancos += contador[0] != antes
        return avancos
    finally:
        parar.set()
        thread.join()
        sys.setswitchinterval(intervalo)


def test_produto_matriz_vetor_solta_o_gil():
    # Sem isso, W threads em Python rodam em série e o servidor não processa imagens ao mesmo tempo.
    # Máquina carregada só pode esconder a soltura, nunca inventá-la: por isso vale a melhor tentativa.
    H = np.asfortranarray(np.random.default_rng(0).random((2500, 2500)))
    x = np.ones(2500)
    y = np.empty(2500)

    def melhor(chamada):
        return max(_chamadas_em_que_outra_thread_avancou(chamada) for _ in range(5))

    def pior(chamada):
        return min(_chamadas_em_que_outra_thread_avancou(chamada) for _ in range(5))

    assert pior(lambda: dgemv(1.0, H, x, beta=0.0, y=y, overwrite_y=1)) <= 2
    assert melhor(lambda: h_vezes(H, x, y)) >= 4
    assert melhor(lambda: ht_vezes(H, x, y)) >= 4
