import io
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from cliente.carga.manifesto import gerar_carga, gravar_carga
from cliente.comum.caminhos import DADOS_PADRAO
from cliente.demonstracao.instancia import executar_instancia, main, pedidos_do_cliente
from cliente.demonstracao.terminal import Pintor, cor_ativa, linha_desfecho, linha_envio, linha_progresso, linhas_resumo
from cliente.envio.enviar_sinais import CargaInvalida

RAIZ = Path(__file__).resolve().parents[3]
ANSI = re.compile(r"\x1b\[[0-9;]*m")
SEM_COR = Pintor(False)
COM_COR = Pintor(True)


def nova_carga(dados, *, clientes=3, sinais=3, intervalo=0.3, semente=42):
    return gerar_carga(dados, semente=semente, clientes=clientes, sinais_por_cliente=sinais, algoritmos=None,
                       intervalo_max_s=intervalo)


def gravar(carga, pasta: Path) -> Path:
    caminho = pasta / "carga.json"
    gravar_carga(carga, caminho)
    return caminho


def rodar(caminho, numero, url, dados, saida, **opcoes):
    terminal = io.StringIO()
    resultado = executar_instancia(caminho, numero, url, saida=saida, dados=dados, intervalo_consulta_s=0.05,
                                   limite_s=20.0, terminal=terminal, **opcoes)
    return resultado, terminal.getvalue()


def linhas_de_imagem(texto: str) -> list[str]:
    """Linhas da tabela IMAGENS com tempo de reconstrução (as imagens prontas)."""
    depois = texto.split("IMAGENS", 1)[1].splitlines()
    return [l for l in depois if re.search(r"\d+/\d+\s+[\d,]+ s\s+[\d,]+ s", l)]


def envios(saida: Path) -> list[dict]:
    return [json.loads(l) for l in (saida / "cliente" / "envios.jsonl").read_text().splitlines()]


# Filtro do cliente N

def test_filtra_so_os_pedidos_do_cliente_n_na_ordem(dados):
    carga = nova_carga(dados, clientes=3, sinais=4)
    propria = pedidos_do_cliente(carga, 2)
    esperados = [p for p in carga["pedidos"] if p["client_id"] == "cliente-002"]
    assert propria["pedidos"] == esperados and len(esperados) == 4
    assert propria["semente"] == carga["semente"] and propria["modelos"] == carga["modelos"]
    assert len(carga["pedidos"]) == 12


def test_cliente_ausente_e_erro_com_os_disponiveis(dados):
    with pytest.raises(ValueError, match="cliente-001, cliente-002"):
        pedidos_do_cliente(nova_carga(dados, clientes=2), 7)


def test_envia_so_os_pedidos_do_cliente(dados, subir_stub, tmp_path):
    stub = subir_stub()
    caminho = gravar(nova_carga(dados), tmp_path)
    resultado, _ = rodar(caminho, 3, stub.url, dados, tmp_path / "c3")
    recebidos = [p["parametros"]["job_id"] for p in stub.estado.posts_recebidos]
    assert [r.rsplit("-", 1)[0] for r in recebidos] == ["c003-s0001", "c003-s0002", "c003-s0003"]
    assert all(re.fullmatch(r"c003-s000\d-\d{6}", r) for r in recebidos)
    assert {p["parametros"]["client_id"] for p in stub.estado.posts_recebidos} == {"cliente-003"}
    assert resultado["resumo"]["concluidos"] == 3


def test_crc_divergente_nao_envia_nada(dados, subir_stub, tmp_path):
    stub = subir_stub()
    carga = nova_carga(dados)
    carga["pedidos"][0]["crc32"] = "00000000"
    with pytest.raises(CargaInvalida):
        rodar(gravar(carga, tmp_path), 1, stub.url, dados, tmp_path / "c1")
    assert stub.estado.posts_recebidos == []


# Agenda relativa ao início de cada processo

def test_agenda_conta_do_inicio_de_cada_instancia(dados, subir_stub, tmp_path):
    stub = subir_stub()
    caminho = gravar(nova_carga(dados, intervalo=0.3), tmp_path)
    primeiro, _ = rodar(caminho, 1, stub.url, dados, tmp_path / "c1")
    time.sleep(0.5)
    segundo, _ = rodar(caminho, 2, stub.url, dados, tmp_path / "c2")
    assert segundo["resumo"]["t0_wall"] - primeiro["resumo"]["t0_wall"] > 0.5
    for resultado, saida in ((primeiro, tmp_path / "c1"), (segundo, tmp_path / "c2")):
        registros = envios(saida)
        assert len(registros) == 3
        for registro in registros:
            # Instante real do envio, medido do t0 desta instância, bate com o planejado na carga.
            relativo = registro["t_envio_wall"] - resultado["resumo"]["t0_wall"]
            assert relativo == pytest.approx(registro["planejado_s"], abs=0.1)
            assert 0 <= registro["atraso_s"] < 0.1


