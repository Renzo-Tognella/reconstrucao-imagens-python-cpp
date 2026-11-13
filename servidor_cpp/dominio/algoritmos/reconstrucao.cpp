#include "dominio/algoritmos/reconstrucao.hpp"

#include "dominio/algoritmos/cgne.hpp"
#include "dominio/algoritmos/cgnr.hpp"

#include <stdexcept>
#include <utility>

std::optional<Algoritmo> algoritmo_de_nome(const std::string& nome) {
    if (nome == "cgnr") {
        return Algoritmo::cgnr;
    }
    if (nome == "cgne") {
        return Algoritmo::cgne;
    }
    return std::nullopt;
}

const char* nome_do_algoritmo(Algoritmo algoritmo) {
    return algoritmo == Algoritmo::cgnr ? "cgnr" : "cgne";
}

Resultado reconstruir(Algoritmo algoritmo, const MatrizColunas& H, std::vector<double> g) {
    if (g.size() != H.linhas) {
        throw std::invalid_argument("sinal com " + std::to_string(g.size()) + " amostras; H tem " +
                                    std::to_string(H.linhas) + " linhas");
    }
    return algoritmo == Algoritmo::cgnr ? reconstruir_cgnr(H, std::move(g)) : reconstruir_cgne(H, std::move(g));
}
