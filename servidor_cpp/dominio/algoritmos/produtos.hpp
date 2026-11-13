#pragma once

#include <cstddef>
#include <vector>

struct MatrizColunas {
    const double* dados;
    std::size_t linhas;
    std::size_t colunas;
};

void multiplicar(const MatrizColunas& H, const std::vector<double>& x, std::vector<double>& y);
void multiplicar_transposta(const MatrizColunas& H, const std::vector<double>& x, std::vector<double>& y);

double produto_interno(const std::vector<double>& x, const std::vector<double>& y);
double norma(const std::vector<double>& x);
void somar_multiplo(double a, const std::vector<double>& x, std::vector<double>& y);
void atualizar_direcao(std::vector<double>& p, const std::vector<double>& z, double beta);