# Formatação das linhas

PEDIDO = {"job_id": "c001-s0002", "client_id": "cliente-001", "sinal": "g2", "modelo": "30x30", "ganho": True,
          "algoritmo": "cgne", "instante_planejado_s": 1.5}
# 2026-11-12 12:34:56.789 no fuso local do teste.
INSTANTE = time.mktime((2026, 11, 12, 12, 34, 56, 0, 0, -1)) + 0.789


def test_linha_de_envio_tem_os_campos_pedidos():
    registro = {"t_envio_wall": INSTANTE, "efetivo_s": 1.502, "status_http": 202, "duracao_post_s": 0.0123,
                "desfecho": "aceito", "erro": None}
    linha = linha_envio(PEDIDO, registro, "2/3", SEM_COR)
    for trecho in ("12:34:56", "2/3", "1,5 s", "g2", "30x30", "CGNE", "sim", "aceito (202)", "12,3 ms"):
        assert trecho in linha
    assert not ANSI.search(linha) and "\n" not in linha


def test_colunas_de_envio_ficam_alinhadas():
    curto = linha_envio(PEDIDO, {"t_envio_wall": INSTANTE, "efetivo_s": 1.5, "status_http": 202,
                                 "duracao_post_s": 0.002, "desfecho": "aceito", "erro": None}, "2/3", SEM_COR)
    longo = linha_envio(PEDIDO, {"t_envio_wall": INSTANTE, "efetivo_s": 31.25, "status_http": 503,
                                 "duracao_post_s": 0.0345, "desfecho": "rejeitado", "erro": "queue_full"},
                        "12/15", SEM_COR)
    assert curto.index("g2") == longo.index("g2") and curto.index("ms") == longo.index("ms")


def test_linha_de_envio_recusado_e_sem_resposta():
    recusado = linha_envio({**PEDIDO, "ganho": False},
                           {"t_envio_wall": INSTANTE, "efetivo_s": 1.5, "status_http": 503, "duracao_post_s": 0.002,
                            "desfecho": "rejeitado", "erro": "queue_full"}, "2/3", SEM_COR)
    assert "fila cheia (503)" in recusado and " não " in recusado
    caido = linha_envio(PEDIDO, {"t_envio_wall": INSTANTE, "efetivo_s": 1.5, "status_http": None,
                                 "duracao_post_s": 0.001, "desfecho": "erro_transporte", "erro": "ConnectError"},
                        "2/3", SEM_COR)
    assert "sem resposta (ConnectError)" in caido


def test_linha_de_progresso_conta_estados():
    linha = linha_progresso(INSTANTE, 4, {"prontas": 2, "na_fila": 1, "reconstruindo": 1, "falhas": 0, "sem_resposta": 0},
                            total=4, pintar=SEM_COR)
    assert "12:34:56" in linha and "consulta 4: 2 de 4 prontas, 1 na fila, 1 reconstruindo" in linha
    assert "falha" not in linha
    com_falha = linha_progresso(INSTANTE, 1, {"prontas": 0, "na_fila": 0, "reconstruindo": 0, "falhas": 1, "sem_resposta": 2},
                                total=3, pintar=SEM_COR)
    assert "1 com falha" in com_falha and "2 sem resposta" in com_falha and "na fila" not in com_falha


def test_linha_de_imagem_pronta_e_de_falha():
    job = {"queue_wait_s": 0.0123, "duration_s": 0.4567, "iterations": 10, "stop_reason": "max_iterations"}
    pronta = linha_desfecho(INSTANTE, "2/3", "done", job, None, SEM_COR)
    for trecho in ("12:34:56", "2/3", "0,012 s", "0,457 s", "10 (limite)"):
        assert trecho in pronta
    convergiu = linha_desfecho(INSTANTE, "2/3", "done", {**job, "iterations": 4, "stop_reason": "tolerance"}, None,
                               SEM_COR)
    assert "4 (convergiu)" in convergiu
    falha = linha_desfecho(INSTANTE, "3/3", "failed", {"error": "numerical_failure"}, "numerical_failure", SEM_COR)
    assert "falhou: numerical_failure" in falha
    sem_fim = linha_desfecho(INSTANTE, "3/3", "sem_conclusao", None, None, SEM_COR)
    assert "não terminou" in sem_fim


