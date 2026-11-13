from __future__ import annotations

from pathlib import Path

from monitor.coleta.processo import escolher_pid, saida_na_linha

SERVIDOR_PY = ["python", "-m", "recon_py.servidor", "--porta", "8000", "--dados", "dados", "--saida", "res/py"]


def _proc(pid, ppid, cmdline):
    return {"pid": pid, "ppid": ppid, "cmdline": cmdline}


def test_escolhe_o_processo_com_a_porta_do_servidor():
    candidatos = [
        _proc(10, 1, ["zsh"]),
        _proc(20, 1, SERVIDOR_PY),
        _proc(30, 1, ["python", "-m", "monitor", "--servidor", "http://127.0.0.1:8000", "--porta", "8050"]),
    ]
    assert escolher_pid(candidatos, 8000, excluir=set()) == 20


def test_aceita_porta_no_formato_com_igual():
    candidatos = [_proc(20, 1, ["build/servidor_cpp", "--porta=8000"])]
    assert escolher_pid(candidatos, 8000, excluir=set()) == 20


def test_nao_confunde_porta_com_prefixo_comum():
    candidatos = [_proc(20, 1, ["build/servidor_cpp", "--porta", "80001"])]
    assert escolher_pid(candidatos, 8000, excluir=set()) is None


def test_prefere_o_ancestral_quando_um_lancador_tem_a_mesma_linha():
    # `uv run python -m recon_py.servidor ...` cria dois processos com a mesma porta; o pai soma o filho.
    candidatos = [_proc(21, 20, SERVIDOR_PY), _proc(20, 5, ["uv", "run", *SERVIDOR_PY])]
    assert escolher_pid(candidatos, 8000, excluir=set()) == 20


def test_ignora_processos_excluidos_e_linhas_ilegiveis():
    candidatos = [_proc(20, 1, SERVIDOR_PY), _proc(40, 1, None)]
    assert escolher_pid(candidatos, 8000, excluir={20}) is None


def test_entre_dois_servidores_soltos_prefere_o_que_parece_servidor():
    candidatos = [
        _proc(50, 1, ["python", "outro.py", "--porta", "8000"]),
        _proc(60, 1, SERVIDOR_PY),
    ]
    assert escolher_pid(candidatos, 8000, excluir=set()) == 60


def test_saida_relativa_e_resolvida_pelo_diretorio_do_processo():
    assert saida_na_linha(SERVIDOR_PY, Path("/projeto")) == Path("/projeto/res/py")
    assert saida_na_linha(["x", "--saida=/abs/s"], Path("/projeto")) == Path("/abs/s")
    assert saida_na_linha(["x", "--porta", "1"], Path("/projeto")) is None
