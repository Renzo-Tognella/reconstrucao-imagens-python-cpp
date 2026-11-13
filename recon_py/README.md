# Servidor Python

Versão interpretada e não fortemente tipada: Python 3.12, NumPy, SciPy, FastAPI e Uvicorn. Todos os comandos rodam na raiz do projeto.

## Subir

Uma vez, antes da primeira execução:

```bash
uv sync
```

```bash
.venv/bin/python preparar_dados.py
```

Servidor:

```bash
.venv/bin/python -m recon_py.servidor --porta 8000 --dados dados --saida resultados/demo/servidor-python --workers 6 --aquecer 30x30,60x60
```

Pronto quando aparecer `Servidor Python em http://127.0.0.1:8000`. `Ctrl+C` encerra.

## Opções

| Opção | Padrão | Uso |
| --- | --- | --- |
| `--porta` | obrigatória | porta HTTP em 127.0.0.1 |
| `--dados` | obrigatória | pasta gerada por `preparar_dados.py` |
| `--saida` | obrigatória | onde ficam `events.jsonl` e `jobs/` |
| `--workers` | 1 | reconstruções ao mesmo tempo (6 nos testes) |
| `--blas-threads` | 1 | threads da BLAS em cada reconstrução |
| `--fila-max` | 256 | pedidos na fila antes de responder `503` |
| `--fila-max-bytes` | 268435456 | bytes de sinais na fila antes de responder `503` |
| `--reserva-mem-mb` | 512 | RAM que precisa sobrar para uma tarefa começar |
| `--espera-mem-max-s` | 60 | espera por memória antes de a tarefa falhar |
| `--aquecer` | nenhum | modelos carregados antes de abrir a porta |

Rotas: `POST /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/image`, `GET /jobs/{id}/vector`, `GET /metrics`, `GET /info`. Detalhes no [README principal](../README.md#api).

## Testar

```bash
.venv/bin/python -m pytest -q tests/python
```

```bash
.venv/bin/python -m pytest -q tests/conformidade -k python
```

O segundo comando sobe este servidor e confere o contrato HTTP, o mesmo usado no servidor C++.

## Avaliar

1. Operações básicas (etapa 2): MN, aM e Ma conferidos com os gabaritos.

   ```bash
   .venv/bin/python -m pytest -q tests/python/etapas/test_operacoes_basicas.py
   ```

2. Protótipo (etapa 3): tempo, memória e CPU de cada reconstrução.

   ```bash
   .venv/bin/python -m recon_py.prototipo --dados dados --modelo 30x30 --sinal dados/sinais/30x30/g1.f64 --algoritmo cgnr --repeticoes 3
   ```

3. Reconstrução até ε < 1e-4 ou 10 iterações: a linha `concluído` no terminal do servidor mostra as iterações e se parou por `convergiu` ou `limite`.
4. Fila e controle de recursos: as linhas do terminal mostram `fila N, rodando M`. Com uma rajada (ver o [README do cliente](../cliente/README.md#avaliar)) a espera na fila aparece; com `--fila-max 40` o excesso volta como `503`.
5. Comparativo: o monitor mostra imagens concluídas, tempo total, CPU, memória, média e moda da fila e tempo médio de reconstrução.

   ```bash
   .venv/bin/python -m monitor --servidor http://127.0.0.1:8000
   ```