def test_resumo_mostra_contagens_e_tempos():
    resumo = {"pedidos": 3, "nao_enviados": 0, "concluidos": 2, "rejeitados": 1, "erros_http": 0, "falhas": 0,
              "sem_conclusao": 0, "erros_download": 0, "erros_transporte": 0, "t0_wall": 100.0, "fim_wall": 104.25}
    jobs = [{"queue_wait_s": 0.1, "duration_s": 0.5}, {"queue_wait_s": 0.3, "duration_s": 0.7}]
    linhas = linhas_resumo("cliente-001", resumo, jobs, Path("/x/relatorio_cliente.html"), SEM_COR)
    texto = "\n".join(linhas)
    assert "RESUMO DO CLIENTE 1" in texto
    assert re.search(r"Imagens prontas\s+2 de 3", texto) and re.search(r"Recusadas pelo servidor\s+1", texto)
    for trecho in ("4,25 s", "0,800 s (0,200 s na fila + 0,600 s reconstruindo)", "/x/relatorio_cliente.html"):
        assert trecho in texto
    assert "Com falha" not in texto


def test_conflito_de_id_aparece_como_id_ja_usado():
    linha = linha_envio(PEDIDO, {"t_envio_wall": INSTANTE, "efetivo_s": 1.5, "status_http": 409,
                                 "duracao_post_s": 0.002, "desfecho": "erro_http", "erro": "job_conflict"},
                        "2/3", SEM_COR)
    assert "id já usado (409)" in linha


def test_cor_so_quando_ligada():
    registro = {"t_envio_wall": INSTANTE, "efetivo_s": 1.5, "status_http": 202, "duracao_post_s": 0.01,
                "desfecho": "aceito", "erro": None}
    colorida = linha_envio(PEDIDO, registro, "2/3", COM_COR)
    assert ANSI.search(colorida)
    assert ANSI.sub("", colorida) == linha_envio(PEDIDO, registro, "2/3", SEM_COR)


def test_deteccao_de_cor():
    class Tty(io.StringIO):
        def isatty(self):
            return True

    assert cor_ativa("auto", Tty(), {"TERM": "xterm-256color"}) is True
    assert cor_ativa("auto", io.StringIO(), {"TERM": "xterm-256color"}) is False
    assert cor_ativa("auto", Tty(), {"TERM": "xterm", "NO_COLOR": "1"}) is False
    assert cor_ativa("auto", Tty(), {"TERM": "dumb"}) is False
    assert cor_ativa("sim", io.StringIO(), {}) is True
    assert cor_ativa("nao", Tty(), {"TERM": "xterm"}) is False


# Fluxo completo com o stub

def test_mesma_carga_duas_vezes_no_mesmo_servidor_reconstroi_de_novo(dados, subir_stub, tmp_path):
    stub = subir_stub(duracao_s=0.05)
    caminho = gravar(nova_carga(dados), tmp_path)
    primeira, _ = rodar(caminho, 1, stub.url, dados, tmp_path / "r1", carimbo="100000")
    segunda, texto = rodar(caminho, 1, stub.url, dados, tmp_path / "r2", carimbo="100001")
    for resultado in (primeira, segunda):
        assert resultado["resumo"]["aceitos"] == 3 and resultado["resumo"]["concluidos"] == 3
    assert all(e["status_http"] == 202 for e in envios(tmp_path / "r2"))
    assert "já recebido" not in texto and "409" not in texto
    ids = [p["parametros"]["job_id"] for p in stub.estado.posts_recebidos]
    assert len(ids) == 6 and len(set(ids)) == 6


def test_terminal_relatorio_e_registros_com_stub(dados, subir_stub, tmp_path):
    stub = subir_stub(duracao_s=0.1)
    saida = tmp_path / "c1"
    resultado, texto = rodar(gravar(nova_carga(dados), tmp_path), 1, stub.url, dados, saida)
    linhas = texto.splitlines()
    assert "Cliente 1 → servidor" in texto and "3 sinais, enviados entre" in texto
    assert sum("aceito (202)" in l for l in linhas) == 3
    assert len(linhas_de_imagem(texto)) == 3
    assert any("consulta" in l and "3 de 3 prontas" in l for l in linhas)
    # Todos os envios aparecem antes da tabela de imagens.
    assert max(i for i, l in enumerate(linhas) if "aceito (202)" in l) < linhas.index("IMAGENS")
    assert "Os 3 envios terminaram" in texto
    assert re.search(r"Imagens prontas\s+3 de 3", texto) and not ANSI.search(texto)
    html = (saida / "relatorio_cliente.html").read_text(encoding="utf-8")
    assert html.count('src="data:image/png;base64,') == 3 and "cliente-001" in html and "c002-" not in html
    carga_propria = json.loads((saida / "carga.json").read_text())
    assert {p["client_id"] for p in carga_propria["pedidos"]} == {"cliente-001"}
    registro = json.loads((saida / "execucao.json").read_text())
    assert registro["implementacao"] == "python" and registro["cliente"] == "cliente-001"
    assert resultado["relatorio"] == saida / "relatorio_cliente.html"


