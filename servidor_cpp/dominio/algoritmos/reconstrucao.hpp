// Porta de entrada do domínio: escolhe CGNR ou CGNE pelo nome e roda a reconstrução.
#pragma once

#include "dominio/algoritmos/produtos.hpp"
#include "dominio/algoritmos/resultado.hpp"

#include <optional>
#include <string>
#include <vector>

enum class Algoritmo { cgnr, cgne };

std::optional<Algoritmo> algoritmo_de_nome(const std::string& nome);
const char* nome_do_algoritmo(Algoritmo algoritmo);

// g é consumido: vira o resíduo r, sem cópia, para o custo de memória bater com o protocolo
// (r e w por linha; f, z e p por coluna). Lança FalhaNumerica se surgir valor não finito.
Resultado reconstruir(Algoritmo algoritmo, const MatrizColunas& H, std::vector<double> g);
