// H·x, Hᵀ·x e as operações de vetor usadas pelo CGNR e pelo CGNE, todas pela CBLAS.
#pragma once

#include <cstddef>
#include <vector>

// Matriz densa por colunas. A função não copia nem altera os dados, que costumam vir de um mmap.
struct MatrizColunas {
    const double* dados;
    std::size_t linhas;
    std::size_t colunas;
};

void multiplicar(const MatrizColunas& H, const std::vector<double>& x, std::vector<double>& y);
void multiplicar_transposta(const MatrizColunas& H, const std::vector<double>& x, std::vector<double>& y);

double produto_interno(const std::vector<double>& x, const std::vector<double>& y);
double norma(const std::vector<double>& x);
// y += a·x
void somar_multiplo(double a, const std::vector<double>& x, std::vector<double>& y);
// p = z + beta·p
void atualizar_direcao(std::vector<double>& p, const std::vector<double>& z, double beta);
