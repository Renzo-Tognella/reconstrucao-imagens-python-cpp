from __future__ import annotations

import pytest

from tests.cliente.apoio import criar_dados
from tests.cliente.stub_servidor import Stub


@pytest.fixture
def dados(tmp_path):
    return criar_dados(tmp_path / "dados")


@pytest.fixture
def subir_stub(tmp_path, dados):
    abertos = []

    def subir(**opcoes):
        stub = Stub(dados, tmp_path / f"servidor-{len(abertos)}", **opcoes)
        abertos.append(stub)
        return stub

    yield subir
    for stub in abertos:
        stub.encerrar()
