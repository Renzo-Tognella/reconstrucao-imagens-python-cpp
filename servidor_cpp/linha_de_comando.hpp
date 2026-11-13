// Opções de linha de comando do servidor_cpp.
#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

struct Opcoes {
    std::optional<int> porta;
    std::string dados;
    std::string saida;
    std::uint64_t workers = 1;
    std::uint64_t blas_threads = 1;
    std::uint64_t fila_max = 256;
    std::uint64_t fila_max_bytes = 268435456;
    std::uint64_t reserva_mem_mb = 512;
    std::uint64_t espera_mem_max_s = 60;
    std::vector<std::string> aquecer;
};

// Lança std::invalid_argument com a mensagem para o usuário.
Opcoes ler_opcoes(int argc, char** argv);
