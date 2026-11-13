import json
import re
import zlib

import numpy as np
import pytest

from cliente.carga.ganho import aplicar_ganho
from cliente.carga.manifesto import gerar_carga, main
from cliente.carga.sinais import corpo_do_pedido
from tests.cliente.apoio import criar_dados

ID_VALIDO = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def gerar(dados, **ajustes):
    opcoes = dict(semente=42, clientes=3, sinais_por_cliente=15, algoritmos=None, intervalo_max_s=5.0)
    return gerar_carga(dados, **{**opcoes, **ajustes})


def test_mesma_semente_gera_arquivo_identico(tmp_path):
    dados = criar_dados(tmp_path / "dados")
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    argumentos = ["--semente", "7", "--clientes", "3", "--sinais-por-cliente", "15", "--dados", str(dados)]
    main([*argumentos, "--saida", str(a)])
    main([*argumentos, "--saida", str(b)])
    assert a.read_bytes() == b.read_bytes()


def test_semente_diferente_muda_a_sequencia(tmp_path):
    dados = criar_dados(tmp_path / "dados")
    assert gerar(dados, semente=1)["pedidos"] != gerar(dados, semente=2)["pedidos"]


def test_quantidade_e_identificadores(tmp_path):
    carga = gerar(criar_dados(tmp_path / "dados"), clientes=4, sinais_por_cliente=16)
    pedidos = carga["pedidos"]
    assert len(pedidos) == 4 * 16
    assert len({p["job_id"] for p in pedidos}) == len(pedidos)
    assert len({p["client_id"] for p in pedidos}) == 4
    for pedido in pedidos:
        assert ID_VALIDO.match(pedido["job_id"]) and ID_VALIDO.match(pedido["client_id"])


def test_atrasos_ficam_no_intervalo_e_instante_e_acumulado(tmp_path):
    carga = gerar(criar_dados(tmp_path / "dados"), intervalo_max_s=0.5, clientes=2, sinais_por_cliente=50)
    for cliente in {p["client_id"] for p in carga["pedidos"]}:
        acumulado = 0.0
        for pedido in (p for p in carga["pedidos"] if p["client_id"] == cliente):
            assert 0 <= pedido["atraso_s"] <= 0.5
            acumulado += pedido["atraso_s"]
            assert pedido["instante_planejado_s"] == pytest.approx(acumulado, abs=1e-6)


def test_sorteio_cobre_ganho_algoritmo_e_sinal(tmp_path):
    pedidos = gerar(criar_dados(tmp_path / "dados"), sinais_por_cliente=60)["pedidos"]
    assert {p["ganho"] for p in pedidos} == {True, False}
    assert {p["algoritmo"] for p in pedidos} == {"cgnr", "cgne"}
    assert {p["sinal"] for p in pedidos} == {"g1", "g2"}


def test_modelo_novo_no_manifesto_entra_sem_mudar_codigo(tmp_path):
    dados = criar_dados(tmp_path / "dados", modelos={"30x30": (4, 3, 2, 2), "60x60": (5, 2, 2, 3)})
    pedidos = gerar(dados, sinais_por_cliente=60)["pedidos"]
    assert {p["modelo"] for p in pedidos} == {"30x30", "60x60"}
    assert {p["tamanho_bytes"] for p in pedidos if p["modelo"] == "60x60"} == {5 * 2 * 8}


def test_algoritmos_podem_ser_restritos_e_desconhecido_e_erro(tmp_path):
    dados = criar_dados(tmp_path / "dados")
    assert {p["algoritmo"] for p in gerar(dados, algoritmos=["cgne"])["pedidos"]} == {"cgne"}
    with pytest.raises(ValueError, match="sirt"):
        gerar(dados, algoritmos=["sirt"])


def test_crc_e_do_corpo_final_com_ganho_aplicado(tmp_path):
    dados = criar_dados(tmp_path / "dados")
    carga = gerar(dados, sinais_por_cliente=40)
    modelo = carga["modelos"]["30x30"]
    for pedido in carga["pedidos"]:
        sinal = np.fromfile(dados / "sinais" / "30x30" / f"{pedido['sinal']}.f64", dtype="<f8")
        if pedido["ganho"]:
            sinal = aplicar_ganho(sinal, modelo["S"], modelo["N"])
        corpo = sinal.astype("<f8").tobytes()
        assert pedido["crc32"] == f"{zlib.crc32(corpo):08x}"
        assert corpo_do_pedido(dados, pedido) == corpo


def test_arquivo_registra_o_necessario_para_reproduzir(tmp_path):
    dados = criar_dados(tmp_path / "dados")
    saida = tmp_path / "sub" / "carga.json"
    main(["--semente", "42", "--clientes", "2", "--sinais-por-cliente", "2", "--intervalo-max", "1.5",
          "--algoritmos", "cgnr", "--saida", str(saida), "--dados", str(dados)])
    carga = json.loads(saida.read_text())
    assert carga["semente"] == 42
    assert carga["parametros"] == {"clientes": 2, "sinais_por_cliente": 2, "algoritmos": ["cgnr"], "intervalo_max_s": 1.5}
    assert carga["modelos"]["30x30"]["sha256"]
    assert set(carga["modelos"]["30x30"]["sinais"]) == {"g1", "g2"}
    assert carga["gerador"].startswith("numpy.random.default_rng")
    assert carga["versao_numpy"] == np.__version__
    assert carga["atende_minimo_enunciado"] is False


def test_minimo_do_enunciado_e_registrado(tmp_path):
    carga = gerar(criar_dados(tmp_path / "dados"))
    assert carga["atende_minimo_enunciado"] is True


