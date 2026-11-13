from __future__ import annotations

import json
import re
import threading
import time
import zlib
from dataclasses import replace

import numpy as np
import pytest

from recon_py.aplicacao.fila.controle_memoria import custo_bytes
from recon_py.aplicacao.fila.fila import Conflito, Fila, FilaCheia, OpcoesFila
from recon_py.aplicacao.fila.tarefa import Pedido
from recon_py.dominio.algoritmos import catalogo
from recon_py.dominio.algoritmos.resultado import FalhaNumerica, Resultado
from recon_py.dominio.modelo import Modelo
from recon_py.infraestrutura import gravacao
from recon_py.infraestrutura.matriz import mapear_h
from recon_py.montagem import montar_fila, montar_recursos

LIMITE_S = 5.0
ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")


@pytest.fixture
def modelo(tmp_path) -> Modelo:
    arquivo = tmp_path / "H.f64"
    np.arange(1.0, 7.0 * 3 + 1).reshape((7, 3), order="F").tofile(arquivo)
    return Modelo("m", linhas=7, colunas=3, largura=3, altura=1, arquivo=arquivo)


class AlgoritmoControlado:
    """Só termina quando o teste libera, para fixar a intercalação entre as tarefas."""

    def __init__(self) -> None:
        self.liberar = threading.Event()

    def __call__(self, H, g) -> Resultado:
        assert self.liberar.wait(LIMITE_S)
        return Resultado(np.ones(H.shape[1]), [1.0], 1, "tolerance")


@pytest.fixture
def controlado(monkeypatch) -> AlgoritmoControlado:
    algoritmo = AlgoritmoControlado()
    monkeypatch.setitem(catalogo.ALGORITMOS, "controlado", algoritmo)
    return algoritmo


@pytest.fixture
def criar_fila(modelo, tmp_path, controlado):
    # Depende de `controlado` para encerrar a fila antes de o algoritmo sair de ALGORITMOS.
    criadas = []

    def criar(trocas: dict | None = None, **opcoes) -> Fila:
        """`trocas` substitui recursos externos reais, como a leitura de memória livre."""
        valores = dict(workers=1, fila_max=256, fila_max_bytes=2**28, reserva_bytes=0, espera_max_s=60.0) | opcoes
        recursos = replace(montar_recursos(tmp_path / "saida"), **(trocas or {}))
        fila = Fila({"m": modelo}, OpcoesFila(**valores), recursos)
        fila.iniciar()
        criadas.append(fila)
        return fila

    yield criar
    controlado.liberar.set()
    for fila in criadas:
        fila.encerrar()


def pedido(job_id: str, modelo: Modelo, algorithm: str = "controlado", client_id: str = "c", valor: float = 1.0) -> Pedido:
    sinal = np.full(modelo.linhas, valor)
    return Pedido(job_id, client_id, "g", modelo.nome, algorithm, False, sinal, zlib.crc32(sinal.tobytes()))


def esperar(condicao) -> None:
    fim = time.monotonic() + LIMITE_S
    while not condicao():
        assert time.monotonic() < fim, "condição não ocorreu no prazo"
        time.sleep(0.005)


def eventos(fila: Fila) -> list[dict]:
    return [json.loads(linha) for linha in fila.caminho_eventos.read_text().splitlines()]


def status(fila: Fila, job_id: str) -> str:
    return fila.consultar(job_id)["status"]


def test_custo_conta_so_os_vetores_de_trabalho(modelo):
    # H é mapeamento somente leitura de arquivo: o sistema recupera essas páginas sem usar swap.
    assert custo_bytes(modelo) == 8 * (2 * 7 + 3 * 3)


def test_h_maior_que_a_memoria_fisica_falha_na_hora_sem_travar_quem_vem_atras(tmp_path, modelo, controlado):
    # O arquivo de H nem precisa existir: a tarefa falha antes do primeiro mapeamento.
    gigante = Modelo("gigante", linhas=10**6, colunas=10**6, largura=1, altura=1, arquivo=tmp_path / "nao-existe.f64")
    fila = montar_fila({"m": modelo, "gigante": gigante}, OpcoesFila(1, 256, 2**28, 0, 60.0), tmp_path / "saida")
    fila.iniciar()
    controlado.liberar.set()
    try:
        fila.submeter(pedido("g", gigante))
        fila.submeter(pedido("a", modelo))
        esperar(lambda: status(fila, "a") == "done")
        corpo = fila.consultar("g")
        assert (corpo["status"], corpo["error"]) == ("failed", "insufficient_memory")
        assert corpo["started_at"] is None
        assert corpo["queue_wait_s"] is None
        assert corpo["finished_at"] is not None
    finally:
        fila.encerrar()


