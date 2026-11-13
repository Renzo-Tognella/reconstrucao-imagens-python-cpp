#include "dominio/algoritmos/resultado.hpp"

#include "dominio/algoritmos/criterios.hpp"

#include <utility>

const char* nome_do_motivo(MotivoParada motivo) {
    switch (motivo) {
        case MotivoParada::tolerance: return "tolerance";
        case MotivoParada::max_iterations: return "max_iterations";
        case MotivoParada::zero_residual: return "zero_residual";
    }
    return "max_iterations";
}

Resultado concluir(std::vector<double> f, std::vector<double> normas, int iteracoes, MotivoParada motivo) {
    for (const double valor : f) {
        exigir_finito(valor, "f");
    }
    Resultado resultado;
    resultado.f = std::move(f);
    resultado.residual_norms = std::move(normas);
    resultado.iterations = iteracoes;
    resultado.motivo = motivo;
    return resultado;
}
