#pragma once

#include <stdexcept>
#include <vector>

enum class MotivoParada { tolerance, max_iterations, zero_residual };
const char* nome_do_motivo(MotivoParada motivo);

struct Resultado {
    std::vector<double> f;
    std::vector<double> residual_norms;
    int iterations = 0;
    MotivoParada motivo = MotivoParada::max_iterations;
};

class FalhaNumerica : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

Resultado concluir(std::vector<double> f, std::vector<double> normas, int iteracoes, MotivoParada motivo);
