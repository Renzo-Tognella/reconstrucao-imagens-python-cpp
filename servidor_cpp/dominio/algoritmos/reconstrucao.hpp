#pragma once

#include "dominio/algoritmos/produtos.hpp"
#include "dominio/algoritmos/resultado.hpp"

#include <optional>
#include <string>
#include <vector>

enum class Algoritmo { cgnr, cgne };

std::optional<Algoritmo> algoritmo_de_nome(const std::string& nome);
const char* nome_do_algoritmo(Algoritmo algoritmo);

Resultado reconstruir(Algoritmo algoritmo, const MatrizColunas& H, std::vector<double> g);
