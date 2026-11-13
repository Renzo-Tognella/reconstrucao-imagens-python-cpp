# Reconstrução de imagens de ultrassom: Python × C++

Trabalho prático de Desenvolvimento Integrado de Sistemas (ICSM31, UTFPR).

Clientes enviam sinais de ultrassom `g` para um servidor, que reconstrói a imagem `f` resolvendo `g = H·f` com CGNR ou CGNE. Existem dois servidores com o mesmo contrato, um em Python e outro em C++, e o projeto mede qual atende melhor a mesma carga.

| Parte | Tecnologia | Pasta |
| --- | --- | --- |
| Servidor interpretado | Python 3.12, NumPy, SciPy, FastAPI, Uvicorn | `recon_py/` |
| Servidor compilado | C++17, OpenBLAS ou Accelerate, cpp-httplib, nlohmann/json | `servidor_cpp/` |
| Cliente | Python, HTTPX, Pillow | `cliente/` |
| Monitor ao vivo | Python, FastAPI, psutil | `monitor/` |
| Preparação dos dados | Python | `preparar_dados.py` |

## Arquitetura

- **Cliente-servidor centralizado.** Um servidor por vez atende vários clientes.
- **Comunicação assíncrona.** O cliente faz `POST /jobs` com o sinal e recebe `202` na hora. Depois consulta `GET /jobs/{id}` a cada 1 s até a imagem ficar pronta e baixa o resultado. O servidor não avisa o cliente; não há WebSocket.
- **HTTP REST com JSON.** O sinal vai no corpo como `float64` binário; o resto é JSON.
- **Fila FIFO com controle de saturação.** Até `W` reconstruções ao mesmo tempo (6 nos testes). Uma tarefa só começa se houver memória livre para ela. Com a fila cheia, o servidor responde `503`.

```text
cliente 1 ─┐                       ┌─ worker 1 ─┐
cliente 2 ─┼─ POST /jobs → fila ───┼─ ...       ├─ resultados em disco ← GET /jobs/{id}
cliente 3 ─┘                       └─ worker W ─┘
```

Os dois servidores seguem a mesma divisão em camadas. Cada camada só usa as de dentro:

```text
dominio/          algoritmos (CGNR, CGNE), imagem PGM
aplicacao/        fila, controle de memória, métricas
infraestrutura/   leitura da matriz, gravação em disco, log de eventos, BLAS
api/ ou http/     uma rota por arquivo em rotas/
etapas/           etapas 2 e 3 do enunciado, que rodam fora do servidor
```

No cliente, as pastas seguem o fluxo de um pedido: `carga/` sorteia os pedidos e aplica o ganho, `envio/` manda os sinais, consulta o servidor e baixa as imagens, `relatorios/` monta o HTML com as imagens e os dados de cada uma, e `demonstracao/` roda um cliente por terminal. O monitor lê o servidor por fora e calcula CPU, memória e fila em `monitor/medicao/`.

## Instalação