def test_recusa_pasta_de_saida_ja_usada(dados, subir_stub, tmp_path):
    stub = subir_stub()
    caminho = gravar(nova_carga(dados, sinais=1), tmp_path)
    rodar(caminho, 1, stub.url, dados, tmp_path / "c1")
    with pytest.raises(FileExistsError):
        rodar(caminho, 1, stub.url, dados, tmp_path / "c1")


def test_servidor_fora_do_ar_sai_com_erro_claro(dados, tmp_path, capsys):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    caminho = gravar(nova_carga(dados, sinais=1), tmp_path)
    codigo = main(["--carga", str(caminho), "--cliente", "1", "--servidor", f"http://127.0.0.1:{porta}",
                   "--saida", str(tmp_path / "c1"), "--dados", str(dados), "--cor", "nao"])
    assert codigo == 2
    assert "não respondeu" in capsys.readouterr().err
    assert not (tmp_path / "c1" / "cliente").exists()


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _encerrar(processo: subprocess.Popen) -> None:
    if processo.poll() is None:
        processo.send_signal(signal.SIGTERM)
        try:
            processo.wait(15)
        except subprocess.TimeoutExpired:
            processo.kill()
            processo.wait()


@pytest.mark.skipif(os.environ.get("CLIENTE_E2E_REAL") != "1", reason="sobe servidor real; defina CLIENTE_E2E_REAL=1")
@pytest.mark.skipif(not (DADOS_PADRAO / "manifesto.json").exists(), reason="dados/ não preparado")
def test_tres_terminais_com_servidor_python_real(tmp_path):
    caminho = tmp_path / "carga.json"
    gravar_carga(gerar_carga(DADOS_PADRAO, semente=42, clientes=3, sinais_por_cliente=3, modelos=["30x30"],
                             algoritmos=None, intervalo_max_s=0.3), caminho)
    porta = _porta_livre()
    url = f"http://127.0.0.1:{porta}"
    log = (tmp_path / "servidor.log").open("wb")
    servidor = subprocess.Popen(
        [sys.executable, "-m", "recon_py.servidor", "--porta", str(porta), "--dados", str(DADOS_PADRAO),
         "--saida", str(tmp_path / "servidor"), "--workers", "1", "--blas-threads", "1", "--aquecer", "30x30"],
        cwd=RAIZ, stdout=log, stderr=subprocess.STDOUT)
    clientes: list[subprocess.Popen] = []
    try:
        limite = time.monotonic() + 120
        while True:
            assert servidor.poll() is None, (tmp_path / "servidor.log").read_text()
            try:
                if httpx.get(f"{url}/info", timeout=2, trust_env=False).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            assert time.monotonic() < limite, "servidor não subiu"
            time.sleep(0.1)
        for numero in (1, 2, 3):
            clientes.append(subprocess.Popen(
                [sys.executable, "-m", "cliente.instancia", "--carga", str(caminho), "--cliente", str(numero),
                 "--servidor", url, "--saida", str(tmp_path / f"c{numero}"), "--cor", "nao"],
                cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True))
            time.sleep(0.4)  # terminais abertos em momentos diferentes
        saidas = [c.communicate(timeout=180)[0] for c in clientes]
        for numero, (cliente, texto) in enumerate(zip(clientes, saidas), start=1):
            assert cliente.returncode == 0, texto
            assert re.search(r"Imagens prontas\s+3 de 3", texto) and len(linhas_de_imagem(texto)) == 3
            html = (tmp_path / f"c{numero}" / "relatorio_cliente.html").read_text(encoding="utf-8")
            assert html.count('src="data:image/png;base64,') == 3
            registro = json.loads((tmp_path / f"c{numero}" / "execucao.json").read_text())
            assert registro["implementacao"] == "python"
        (tmp_path / "saida_terminais.txt").write_text("\n".join(saidas))
        print(saidas[0])
    finally:
        for cliente in clientes:
            _encerrar(cliente)
        _encerrar(servidor)
        log.close()
    with socket.socket() as s:
        assert s.connect_ex(("127.0.0.1", porta)) != 0, "porta do servidor continua ocupada"
