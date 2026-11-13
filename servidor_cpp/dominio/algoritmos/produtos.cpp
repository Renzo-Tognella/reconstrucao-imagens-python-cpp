#include "dominio/algoritmos/produtos.hpp"

#include "dominio/algoritmos/cblas.hpp"

void multiplicar(const MatrizColunas& H, const std::vector<double>& x, std::vector<double>& y) {
    const int m = blas::dimensao(H.linhas);
    cblas_dgemv(CblasColMajor, CblasNoTrans, m, blas::dimensao(H.colunas), 1.0, H.dados, m, x.data(), 1, 0.0,
                y.data(), 1);
}

void multiplicar_transposta(const MatrizColunas& H, const std::vector<double>& x, std::vector<double>& y) {
    const int m = blas::dimensao(H.linhas);
    cblas_dgemv(CblasColMajor, CblasTrans, m, blas::dimensao(H.colunas), 1.0, H.dados, m, x.data(), 1, 0.0,
                y.data(), 1);
}

double produto_interno(const std::vector<double>& x, const std::vector<double>& y) {
    return cblas_ddot(blas::dimensao(x.size()), x.data(), 1, y.data(), 1);
}

double norma(const std::vector<double>& x) { return cblas_dnrm2(blas::dimensao(x.size()), x.data(), 1); }

void somar_multiplo(double a, const std::vector<double>& x, std::vector<double>& y) {
    cblas_daxpy(blas::dimensao(x.size()), a, x.data(), 1, y.data(), 1);
}

void atualizar_direcao(std::vector<double>& p, const std::vector<double>& z, double beta) {
    const int n = blas::dimensao(p.size());
    cblas_dscal(n, beta, p.data(), 1);
    cblas_daxpy(n, 1.0, z.data(), 1, p.data(), 1);
}
