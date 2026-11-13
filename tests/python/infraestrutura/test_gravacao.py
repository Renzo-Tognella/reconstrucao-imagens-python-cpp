from __future__ import annotations

import pytest

from recon_py.infraestrutura.gravacao import gravar_atomico


def test_gravacao_que_falha_nao_deixa_temporario(tmp_path):
    destino = tmp_path / "job.json"
    destino.mkdir()
    with pytest.raises(OSError):
        gravar_atomico(destino, b"{}")
    assert list(tmp_path.iterdir()) == [destino]
