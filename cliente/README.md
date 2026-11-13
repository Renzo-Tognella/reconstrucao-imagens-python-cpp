# Cliente

Envia os sinais de ultrassom ao servidor, espera as imagens e grava os resultados em CSV. Funciona igual com o servidor Python e o C++. Todos os comandos rodam na raiz do projeto, com um servidor já ligado.

## Subir

1. Gerar a carga uma vez. A mesma semente gera a mesma sequência de sinais para os dois servidores.

   ```bash
   .venv/bin/python -m cliente.manifesto --semente 42 --clientes 3 --sinais-por-cliente 15 --saida resultados/demo/carga-completa.json
   ```

2. Um cliente por terminal, iniciados com alguns segundos de diferença:

   ```bash
   .venv/bin/python -m cliente.instancia --carga resultados/demo/carga-completa.json --cliente 1 --servidor http://127.0.0.1:8000
   ```

   ```bash
   .venv/bin/python -m cliente.instancia --carga resultados/demo/carga-completa.json --cliente 2 --servidor http://127.0.0.1:8000
   ```

   ```bash
   .venv/bin/python -m cliente.instancia --carga resultados/demo/carga-completa.json --cliente 3 --servidor http://127.0.0.1:8000
   ```

Ou os três juntos, num terminal só:

```bash
for n in 1 2 3; do .venv/bin/python -m cliente.instancia --carga resultados/demo/carga-completa.json --cliente $n --servidor http://127.0.0.1:8000 & done; wait
```

Cada cliente mostra a tabela de envios, a tabela de imagens prontas e um resumo, e grava tudo em `resultados/demo/<carga>/<python|cpp>/cliente-00N/<data-hora>/`.

## Opções

`cliente.manifesto`:

| Opção | Padrão | Uso |
| --- | --- | --- |
| `--semente` | obrigatória | mesma semente, mesma carga |
| `--clientes` | obrigatória | número de clientes (mínimo do enunciado: 3) |
| `--sinais-por-cliente` | obrigatória | pedidos por cliente (mínimo do enunciado: 15) |
| `--saida` | obrigatória | arquivo JSON da carga |
| `--modelos` | todos | `30x30`, `60x60` ou `30x30,60x60` |
| `--algoritmos` | `cgnr,cgne` | algoritmos sorteados |
| `--ganho` | `sorteado` | `sorteado`, `sim` ou `nao` |
| `--intervalo-max` | 5 | espera máxima antes de cada envio, em s |

`cliente.instancia`:

| Opção | Padrão | Uso |
| --- | --- | --- |
| `--carga` | obrigatória | arquivo gerado pelo `cliente.manifesto` |
| `--cliente` | obrigatória | qual cliente da carga (1, 2, 3…) |
| `--servidor` | `http://127.0.0.1:8000` | endereço do servidor |
| `--saida` | pasta com data e hora | onde gravar registros e relatório |
| `--intervalo-consulta` | 1 | segundos entre consultas `GET /jobs/{id}` |
| `--limite-s` | 600 | espera máxima pelas imagens depois do último envio |
| `--cor` | `auto` | `auto`, `sim` ou `nao` |

## Testar

```bash
.venv/bin/python -m pytest -q tests/cliente
```

Com um servidor Python real em vez do servidor falso dos testes:

```bash
CLIENTE_E2E_REAL=1 .venv/bin/python -m pytest -q tests/cliente/demonstracao -k real
```

## Avaliar

1. No mínimo 3 clientes ao mesmo tempo: os três terminais do passo 2.
2. No mínimo 15 sinais por cliente em intervalos aleatórios: tabela ENVIOS, coluna `saiu aos`.
3. Ganho e modelo sorteados, ganho aplicado no cliente: colunas `modelo` e `ganho`; a fórmula está em `carga/ganho.py`.
4. Relatório com todas as imagens e os dados de cada uma (cliente, sinal, algoritmo, início, fim e iterações). Uma linha por pedido; a coluna `imagem` aponta para o PNG em `cliente/jobs/`:

   ```bash
   open resultados/demo/carga-completa/python/cliente-001/*/relatorio_cliente.csv
   ```

5. Mesma sequência para as duas versões: rode os três clientes com o mesmo arquivo de carga, primeiro contra o servidor Python e depois contra o C++.
6. Saturação: uma rajada de 180 pedidos. Rode os três clientes com `--carga resultados/demo/rajada.json` e veja a espera na fila subir.

   ```bash
   .venv/bin/python -m cliente.manifesto --semente 42 --clientes 3 --sinais-por-cliente 60 --modelos 30x30 --intervalo-max 0.05 --saida resultados/demo/rajada.json
   ```