Requisitos: [uv](https://docs.astral.sh/uv/), CMake e OpenBLAS (`brew install openblas`).

```bash
uv sync
```

Os dados do enunciado estão em `dados-fornecidos/`, menos a matriz do modelo 60×60, que tem 152 MB. Sem ela, só o 30×30 fica disponível.

```bash
curl -L --fail -o dados-fornecidos/60x60/H-1.csv.zip https://nuvem.utfpr.edu.br/index.php/s/GcirTvh7gBDsne6/download
```

Converter os CSVs para os binários que os servidores leem (grava em `dados/`):

```bash
.venv/bin/python preparar_dados.py
```

Compilar o servidor C++ com OpenBLAS:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j2
```

No macOS também dá para compilar com Accelerate:

```bash
cmake -S . -B build-accelerate -DCMAKE_BUILD_TYPE=Release -DBLAS_BACKEND=accelerate && cmake --build build-accelerate -j2
```

Testes (os de conformidade rodam contra os dois servidores):

```bash
.venv/bin/python -m pytest -q
```

```bash
ctest --test-dir build
```

## Como ligar e executar

A demonstração usa 5 terminais: um para o servidor, um para o monitor e um para cada cliente. Antes, faça a [instalação](#instalação) uma vez. Em cada terminal, entre na pasta do projeto.

1. Terminal 1, gerar a carga. Ela é sorteada uma vez e salva, para os dois servidores receberem a mesma sequência:

   ```bash
   .venv/bin/python -m cliente.manifesto --semente 42 --clientes 3 --sinais-por-cliente 15 --modelos 30x30 --saida resultados/demo/carga.json
   ```

2. Terminal 1, ligar o servidor Python:

   ```bash
   .venv/bin/python -m recon_py.servidor --porta 8000 --dados dados --saida resultados/demo/servidor-python --workers 6 --aquecer 30x30
   ```

   ou o servidor C++:

   ```bash
   build/servidor_cpp --porta 8000 --dados dados --saida resultados/demo/servidor-cpp --workers 6 --aquecer 30x30
   ```

   Com `--aquecer`, o servidor carrega a matriz antes de abrir a porta. Quando a porta abre, ele já aceita pedidos.

   O terminal do servidor mostra uma linha por evento de cada pedido (recebido, iniciado, concluído, recusado ou falhou), com o tamanho da fila e quantas reconstruções estão rodando. Os mesmos eventos ficam em `events.jsonl`, na pasta de `--saida`.

3. Terminal 2, ligar o monitor e abrir <http://127.0.0.1:8050> no navegador:

   ```bash
   .venv/bin/python -m monitor --servidor http://127.0.0.1:8000
   ```

4. Terminais 3, 4 e 5, um cliente em cada, iniciados com alguns segundos de diferença (troque `--cliente 1` por 2 e 3):

   ```bash
   .venv/bin/python -m cliente.instancia --carga resultados/demo/carga.json --cliente 1 --servidor http://127.0.0.1:8000
   ```

5. Acompanhar no monitor. Ele mostra fila, tarefas em execução, CPU, memória, imagens por segundo e uma faixa por cliente com a espera na fila e a reconstrução de cada pedido.

Cada cliente aplica o ganho, envia os sinais com intervalos aleatórios, consulta o servidor até as imagens ficarem prontas e grava um relatório HTML com as imagens e os dados de cada uma. O cliente encerra sozinho depois da última imagem.

### Trocar de servidor

1. No terminal 1, pare o servidor com `Ctrl+C`.
2. Ligue o outro servidor (passo 2).
3. No monitor, clique em **Nova rodada** para zerar a tela.
4. Rode os três clientes de novo (passo 4), com a mesma `carga.json`.

### Desligar

Pare o servidor (terminal 1) e o monitor (terminal 2) com `Ctrl+C`.

### Problemas comuns

| Problema | Solução |
| --- | --- |
| Porta 8000 ocupada | Use `--porta 8001` no servidor e `http://127.0.0.1:8001` no monitor e nos clientes |
| `build/servidor_cpp` não existe | `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j2` |
| Pasta `dados/` não existe | `.venv/bin/python preparar_dados.py` |
| `.venv/` não existe | `uv sync` |

### Opções da carga (`cliente.manifesto`)

| Opção | Valores |
| --- | --- |
| `--algoritmos` | `cgnr`, `cgne` ou `cgnr,cgne` (padrão: sorteado) |
| `--modelos` | `30x30`, `60x60` ou os dois (padrão: os dois) |
| `--ganho` | `sorteado` (padrão), `sim` ou `nao` |
| `--intervalo-max` | espera máxima entre envios, em segundos (padrão 5) |
| `--semente` | mesma semente, mesma carga |

## API

| Rota | Resposta |
| --- | --- |
| `POST /jobs?job_id&client_id&signal_id&model&algorithm&gain` | `202` na fila; `200` se o mesmo pedido já chegou; `409` se o `job_id` já existe com outro corpo; `400` para parâmetro, modelo, algoritmo ou tamanho inválido; `413` corpo grande demais; `503` fila cheia |
| `GET /jobs/{id}` | estado (`queued`, `running`, `done`, `failed`), horários, espera na fila, tempo de reconstrução, iterações, motivo da parada e resíduos |
| `GET /jobs/{id}/image` | imagem PGM; `409` se ainda não terminou |
| `GET /jobs/{id}/vector` | vetor `f` em `float64` |
| `GET /metrics` | tamanho da fila, tarefas em execução, aceitas, concluídas, recusadas |
| `GET /info` | linguagem, BLAS, workers e modelos carregados |

Erros sempre voltam como `{"error": "<código>", "detail": "<texto>"}`.

Opções dos dois servidores: `--porta`, `--dados`, `--saida`, `--workers` (padrão 1), `--blas-threads` (padrão 1), `--fila-max` (256 pedidos), `--fila-max-bytes` (256 MiB), `--reserva-mem-mb` (512), `--espera-mem-max-s` (60) e `--aquecer`, que carrega a matriz antes de abrir a porta.

## Algoritmo

Os dois servidores implementam CGNR e CGNE como no enunciado, com chute inicial `f0 = 0`. A parada acontece quando a norma do resíduo muda menos de `1e-4` entre duas iterações, ou depois de 10 iterações. O código fica em `recon_py/dominio/algoritmos/` e `servidor_cpp/dominio/algoritmos/`, uma operação BLAS por linha nos dois lados.

A primeira iteração já mostra a imagem porque `Hᵀ·g` compara o eco medido com o eco esperado de cada pixel. As iterações seguintes corrigem o resíduo.

## Resultados

Medição num Apple M3 com 8 GiB, na bateria, com uma thread por chamada BLAS e 6 reconstruções simultâneas.

| Cenário | Python + Accelerate | C++ + Accelerate | C++ + OpenBLAS |
| --- | ---: | ---: | ---: |
| Rajada 30×30, imagens/s (5 rep.) | 24,7 ± 1,2 | 24,8 ± 1,1 | 29,4 ± 1,6 |
| Agenda 30×30, reconstrução média (5 rep.) | 0,058 s | 0,057 s | 0,091 s |
| Agenda 30×30, pico de memória | 272 MiB | 201 MiB | 198 MiB |
| Saturação, 2880 pedidos, imagens/s | 28,0 | 27,8 | 33,7 |
| Agenda com dois modelos, tempo total (3 rep.) | 76,8 ± 40,0 s | 62,9 ± 28,7 s | 51,5 ± 6,9 s |

- Com a mesma BLAS, Python e C++ empataram em velocidade. O Python usou cerca de 70 MiB a mais.
- A biblioteca pesou mais que a linguagem: o OpenBLAS foi mais lento por tarefa e mais rápido com 6 tarefas simultâneas.
- Na agenda do enunciado, o tempo total (cerca de 35,3 s) depende da duração da agenda e não diferencia as versões.
- A fila recusou pedidos só acima de 16 vezes a carga do enunciado, sem falhas.
- No 60×60, a matriz de 1,4 GiB não coube na memória livre. As tarefas variaram de 0,3 s a 59 s e não permitem ordenar as versões.
