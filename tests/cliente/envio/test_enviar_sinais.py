import asyncio
import json
import time
import zlib

import pytest
from PIL import Image

from cliente.carga.manifesto import gerar_carga
from cliente.comum.registros import ler_jsonl
from cliente.envio.enviar_sinais import CargaInvalida, executar_carga


def nova_carga(dados, clientes=3, sinais=3, intervalo=0.02, semente=42):
    return gerar_carga(dados, semente=semente, clientes=clientes, sinais_por_cliente=sinais,
                       algoritmos=None, intervalo_max_s=intervalo)


def rodar(carga, stub_url, dados, saida, **opcoes):
    opcoes = {"limite_s": 10.0, "intervalo_consulta_s": 0.05, **opcoes}
    return asyncio.run(executar_carga(carga, url=stub_url, dados=dados, saida=saida, **opcoes))


def envios(saida):
    return {e["job_id"]: e for e in ler_jsonl(saida / "envios.jsonl")[0]}


def desfechos(saida):
    return {e["job_id"]: e for e in ler_jsonl(saida / "desfechos.jsonl")[0]}


def test_todos_os_pedidos_chegam_ao_servidor_e_terminam(dados, subir_stub, tmp_path):
    stub = subir_stub(workers=2)
    carga = nova_carga(dados)
    saida = tmp_path / "cli"
    resumo = rodar(carga, stub.url, dados, saida)
    assert resumo["aceitos"] == 9 and resumo["concluidos"] == 9
    assert set(envios(saida)) == {p["job_id"] for p in carga["pedidos"]}
    assert {e["status_http"] for e in envios(saida).values()} == {202}
    assert {d["desfecho"] for d in desfechos(saida).values()} == {"done"}


def test_corpo_enviado_tem_o_crc_do_arquivo_de_carga(dados, subir_stub, tmp_path):
    stub = subir_stub()
    carga = nova_carga(dados)
    rodar(carga, stub.url, dados, tmp_path / "cli")
    por_job = {r["parametros"]["job_id"]: r for r in stub.estado.posts_recebidos}
    for pedido in carga["pedidos"]:
        recebido = por_job[pedido["job_id"]]
        assert f"{recebido['crc']:08x}" == pedido["crc32"]
        assert recebido["parametros"]["gain"] == ("1" if pedido["ganho"] else "0")
        assert recebido["parametros"]["model"] == pedido["modelo"]
        assert recebido["parametros"]["algorithm"] == pedido["algoritmo"]
        assert recebido["parametros"]["signal_id"] == pedido["sinal"]
        assert recebido["parametros"]["client_id"] == pedido["client_id"]


def test_cada_conexao_leva_um_unico_pedido(dados, subir_stub, tmp_path):
    stub = subir_stub()
    rodar(nova_carga(dados), stub.url, dados, tmp_path / "cli")
    assert stub.estado.max_pedidos_por_conexao == 1
    assert set(stub.estado.cabecalhos_connection) == {"close"}


def test_envios_nao_esperam_a_reconstrucao(dados, subir_stub, tmp_path):
    stub = subir_stub(duracao_s=0.4)
    carga = nova_carga(dados, clientes=1, sinais=3, intervalo=0.0)
    saida = tmp_path / "cli"
    rodar(carga, stub.url, dados, saida)
    assert max(e["efetivo_s"] for e in envios(saida).values()) < 0.4


def test_post_lento_nao_atrasa_o_proximo_envio_do_mesmo_cliente(dados, subir_stub, tmp_path):
    stub = subir_stub(atraso_post_s=0.4)
    carga = nova_carga(dados, clientes=1, sinais=3)
    for indice, pedido in enumerate(carga["pedidos"]):
        pedido["instante_planejado_s"] = 0.02 + 0.05 * indice
    saida = tmp_path / "cli"
    rodar(carga, stub.url, dados, saida)
    efetivos = sorted(e["efetivo_s"] for e in envios(saida).values())
    assert efetivos[2] - efetivos[0] < 0.3
    assert all(e["duracao_post_s"] >= 0.4 for e in envios(saida).values())


