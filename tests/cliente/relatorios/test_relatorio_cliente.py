import base64
import json
from html.parser import HTMLParser

from cliente.relatorios.relatorio_cliente import gerar_relatorio, main
from tests.cliente.apoio import criar_execucao, envio, job

PNG_1X1 = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGNgAAAAAgABc3UBGAAAAABJRU5ErkJggg==")


class Linhas(HTMLParser):
    def __init__(self):
        super().__init__()
        self.linhas: dict[str, dict] = {}
        self.atual = None

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if tag == "tr" and "data-job" in atributos:
            self.atual = self.linhas.setdefault(atributos["data-job"], {"texto": "", "imgs": [], "classe": atributos.get("class", "")})
        if tag == "img" and self.atual is not None:
            self.atual["imgs"].append(atributos["src"])

    def handle_endtag(self, tag):
        if tag == "tr":
            self.atual = None

    def handle_data(self, data):
        if self.atual is not None:
            self.atual["texto"] += data + " "


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
    leitor = Linhas()
    leitor.feed(caminho.read_text(encoding="utf-8"))
    return leitor.linhas


def test_imagem_concluida_tem_todos_os_campos_do_enunciado(tmp_path):
    linhas = analisar(gerar_relatorio(montar(tmp_path / "x")))
    linha = linhas["ok"]
    for esperado in ("cli-1", "g1", "cgnr", "30x30", "2026-11-04T12:00:00.500Z", "2026-11-04T12:00:01.500Z",
                     "10", "max_iterations", "sim"):
        assert esperado in linha["texto"], esperado
    assert linha["imgs"][0] == "data:image/png;base64," + base64.b64encode(PNG_1X1).decode()


def test_relatorio_nao_referencia_arquivos_externos(tmp_path):
    html = gerar_relatorio(montar(tmp_path / "x")).read_text(encoding="utf-8")
    assert 'src="data:image/png;base64,' in html
    assert "src=\"http" not in html and "href=\"http" not in html and ".png\"" not in html


def test_rejeitados_e_falhos_ficam_identificados_sem_imagem(tmp_path):
    linhas = analisar(gerar_relatorio(montar(tmp_path / "x")))
    assert "rejeitado" in linhas["rej"]["texto"] and "503" in linhas["rej"]["texto"]
    assert "falhou" in linhas["fal"]["texto"] and "numerical_failure" in linhas["fal"]["texto"]
    assert "sem conclusão" in linhas["lim"]["texto"] and "running" in linhas["lim"]["texto"]
    assert "não enviado" in linhas["nao"]["texto"]
    assert "erro de transporte" in linhas["tra"]["texto"]
    for job_id in ("rej", "fal", "lim", "nao", "tra"):
        assert linhas[job_id]["imgs"] == []
        assert "problema" in linhas[job_id]["classe"]
        assert "concluída" not in linhas[job_id]["texto"]
    assert "concluída" in linhas["ok"]["texto"]


def test_done_sem_png_nao_passa_por_sucesso(tmp_path):
    pasta = montar(tmp_path / "x")
    (pasta / "cliente" / "jobs" / "ok.png").unlink()
    linha = analisar(gerar_relatorio(pasta))["ok"]
    assert "concluída" not in linha["texto"] and "problema" in linha["classe"]


def test_todo_pedido_da_carga_aparece_mesmo_sem_registro_de_envio(tmp_path):
    pasta = montar(tmp_path / "x")
    carga = json.loads((pasta / "carga.json").read_text())
    carga["pedidos"].append({"job_id": "sumiu", "client_id": "cli-4", "modelo": "30x30", "sinal": "g1", "ganho": False, "algoritmo": "cgnr"})
    (pasta / "carga.json").write_text(json.dumps(carga))
    linhas = analisar(gerar_relatorio(pasta))
    assert "sem registro" in linhas["sumiu"]["texto"]


def test_texto_do_servidor_e_escapado(tmp_path):
    pasta = montar(tmp_path / "x")
    malicioso = job("fal", status="failed", duracao=None)
    malicioso["error"] = "<script>alert(1)</script>"
    (pasta / "cliente" / "jobs" / "fal.json").write_text(json.dumps(malicioso))
    desfechos = (pasta / "cliente" / "desfechos.jsonl").read_text().replace("numerical_failure", "<script>alert(1)</script>")
    (pasta / "cliente" / "desfechos.jsonl").write_text(desfechos)
    assert "<script>" not in gerar_relatorio(pasta).read_text(encoding="utf-8")


def test_resumo_conta_cada_desfecho(tmp_path):
    html = gerar_relatorio(montar(tmp_path / "x")).read_text(encoding="utf-8")
    assert 'data-indicador="concluidas">1<' in html
    assert 'data-indicador="rejeitadas">1<' in html
    assert 'data-indicador="falhas">1<' in html
    assert 'data-indicador="outras">3<' in html


def test_linha_de_comando(tmp_path):
    pasta = montar(tmp_path / "x")
    assert main(["--execucao", str(pasta)]) == 0
    assert (pasta / "relatorio_cliente.html").exists()
