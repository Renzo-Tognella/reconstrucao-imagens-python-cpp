#include "dominio/algoritmos/cgnr.hpp"

#include "dominio/algoritmos/criterios.hpp"

#include <cmath>
#include <utility>

Resultado reconstruir_cgnr(const MatrizColunas& H, std::vector<double> g) {
    std::vector<double> r = std::move(g);
    std::vector<double> w(H.linhas);
    std::vector<double> f(H.colunas, 0.0);
    std::vector<double> z(H.colunas);
    std::vector<double> normas;
    normas.reserve(MAX_ITERACOES + 1);

    double rnorm = norma(r);
    exigir_finito(rnorm, "norma de g");
    normas.push_back(rnorm);
    multiplicar_transposta(H, r, z);
    std::vector<double> p = z;
    double zz = produto_interno(z, z);
    exigir_finito(zz, "zz");
    if (zz == 0.0) {
        return concluir(std::move(f), std::move(normas), 0, MotivoParada::zero_residual);
    }

    for (int i = 1; i <= MAX_ITERACOES; ++i) {
        multiplicar(H, p, w);
        const double ww = produto_interno(w, w);
        exigir_nao_nulo_e_finito(ww, "ww");
        const double alpha = zz / ww;
        exigir_finito(alpha, "alpha");
        somar_multiplo(alpha, p, f);
        somar_multiplo(-alpha, w, r);
        const double novo = norma(r);
        exigir_finito(novo, "norma do resíduo");
        normas.push_back(novo);
        if (std::fabs(novo - rnorm) < TOLERANCIA) {
            return concluir(std::move(f), std::move(normas), i, MotivoParada::tolerance);
        }
        rnorm = novo;
        multiplicar_transposta(H, r, z);
        const double zz2 = produto_interno(z, z);
        exigir_finito(zz2, "zz");
        if (zz2 == 0.0) {
            return concluir(std::move(f), std::move(normas), i, MotivoParada::zero_residual);
        }
        const double beta = zz2 / zz;
        exigir_finito(beta, "beta");
        atualizar_direcao(p, z, beta);
        zz = zz2;
    }
    return concluir(std::move(f), std::move(normas), MAX_ITERACOES, MotivoParada::max_iterations);
}
