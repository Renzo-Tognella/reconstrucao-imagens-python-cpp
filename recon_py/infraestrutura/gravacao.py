from __future__ import annotations

from pathlib import Path


def gravar_atomico(destino: Path, conteudo: bytes) -> None:
    temporario = destino.with_name(destino.name + ".tmp")
    try:
        temporario.write_bytes(conteudo)
        temporario.replace(destino)
    except BaseException:
        temporario.unlink(missing_ok=True)
        raise


class PastaDeResultados:
    def __init__(self, saida: Path) -> None:
        self._jobs = saida / "jobs"
        self._jobs.mkdir(parents=True, exist_ok=True)

    def caminho(self, job_id: str, extensao: str) -> Path:
        return self._jobs / f"{job_id}.{extensao}"

    def gravar(self, job_id: str, extensao: str, conteudo: bytes) -> None:
        gravar_atomico(self.caminho(job_id, extensao), conteudo)
