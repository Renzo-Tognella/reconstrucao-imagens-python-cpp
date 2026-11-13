#pragma once

#include "dominio/algoritmos/produtos.hpp"
#include "dominio/algoritmos/resultado.hpp"

#include <vector>

Resultado reconstruir_cgnr(const MatrizColunas& H, std::vector<double> g);