def test_clientes_partem_do_mesmo_instante(dados, subir_stub, tmp_path):
    stub = subir_stub()
    carga = nova_carga(dados, clientes=3, sinais=1)
    for pedido in carga["pedidos"]:
        pedido["instante_planejado_s"] = 0.05
    saida = tmp_path / "cli"
    rodar(carga, stub.url, dados, saida)
    efetivos = [e["efetivo_s"] for e in envios(saida).values()]
    assert max(efetivos) - min(efetivos) < 0.05


def test_registro_tem_planejado_efetivo_e_atraso(dados, subir_stub, tmp_path):
    stub = subir_stub()
    saida = tmp_path / "cli"
    rodar(nova_carga(dados), stub.url, dados, saida)
    for registro in envios(saida).values():
        assert registro["atraso_s"] == pytest.approx(registro["efetivo_s"] - registro["planejado_s"])
        assert registro["t_envio_wall"] > 0


def test_503_e_rejeitado_sem_retry(dados, subir_stub, tmp_path):
    stub = subir_stub(fila_max=1, duracao_s=0.2)
    carga = nova_carga(dados, clientes=2, sinais=4, intervalo=0.0)
    saida = tmp_path / "cli"
    resumo = rodar(carga, stub.url, dados, saida)
    assert len(stub.estado.posts_recebidos) == len(carga["pedidos"])
    rejeitados = [e for e in envios(saida).values() if e["status_http"] == 503]
    assert rejeitados and all(e["desfecho"] == "rejeitado" and e["erro"] == "queue_full" for e in rejeitados)
    assert resumo["rejeitados"] == len(rejeitados)
    assert not set(e["job_id"] for e in rejeitados) & set(desfechos(saida))


def test_baixa_imagem_vetor_e_metadados_e_gera_png_ampliado(dados, subir_stub, tmp_path):
    stub = subir_stub()
    carga = nova_carga(dados, clientes=1, sinais=1)
    saida = tmp_path / "cli"
    rodar(carga, stub.url, dados, saida)
    job_id = carga["pedidos"][0]["job_id"]
    pasta = saida / "jobs"
    assert json.loads((pasta / f"{job_id}.json").read_text())["status"] == "done"
    assert (pasta / f"{job_id}.pgm").read_bytes() == stub.estado.imagens[job_id]
    assert (pasta / f"{job_id}.f64").read_bytes() == stub.estado.vetores[job_id]
    with Image.open(pasta / f"{job_id}.png") as png:
        assert png.format == "PNG"
        escala = png.width // 2
        assert escala > 1 and png.size == (2 * escala, 2 * escala)
        assert png.getpixel((escala, 0)) == 7
        assert png.getpixel((2 * escala - 1, escala - 1)) == 7


def test_tarefa_com_falha_nao_baixa_imagem_e_fica_identificada(dados, subir_stub, tmp_path):
    stub = subir_stub(sinais_com_falha=("g1", "g2"))
    carga = nova_carga(dados, clientes=1, sinais=1)
    saida = tmp_path / "cli"
    resumo = rodar(carga, stub.url, dados, saida)
    job_id = carga["pedidos"][0]["job_id"]
    assert desfechos(saida)[job_id]["desfecho"] == "failed"
    assert desfechos(saida)[job_id]["erro"] == "numerical_failure"
    assert not (saida / "jobs" / f"{job_id}.pgm").exists()
    assert (saida / "jobs" / f"{job_id}.json").exists()
    assert resumo["falhas"] == 1 and resumo["concluidos"] == 0


def test_limite_de_espera_marca_sem_conclusao(dados, subir_stub, tmp_path):
    stub = subir_stub(duracao_s=30.0)
    carga = nova_carga(dados, clientes=1, sinais=2, intervalo=0.0)
    saida = tmp_path / "cli"
    resumo = rodar(carga, stub.url, dados, saida, limite_s=0.2)
    assert resumo["sem_conclusao"] == 2
    assert {d["desfecho"] for d in desfechos(saida).values()} == {"sem_conclusao"}
    assert {d["ultimo_status"] for d in desfechos(saida).values()} <= {"queued", "running"}


