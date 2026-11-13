"""Acha o processo servidor pela linha de comando. No macOS, `net_connections` exige root, por isso não é usado."""
from __future__ import annotations

import os
from pathlib import Path

import psutil

NOMES_DE_SERVIDOR = ("recon_py.servidor", "servidor_cpp")


def _valor_da_opcao(cmdline: list[str], opcao: str) -> str | None:
    for indice, parte in enumerate(cmdline):
        if parte == opcao and indice + 1 < len(cmdline):
            return cmdline[indice + 1]
        if parte.startswith(opcao + "="):
            return parte.split("=", 1)[1]
    return None


def _usa_a_porta(cmdline: list[str] | None, porta: int) -> bool:
    return bool(cmdline) and _valor_da_opcao(cmdline, "--porta") == str(porta)


def escolher_pid(candidatos: list[dict], porta: int, excluir: set[int]) -> int | None:
    """Entre processos `{pid, ppid, cmdline}`, o que roda com `--porta <porta>`.

    Um lançador (`uv run ...`) repete a linha do filho: fica o ancestral, porque a medição soma os filhos.
    """
    com_porta = [c for c in candidatos if c["pid"] not in excluir and _usa_a_porta(c["cmdline"], porta)]
    pids = {c["pid"] for c in com_porta}
    raizes = [c for c in com_porta if c["ppid"] not in pids]
    if not raizes:
        return None

    def prioridade(candidato: dict) -> tuple[int, int]:
        linha = " ".join(candidato["cmdline"])
        parece_servidor = any(nome in linha for nome in NOMES_DE_SERVIDOR)
        return (0 if parece_servidor else 1, candidato["pid"])

    return min(raizes, key=prioridade)["pid"]


def saida_na_linha(cmdline: list[str], cwd: Path) -> Path | None:
    valor = _valor_da_opcao(cmdline, "--saida")
    if valor is None:
        return None
    caminho = Path(valor)
    return caminho if caminho.is_absolute() else cwd / caminho


def _proprios_e_ancestrais() -> set[int]:
    excluir = {os.getpid()}
    try:
        excluir.update(p.pid for p in psutil.Process().parents())
    except psutil.Error:
        pass
    return excluir


def descobrir_pid(porta: int) -> int | None:
    usuario = psutil.Process().username()
    candidatos = []
    for processo in psutil.process_iter(["pid", "ppid", "username", "cmdline"]):
        dados = processo.info
        if dados.get("username") == usuario:
            candidatos.append({"pid": dados["pid"], "ppid": dados["ppid"], "cmdline": dados.get("cmdline")})
    return escolher_pid(candidatos, porta, _proprios_e_ancestrais())


def saida_do_processo(pid: int) -> Path | None:
    """A pasta `--saida` com que o servidor foi iniciado, resolvida pelo diretório de trabalho dele."""
    try:
        processo = psutil.Process(pid)
        familia = [processo, *processo.children(recursive=True)]
        for membro in familia:
            saida = saida_na_linha(membro.cmdline(), Path(membro.cwd()))
            if saida is not None:
                return saida.resolve()
    except psutil.Error:
        return None
    return None
