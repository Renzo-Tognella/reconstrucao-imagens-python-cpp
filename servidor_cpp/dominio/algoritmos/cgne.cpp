#include "dominio/algoritmos/cgne.hpp"

#include "dominio/algoritmos/criterios.hpp"

#include <cmath>
#include <utility>

Resultado reconstruir_cgne(const MatrizColunas& H, std::vector<double> g) {
    std::vector<double> r = std::move(g);
    std::vector<double> w(H.linhas);
    std::vector<double> f(H.colunas, 0.0);
    std::vector<double> z(H.colunas);
    std::vector<double> p(H.colunas);
    std::vector<double> normas;
    normas.reserve(MAX_ITERACOES + 1);

    double rr = produto_interno(r, r);
    double rnorm = norma(r);
    exigir_finito(rr, "rr");
    exigir_finito(rnorm, "norma de g");
    normas.push_back(rnorm);
    multiplicar_transposta(H, r, p);
    if (rr == 0.0) {
        return concluir(std::move(f), std::move(normas), 0, MotivoParada::zero_residual);
    }

    for (int i = 1; i <= MAX_ITERACOES; ++i) {
        const double pp = produto_interno(p, p);
        exigir_nao_nulo_e_finito(pp, "pp");
        const double alpha = rr / pp;
        exigir_finito(alpha, "alpha");
        somar_multiplo(alpha, p, f);
        multiplicar(H, p, w);
        somar_multiplo(-alpha, w, r);
        const double novo = norma(r);
        exigir_finito(novo, "norma do resíduo");
        normas.push_back(novo);
        if (std::fabs(novo - rnorm) < TOLERANCIA) {
            return concluir(std::move(f), std::move(normas), i, MotivoParada::tolerance);
        }
        rnorm = novo;
        const double rr2 = produto_interno(r, r);
        exigir_finito(rr2, "rr");
        if (rr2 == 0.0) {
            return concluir(std::move(f), std::move(normas), i, MotivoParada::zero_residual);
        }
        const double beta = rr2 / rr;
        exigir_finito(beta, "beta");
        multiplicar_transposta(H, r, z);
        atualizar_direcao(p, z, beta);
        rr = rr2;
    }
    return concluir(std::move(f), std::move(normas), MAX_ITERACOES, MotivoParada::max_iterations);
}
