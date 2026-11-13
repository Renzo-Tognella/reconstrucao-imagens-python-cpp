#pragma once

#include "dominio/algoritmos/resultado.hpp"

#include <cmath>
#include <string>

inline constexpr int MAX_ITERACOES = 10;
inline constexpr double TOLERANCIA = 1e-4;

inline void exigir_finito(double valor, const char* nome) {
    if (!std::isfinite(valor)) {
        throw FalhaNumerica(std::string(nome) + " não é finito");
    }
}

inline void exigir_nao_nulo_e_finito(double valor, const char* nome) {
    exigir_finito(valor, nome);
    if (valor == 0.0) {
        throw FalhaNumerica(std::string(nome) + " é zero");
    }
}