@pytest.mark.parametrize("total_acima,cabe", [(0, True), (-1, False)])
def test_limite_de_h_desconta_a_reserva_da_memoria_fisica(criar_fila, modelo, controlado, total_acima, cabe):
    tamanho_h = 8 * modelo.linhas * modelo.colunas
    controlado.liberar.set()
    fila = criar_fila({"memoria_fisica": lambda: tamanho_h + 100 + total_acima}, workers=1, reserva_bytes=100)
    fila.submeter(pedido("a", modelo))
    esperar(lambda: status(fila, "a") in ("done", "failed"))
    assert status(fila, "a") == ("done" if cabe else "failed")


def test_limite_de_h_nao_vale_depois_do_mapeamento(criar_fila, modelo, controlado):
    memoria = {"total": 2**40}
    controlado.liberar.set()
    fila = criar_fila({"memoria_fisica": lambda: memoria["total"]}, workers=1)
    fila.submeter(pedido("a", modelo))
    esperar(lambda: status(fila, "a") == "done")
    memoria["total"] = 0
    fila.submeter(pedido("b", modelo))
    esperar(lambda: status(fila, "b") in ("done", "failed"))
    assert status(fila, "b") == "done"


def test_aquecer_mapeia_h_uma_vez_e_a_tarefa_reaproveita(criar_fila, modelo, controlado):
    chamadas = []
    controlado.liberar.set()
    fila = criar_fila({"abrir_h": lambda m: chamadas.append(m.nome) or mapear_h(m)}, workers=1)
    fila.aquecer(["m"])
    fila.submeter(pedido("a", modelo))
    esperar(lambda: status(fila, "a") == "done")
    assert chamadas == ["m"]


def test_fifo_com_um_worker(criar_fila, modelo, controlado):
    fila = criar_fila(workers=1)
    for job in "abc":
        assert fila.submeter(pedido(job, modelo)) == (True, "queued")
    esperar(lambda: fila.metricas()["running"] == 1)
    assert fila.metricas()["queue_depth"] == 2
    assert status(fila, "a") == "running"
    assert status(fila, "b") == "queued"
    controlado.liberar.set()
    esperar(lambda: fila.metricas()["completed"] == 3)
    iniciados = [e["job_id"] for e in eventos(fila) if e["event"] == "started"]
    assert iniciados == ["a", "b", "c"]


def test_contagem_nos_eventos_nao_inclui_em_execucao_na_fila(criar_fila, modelo, controlado):
    fila = criar_fila(workers=1)
    fila.submeter(pedido("a", modelo))
    esperar(lambda: fila.metricas()["running"] == 1)
    fila.submeter(pedido("b", modelo))
    controlado.liberar.set()
    esperar(lambda: fila.metricas()["completed"] == 2)
    por_chave = {(e["event"], e["job_id"]): e for e in eventos(fila)}
    assert por_chave["started", "a"]["running"] == 1
    assert por_chave["started", "a"]["queue_depth"] == 0
    assert por_chave["accepted", "b"]["queue_depth"] == 1
    assert por_chave["accepted", "b"]["running"] == 1
    assert ISO.fullmatch(por_chave["accepted", "b"]["t_wall"])


def test_tarefas_em_execucao_reservam_memoria(criar_fila, modelo, controlado):
    # Cabe exatamente a primeira tarefa. A segunda precisa esperar, sem falhar enquanto há tarefa rodando.
    disponivel = custo_bytes(modelo) + 100
    fila = criar_fila({"memoria_livre": lambda: disponivel}, workers=2, reserva_bytes=100, espera_max_s=0.05)
    fila.submeter(pedido("a", modelo))
    fila.submeter(pedido("b", modelo))
    esperar(lambda: fila.metricas()["waiting_memory"])
    time.sleep(0.25)
    assert fila.metricas()["running"] == 1
    assert status(fila, "b") == "queued"
    controlado.liberar.set()
    esperar(lambda: fila.metricas()["completed"] == 2)
    assert fila.metricas()["waiting_memory"] is False
    assert fila.metricas()["failed"] == 0


def test_cabeca_sem_memoria_e_sem_tarefas_rodando_falha(criar_fila, modelo, controlado):
    fila = criar_fila({"memoria_livre": lambda: 0}, workers=1, reserva_bytes=1, espera_max_s=0.05)
    fila.submeter(pedido("a", modelo))
    esperar(lambda: status(fila, "a") == "failed")
    corpo = fila.consultar("a")
    assert corpo["error"] == "insufficient_memory"
    assert corpo["started_at"] is None
    assert fila.metricas() | {"uptime_s": 0} == {
        "queue_depth": 0, "running": 0, "accepted": 1, "completed": 0, "failed": 1,
        "rejected": 0, "waiting_memory": False, "uptime_s": 0,
    }
    assert json.loads(fila.caminho_resultado("a", "json").read_text())["error"] == "insufficient_memory"
    assert not fila.caminho_resultado("a", "pgm").exists()
    assert [e["event"] for e in eventos(fila)] == ["accepted", "failed"]