def test_intervalo_zero_gera_rajada_com_a_mesma_sequencia(tmp_path):
    dados = criar_dados(tmp_path / "dados")
    saida = tmp_path / "rajada.json"
    main(["--semente", "42", "--clientes", "3", "--sinais-por-cliente", "15", "--intervalo-max", "0",
          "--saida", str(saida), "--dados", str(dados)])
    rajada = json.loads(saida.read_text())
    assert rajada["parametros"]["intervalo_max_s"] == 0
    assert all(p["atraso_s"] == 0 and p["instante_planejado_s"] == 0 for p in rajada["pedidos"])
    agendada = gerar(dados)["pedidos"]
    chaves = ("job_id", "client_id", "modelo", "sinal", "ganho", "algoritmo", "crc32")
    assert [[p[c] for c in chaves] for p in rajada["pedidos"]] == [[p[c] for c in chaves] for p in agendada]


def test_modelos_restringe_o_sorteio(tmp_path):
    dados = criar_dados(tmp_path / "dados")
    nome = next(iter(json.loads((dados / "manifesto.json").read_text())["modelos"]))
    carga = gerar(dados, modelos=[nome])
    assert {pedido["modelo"] for pedido in carga["pedidos"]} == {nome}
    assert list(carga["modelos"]) == [nome]


def test_modelo_desconhecido_e_erro(tmp_path):
    with pytest.raises(ValueError, match="99x99"):
        gerar(criar_dados(tmp_path / "dados"), modelos=["99x99"])


# Hash de parametros + pedidos gerados antes de existir --ganho (semente 7, dois modelos sintéticos).
# Se mudar, cargas já gravadas deixam de ser reproduzidas byte a byte.
HASH_SORTEADO_ANTES_DO_GANHO = "6e731df3acfe62eba9be68e060ce58c0bc33b38238e4c250f9e5a82144d734f5"


def _dados_dois_modelos(tmp_path):
    return criar_dados(tmp_path / "dados", modelos={"30x30": (4, 3, 2, 2), "60x60": (5, 2, 2, 3)})


def test_ganho_sorteado_reproduz_cargas_antigas(tmp_path):
    import hashlib
    dados = _dados_dois_modelos(tmp_path)
    for carga in (gerar(dados, semente=7), gerar(dados, semente=7, ganho="sorteado")):
        conteudo = json.dumps({"parametros": carga["parametros"], "pedidos": carga["pedidos"]}, sort_keys=True)
        assert hashlib.sha256(conteudo.encode()).hexdigest() == HASH_SORTEADO_ANTES_DO_GANHO
        assert "ganho" not in carga["parametros"]


@pytest.mark.parametrize("modo, esperado", [("sim", True), ("nao", False)])
def test_ganho_fixo_muda_so_o_ganho_e_o_corpo(tmp_path, modo, esperado):
    dados = _dados_dois_modelos(tmp_path)
    sorteada = gerar(dados, semente=7, sinais_por_cliente=30)
    fixa = gerar(dados, semente=7, sinais_por_cliente=30, ganho=modo)
    assert {p["ganho"] for p in fixa["pedidos"]} == {esperado}
    assert fixa["parametros"]["ganho"] == modo
    chaves = ("job_id", "client_id", "modelo", "sinal", "algoritmo", "atraso_s", "instante_planejado_s")
    assert [[p[c] for c in chaves] for p in fixa["pedidos"]] == [[p[c] for c in chaves] for p in sorteada["pedidos"]]
    for pedido in fixa["pedidos"]:
        assert pedido["crc32"] == f"{zlib.crc32(corpo_do_pedido(dados, pedido)):08x}"


def test_ganho_fixo_e_deterministico_pela_linha_de_comando(tmp_path):
    dados = criar_dados(tmp_path / "dados")
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    argumentos = ["--semente", "3", "--clientes", "3", "--sinais-por-cliente", "15", "--ganho", "sim", "--dados", str(dados)]
    main([*argumentos, "--saida", str(a)])
    main([*argumentos, "--saida", str(b)])
    assert a.read_bytes() == b.read_bytes()
    assert {p["ganho"] for p in json.loads(a.read_text())["pedidos"]} == {True}


def test_ganho_invalido_e_erro(tmp_path):
    dados = criar_dados(tmp_path / "dados")
    with pytest.raises(ValueError, match="talvez"):
        gerar(dados, ganho="talvez")
    with pytest.raises(SystemExit):
        main(["--semente", "1", "--clientes", "1", "--sinais-por-cliente", "1", "--ganho", "talvez",
              "--saida", str(tmp_path / "x.json"), "--dados", str(dados)])


@pytest.mark.parametrize("lista, esperados", [("cgnr", {"cgnr"}), ("cgne", {"cgne"}), ("cgnr,cgne", {"cgnr", "cgne"})])
def test_algoritmos_e_modelos_pela_linha_de_comando(tmp_path, lista, esperados):
    dados = _dados_dois_modelos(tmp_path)
    saida = tmp_path / "carga.json"
    main(["--semente", "5", "--clientes", "3", "--sinais-por-cliente", "20", "--algoritmos", lista,
          "--modelos", "60x60", "--saida", str(saida), "--dados", str(dados)])
    carga = json.loads(saida.read_text())
    assert {p["algoritmo"] for p in carga["pedidos"]} == esperados
    assert {p["modelo"] for p in carga["pedidos"]} == {"60x60"}
    assert carga["parametros"]["algoritmos"] == lista.split(",")
