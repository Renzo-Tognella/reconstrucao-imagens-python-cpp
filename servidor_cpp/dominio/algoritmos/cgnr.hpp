// CGNR do enunciado, operação por operação.
#pragma once

#include "dominio/algoritmos/produtos.hpp"
#include "dominio/algoritmos/resultado.hpp"

#include <vector>

// Espera g com H.linhas amostras; g vira o resíduo r, sem cópia.
Resultado reconstruir_cgnr(const MatrizColunas& H, std::vector<double> g);