def test_prazo_de_memoria_so_conta_com_nada_em_execucao(criar_fila, modelo, controlado):
    # Com W=2 a cabeça espera enquanto outra roda. O prazo só pode começar quando a última tarefa terminar.
    memoria = {"valor": 2**40}
    espera_max_s = 0.3
    fila = criar_fila({"memoria_livre": lambda: memoria["valor"]}, workers=2, reserva_bytes=1, espera_max_s=espera_max_s)
    fila.submeter(pedido("a", modelo))
    esperar(lambda: status(fila, "a") == "running")
    memoria["valor"] = 0
    fila.submeter(pedido("b", modelo))
    esperar(lambda: fila.metricas()["waiting_memory"])
    time.sleep(2 * espera_max_s)
    assert status(fila, "b") == "queued"
    controlado.liberar.set()
    esperar(lambda: status(fila, "b") == "failed")
    por_chave = {(e["event"], e["job_id"]): e for e in eventos(fila)}
    assert por_chave["failed", "b"]["t_mono"] - por_chave["finished", "a"]["t_mono"] >= espera_max_s


def test_memoria_que_volta_libera_a_cabeca(criar_fila, modelo, controlado):
    memoria = {"valor": 0}
    fila = criar_fila({"memoria_livre": lambda: memoria["valor"]}, workers=1, reserva_bytes=1)
    fila.submeter(pedido("a", modelo))
    esperar(lambda: fila.metricas()["waiting_memory"])
    controlado.liberar.set()
    memoria["valor"] = 2**40
    esperar(lambda: status(fila, "a") == "done")


def test_falha_numerica_libera_a_reserva_e_nao_gera_imagem(criar_fila, modelo, controlado, monkeypatch):
    def falhar(H, g):
        raise FalhaNumerica("ww igual a zero")

    monkeypatch.setitem(catalogo.ALGORITMOS, "falhar", falhar)
    controlado.liberar.set()
    fila = criar_fila(workers=1)
    fila.submeter(pedido("a", modelo, algorithm="falhar"))
    fila.submeter(pedido("b", modelo))
    esperar(lambda: status(fila, "b") == "done")
    corpo = fila.consultar("a")
    assert (corpo["status"], corpo["error"]) == ("failed", "numerical_failure")
    assert corpo["finished_at"] is not None
    assert corpo["duration_s"] is None
    assert not fila.caminho_resultado("a", "pgm").exists()
    assert not fila.caminho_resultado("a", "f64").exists()
    assert fila.metricas()["failed"] == 1
    assert fila.metricas()["completed"] == 1


class ArquivoQuebrado:
    def write(self, _: str) -> None:
        raise OSError(28, "disco cheio")

    def close(self) -> None:
        raise OSError(28, "disco cheio")


def test_falha_ao_gravar_eventos_nao_para_a_fila(criar_fila, modelo, controlado, capsys):
    fila = criar_fila(workers=1)
    fila._eventos._arquivo = ArquivoQuebrado()
    controlado.liberar.set()
    for job in "abc":
        fila.submeter(pedido(job, modelo))
    esperar(lambda: fila.metricas()["completed"] == 3)
    metricas = fila.metricas()
    assert (metricas["running"], metricas["failed"], metricas["queue_depth"]) == (0, 0, 0)
    assert "events.jsonl" in capsys.readouterr().err


def test_falha_depois_de_concluir_nao_conta_a_tarefa_duas_vezes(criar_fila, modelo, controlado, monkeypatch, capsys):
    original = Fila._registrar_evento

    def quebrar_no_fim(self, evento, job_id):
        if evento == "finished" and job_id == "a":
            raise RuntimeError("falha depois de concluir")
        original(self, evento, job_id)

    monkeypatch.setattr(Fila, "_registrar_evento", quebrar_no_fim)
    controlado.liberar.set()
    fila = criar_fila(workers=1)
    fila.submeter(pedido("a", modelo))
    fila.submeter(pedido("b", modelo))
    esperar(lambda: status(fila, "b") == "done")
    metricas = fila.metricas()
    assert (metricas["completed"], metricas["failed"], metricas["running"]) == (2, 0, 0)
    assert status(fila, "a") == "done"
    assert json.loads(fila.caminho_resultado("a", "json").read_text())["status"] == "done"


