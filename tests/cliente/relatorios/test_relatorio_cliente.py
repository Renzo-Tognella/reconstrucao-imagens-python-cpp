import base64
import csv
import json
from datetime import datetime

from cliente.relatorios.relatorio_cliente import COLUNAS, gerar_relatorio, main
from tests.cliente.apoio import criar_execucao, envio, job

PNG_1X1 = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGNgAAAAAgABc3UBGAAAAABJRU5ErkJggg==")


def montar(pasta):
    pedidos = [
        {"job_id": "ok", "client_id": "cli-1", "modelo": "30x30", "sinal": "g1", "ganho": True, "algoritmo": "cgnr"},
        {"job_id": "rej", "client_id": "cli-1", "modelo": "30x30", "sinal": "g2", "ganho": False, "algoritmo": "cgne"},
        {"job_id": "fal", "client_id": "cli-2", "modelo": "30x30", "sinal": "g2", "ganho": False, "algoritmo": "cgne"},
        {"job_id": "lim", "client_id": "cli-2", "modelo": "30x30", "sinal": "g1", "ganho": False, "algoritmo": "cgnr"},
        {"job_id": "nao", "client_id": "cli-3", "modelo": "30x30", "sinal": "g1", "ganho": False, "algoritmo": "cgnr"},
        {"job_id": "tra", "client_id": "cli-3", "modelo": "30x30", "sinal": "g1", "ganho": False, "algoritmo": "cgnr"},
    ]
    envios = [envio("ok"), envio("rej", status=503, desfecho="rejeitado"), envio("fal"), envio("lim"),
              envio("nao", status=None, desfecho="nao_enviado", atraso=None),
              envio("tra", status=None, desfecho="erro_transporte")]
    desfechos = [{"job_id": "ok", "desfecho": "done", "ultimo_status": "done", "erro": None},
                 {"job_id": "fal", "desfecho": "failed", "ultimo_status": "failed", "erro": "numerical_failure"},
                 {"job_id": "lim", "desfecho": "sem_conclusao", "ultimo_status": "running", "erro": None}]
    criar_execucao(pasta, envios=envios, desfechos=desfechos)
    (pasta / "carga.json").write_text(json.dumps({"semente": 42, "pedidos": pedidos}))
    (pasta / "cliente" / "jobs" / "ok.json").write_text(json.dumps(job("ok")))
    (pasta / "cliente" / "jobs" / "ok.png").write_bytes(PNG_1X1)
    (pasta / "cliente" / "jobs" / "fal.json").write_text(json.dumps(job("fal", status="failed", duracao=None)))
    return pasta


def analisar(caminho):
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        assert leitor.fieldnames == COLUNAS
        return {linha["job_id"]: linha for linha in leitor}


def test_imagem_concluida_tem_todos_os_campos_do_enunciado(tmp_path):
    pasta = montar(tmp_path / "x")
    destino = gerar_relatorio(pasta)
    assert destino == pasta / "relatorio_cliente.csv"
    linha = analisar(destino)["ok"]
    assert linha["cliente"] == "cli-1" and linha["sinal"] == "g1" and linha["algoritmo"] == "cgnr"
    assert linha["modelo"] == "30x30" and linha["ganho"] == "sim"
    def local(texto):
        return datetime.fromisoformat(texto).astimezone().isoformat(timespec="milliseconds")

    assert linha["inicio"] == local("2026-11-04T12:00:00.500+00:00")
    assert linha["fim"] == local("2026-11-04T12:00:01.500+00:00")
    assert linha["iteracoes"] == "10" and linha["parada"] == "max_iterations"
    assert linha["situacao"] == "concluída"
    assert (pasta / linha["imagem"]).read_bytes() == PNG_1X1


def test_rejeitados_e_falhos_ficam_identificados_sem_imagem(tmp_path):
    linhas = analisar(gerar_relatorio(montar(tmp_path / "x")))
    assert "rejeitado" in linhas["rej"]["situacao"] and "503" in linhas["rej"]["situacao"]
    assert "falhou" in linhas["fal"]["situacao"] and "numerical_failure" in linhas["fal"]["situacao"]
    assert "sem conclusão" in linhas["lim"]["situacao"] and "running" in linhas["lim"]["situacao"]
    assert "não enviado" in linhas["nao"]["situacao"]
    assert "erro de transporte" in linhas["tra"]["situacao"]
    for job_id in ("rej", "fal", "lim", "nao", "tra"):
        assert linhas[job_id]["imagem"] == "" and linhas[job_id]["situacao"] != "concluída"


def test_done_sem_png_nao_passa_por_sucesso(tmp_path):
    pasta = montar(tmp_path / "x")
    (pasta / "cliente" / "jobs" / "ok.png").unlink()
    linha = analisar(gerar_relatorio(pasta))["ok"]
    assert linha["situacao"] == "imagem ausente no disco" and linha["imagem"] == ""


def test_todo_pedido_da_carga_aparece_mesmo_sem_registro_de_envio(tmp_path):
    pasta = montar(tmp_path / "x")
    carga = json.loads((pasta / "carga.json").read_text())
    carga["pedidos"].append({"job_id": "sumiu", "client_id": "cli-4", "modelo": "30x30", "sinal": "g1", "ganho": False, "algoritmo": "cgnr"})
    (pasta / "carga.json").write_text(json.dumps(carga))
    linhas = analisar(gerar_relatorio(pasta))
    assert len(linhas) == 7 and "sem registro" in linhas["sumiu"]["situacao"]


def test_texto_com_virgula_e_aspas_continua_numa_celula(tmp_path):
    pasta = montar(tmp_path / "x")
    desfechos = (pasta / "cliente" / "desfechos.jsonl").read_text().replace("numerical_failure", 'erro, com \\"aspas\\"')
    (pasta / "cliente" / "desfechos.jsonl").write_text(desfechos)
    linha = analisar(gerar_relatorio(pasta))["fal"]
    assert linha["situacao"] == 'falhou (erro, com "aspas")' and linha["cliente"] == "cli-2"


def test_linha_de_comando(tmp_path):
    pasta = montar(tmp_path / "x")
    assert main(["--execucao", str(pasta)]) == 0
    assert (pasta / "relatorio_cliente.csv").exists() and not (pasta / "relatorio_cliente.html").exists()
