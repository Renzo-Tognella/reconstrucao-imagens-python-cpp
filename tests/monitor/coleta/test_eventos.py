from __future__ import annotations

import json
import os

from monitor.coleta.eventos import LeitorEventos


def _linha(n: int) -> str:
    return json.dumps({"event": "accepted", "job_id": f"j{n}", "t_mono": float(n)}) + "\n"


def test_arquivo_ausente_devolve_lista_vazia(tmp_path):
    assert LeitorEventos(tmp_path / "events.jsonl").ler_novos() == []


def test_le_so_o_que_chegou_depois_da_ultima_leitura(tmp_path):
    caminho = tmp_path / "events.jsonl"
    caminho.write_text(_linha(1) + _linha(2))
    leitor = LeitorEventos(caminho)
    assert [e["job_id"] for e in leitor.ler_novos()] == ["j1", "j2"]
    assert leitor.ler_novos() == []
    with caminho.open("a") as arquivo:
        arquivo.write(_linha(3))
    assert [e["job_id"] for e in leitor.ler_novos()] == ["j3"]


def test_linha_incompleta_no_fim_espera_o_resto(tmp_path):
    caminho = tmp_path / "events.jsonl"
    completa, parcial = _linha(1), _linha(2)
    caminho.write_text(completa + parcial[:10])
    leitor = LeitorEventos(caminho)
    assert [e["job_id"] for e in leitor.ler_novos()] == ["j1"]
    with caminho.open("a") as arquivo:
        arquivo.write(parcial[10:])
    assert [e["job_id"] for e in leitor.ler_novos()] == ["j2"]


def test_linha_invalida_no_meio_e_contada_e_ignorada(tmp_path):
    caminho = tmp_path / "events.jsonl"
    caminho.write_text(_linha(1) + "{quebrada\n" + _linha(2))
    leitor = LeitorEventos(caminho)
    assert [e["job_id"] for e in leitor.ler_novos()] == ["j1", "j2"]
    assert leitor.linhas_invalidas == 1


def test_arquivo_recriado_menor_volta_ao_inicio(tmp_path):
    caminho = tmp_path / "events.jsonl"
    caminho.write_text(_linha(1) + _linha(2))
    leitor = LeitorEventos(caminho)
    leitor.ler_novos()
    os.remove(caminho)
    caminho.write_text(_linha(9))
    assert [e["job_id"] for e in leitor.ler_novos()] == ["j9"]