def test_falha_de_gravacao_vira_output_write_failed(criar_fila, modelo, controlado, monkeypatch, capsys):
    original = gravacao.gravar_atomico

    def disco_cheio_para_a(destino, conteudo):
        if destino.stem == "a":
            raise OSError(28, "disco cheio")
        original(destino, conteudo)

    monkeypatch.setattr(gravacao, "gravar_atomico", disco_cheio_para_a)
    controlado.liberar.set()
    fila = criar_fila(workers=1)
    fila.submeter(pedido("a", modelo))
    fila.submeter(pedido("b", modelo))
    esperar(lambda: status(fila, "b") == "done")
    corpo = fila.consultar("a")
    assert (corpo["status"], corpo["error"]) == ("failed", "output_write_failed")
    # O cálculo terminou: as medidas continuam disponíveis mesmo sem os arquivos.
    assert corpo["iterations"] == 1
    assert corpo["duration_s"] > 0
    metricas = fila.metricas()
    assert (metricas["completed"], metricas["failed"]) == (1, 1)
    assert "disco cheio" in capsys.readouterr().err


def test_erro_inesperado_nao_trava_a_fila(criar_fila, modelo, controlado, monkeypatch, capsys):
    def quebrar(H, g):
        raise RuntimeError("falha de programação")

    monkeypatch.setitem(catalogo.ALGORITMOS, "quebrar", quebrar)
    controlado.liberar.set()
    fila = criar_fila(workers=1)
    fila.submeter(pedido("a", modelo, algorithm="quebrar"))
    fila.submeter(pedido("b", modelo))
    esperar(lambda: status(fila, "b") == "done")
    assert fila.consultar("a")["error"] == "internal_error"
    assert "falha de programação" in capsys.readouterr().err


def test_h_e_mapeada_uma_vez_por_modelo(criar_fila, modelo, controlado):
    chamadas = []
    fila = criar_fila({"abrir_h": lambda m: chamadas.append(m.nome) or mapear_h(m)}, workers=2)
    for job in "abcd":
        fila.submeter(pedido(job, modelo))
    controlado.liberar.set()
    esperar(lambda: fila.metricas()["completed"] == 4)
    assert chamadas == ["m"]


def test_reenvio_identico_devolve_estado_atual_sem_nova_tarefa(criar_fila, modelo, controlado):
    fila = criar_fila(workers=1)
    fila.submeter(pedido("a", modelo))
    esperar(lambda: status(fila, "a") == "running")
    assert fila.submeter(pedido("a", modelo)) == (False, "running")
    assert fila.metricas()["accepted"] == 1
    controlado.liberar.set()


@pytest.mark.parametrize("diferenca", [{"valor": 2.0}, {"client_id": "outro"}, {"algorithm": "cgnr"}])
def test_mesmo_id_com_corpo_ou_metadados_diferentes_conflita(criar_fila, modelo, controlado, diferenca):
    fila = criar_fila(workers=1)
    fila.submeter(pedido("a", modelo))
    with pytest.raises(Conflito):
        fila.submeter(pedido("a", modelo, **diferenca))
    controlado.liberar.set()


def test_fila_cheia_por_quantidade_e_por_bytes(criar_fila, modelo, controlado):
    fila = criar_fila(workers=1, fila_max=2, fila_max_bytes=8 * modelo.linhas)
    fila.submeter(pedido("a", modelo))
    esperar(lambda: fila.metricas()["running"] == 1)
    fila.submeter(pedido("b", modelo))
    with pytest.raises(FilaCheia):
        fila.submeter(pedido("c", modelo))
    assert fila.metricas()["rejected"] == 1
    assert [e for e in eventos(fila) if e["event"] == "rejected"][0]["job_id"] == "c"
    # A tarefa recusada não fica registrada: o mesmo id entra quando houver espaço.
    assert fila.consultar("c") is None
    controlado.liberar.set()
    esperar(lambda: fila.metricas()["completed"] == 2)
    assert fila.submeter(pedido("c", modelo)) == (True, "queued")


def test_encerrar_conclui_a_que_roda_e_nao_inicia_a_fila(modelo, controlado, tmp_path):
    fila = montar_fila({"m": modelo}, OpcoesFila(1, 256, 2**28, 0, 60.0), tmp_path / "saida")
    fila.iniciar()
    fila.submeter(pedido("a", modelo))
    fila.submeter(pedido("b", modelo))
    esperar(lambda: status(fila, "a") == "running")
    encerramento = threading.Thread(target=fila.encerrar)
    encerramento.start()
    time.sleep(0.05)
    controlado.liberar.set()
    encerramento.join(LIMITE_S)
    assert not encerramento.is_alive()
    assert status(fila, "a") == "done"
    assert status(fila, "b") == "queued"
    assert fila.caminho_resultado("a", "pgm").exists()
    assert [e["event"] for e in eventos(fila) if e["job_id"] == "b"] == ["accepted"]