def test_servidor_fora_do_ar_vira_erro_de_transporte(dados, subir_stub, tmp_path):
    stub = subir_stub()
    url = stub.url
    stub.http.shutdown()
    stub.http.server_close()
    carga = nova_carga(dados, clientes=1, sinais=2, intervalo=0.0)
    saida = tmp_path / "cli"
    try:
        resumo = rodar(carga, url, dados, saida, limite_s=0.2)
    finally:
        stub.http = type("Nada", (), {"shutdown": lambda s: None, "server_close": lambda s: None})()
    assert resumo["erros_transporte"] == 2
    assert all(e["status_http"] is None and e["erro"] for e in envios(saida).values())
    assert {e["desfecho"] for e in envios(saida).values()} == {"erro_transporte"}


def test_corpo_que_nao_bate_com_o_crc_impede_o_inicio(dados, subir_stub, tmp_path):
    stub = subir_stub()
    carga = nova_carga(dados)
    carga["pedidos"][0]["crc32"] = f"{zlib.crc32(b'outro'):08x}"
    with pytest.raises(CargaInvalida, match=carga["pedidos"][0]["job_id"]):
        rodar(carga, stub.url, dados, tmp_path / "cli")
    assert stub.estado.posts_recebidos == []


def test_vigia_interrompe_e_registra_o_que_nao_foi_enviado(dados, subir_stub, tmp_path):
    stub = subir_stub()
    carga = nova_carga(dados, clientes=1, sinais=3)
    for indice, pedido in enumerate(carga["pedidos"]):
        pedido["instante_planejado_s"] = 0.0 if indice == 0 else 30.0
    saida = tmp_path / "cli"
    chamadas = []

    def vigia():
        chamadas.append(1)
        return "memória baixa" if len(chamadas) >= 8 else None

    resumo = rodar(carga, stub.url, dados, saida, vigia=vigia, intervalo_vigia_s=0.05)
    assert resumo["interrompido"] == "memória baixa"
    assert sum(1 for e in envios(saida).values() if e["desfecho"] == "nao_enviado") == 2


def test_falha_no_vigia_interrompe_em_vez_de_desligar_a_protecao(dados, subir_stub, tmp_path):
    stub = subir_stub()
    carga = nova_carga(dados, clientes=1, sinais=2, intervalo=0.0)

    def vigia():
        raise OSError("sem acesso")

    resumo = rodar(carga, stub.url, dados, tmp_path / "cli", vigia=vigia, intervalo_vigia_s=0.05)
    assert "sem acesso" in resumo["interrompido"]


def test_vigia_lento_nao_atrasa_os_envios(dados, subir_stub, tmp_path):
    stub = subir_stub()
    carga = nova_carga(dados, clientes=1, sinais=3)
    for indice, pedido in enumerate(carga["pedidos"]):
        pedido["instante_planejado_s"] = 0.05 * indice
    saida = tmp_path / "cli"

    def vigia():
        time.sleep(0.5)

    rodar(carga, stub.url, dados, saida, vigia=vigia, intervalo_vigia_s=0.01)
    assert max(e["atraso_s"] for e in envios(saida).values()) < 0.2


def test_rajada_de_agenda_zero_envia_todos_sem_atraso_relevante(dados, subir_stub, tmp_path):
    stub = subir_stub(workers=2)
    carga = nova_carga(dados, clientes=3, sinais=5, intervalo=0.0)
    saida = tmp_path / "cli"
    resumo = rodar(carga, stub.url, dados, saida)
    assert resumo["concluidos"] == 15
    registros = envios(saida).values()
    assert {e["planejado_s"] for e in registros} == {0.0}
    assert max(e["efetivo_s"] for e in registros) < 0.5
