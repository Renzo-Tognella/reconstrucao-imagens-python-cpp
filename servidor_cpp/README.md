# Servidor C++

Versão compilada e fortemente tipada: C++17, OpenBLAS (ou Accelerate no macOS), cpp-httplib e nlohmann/json. Todos os comandos rodam na raiz do projeto.

## Subir

Uma vez: dependências Python (para preparar os dados) e OpenBLAS.

```bash
brew install openblas
```

```bash
uv sync
```

```bash
.venv/bin/python preparar_dados.py
```

Compilar:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j2
```

Com Accelerate, em vez de OpenBLAS:

```bash
cmake -S . -B build-accelerate -DCMAKE_BUILD_TYPE=Release -DBLAS_BACKEND=accelerate && cmake --build build-accelerate -j2
```

Servidor:

```bash
build/servidor_cpp --porta 8000 --dados dados --saida resultados/demo/servidor-cpp --workers 6 --aquecer 30x30,60x60
```

Pronto quando aparecer `Servidor C++ em http://127.0.0.1:8000`. `Ctrl+C` encerra.

## Opções

As mesmas do servidor Python, com os mesmos padrões: `--porta`, `--dados` e `--saida` (obrigatórias), `--workers` (1), `--blas-threads` (1), `--fila-max` (256), `--fila-max-bytes` (268435456), `--reserva-mem-mb` (512), `--espera-mem-max-s` (60) e `--aquecer`. A tabela com o uso de cada uma está no [README do servidor Python](../recon_py/README.md#opções).

As rotas também são as mesmas. Detalhes no [README principal](../README.md#api).

## Testar

```bash
ctest --test-dir build
```

```bash
.venv/bin/python -m pytest -q tests/conformidade -k cpp
```

O `ctest` roda os algoritmos, a fila e as operações básicas. O segundo comando sobe `build/servidor_cpp` e confere o contrato HTTP.

## Avaliar

1. Operações básicas (etapa 2): MN e aM conferidos com os gabaritos; Ma impresso.

   ```bash
   build/operacoes_check
   ```

2. Protótipo (etapa 3): tempo, memória e CPU de cada reconstrução, uma linha JSON por repetição.

   ```bash
   build/prototipo_cpp --dados dados --modelo 30x30 --sinal dados/sinais/30x30/g1.f64 --algoritmo cgnr --repeticoes 3
   ```

3. Reconstrução até ε < 1e-4 ou 10 iterações: a linha `concluído` no terminal do servidor mostra as iterações e se parou por `convergiu` ou `limite`.
4. Fila e controle de recursos: as linhas do terminal mostram `fila N, rodando M`. Com uma rajada (ver o [README do cliente](../cliente/README.md#avaliar)) a espera na fila aparece; com `--fila-max 40` o excesso volta como `503`.
5. Mesma carga do servidor Python: rode os clientes com o mesmo arquivo de carga e compare no monitor.

   ```bash
   .venv/bin/python -m monitor --servidor http://127.0.0.1:8000
   ```
