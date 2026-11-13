// Ponto único de contato com o backend BLAS escolhido no CMake: threads e descrição.
#pragma once

#include "dominio/algoritmos/cblas.hpp"

#include <cstdlib>
#include <string>

namespace blas {

// Chamar antes da primeira operação BLAS. O Accelerate não tem API para isso: lê
// VECLIB_MAXIMUM_THREADS do ambiente. O setenv cobre a execução normal; quem precisar de
// garantia independente da ordem de inicialização exporta a variável antes de abrir o processo.
inline void configurar_threads(int threads) {
#if defined(BLAS_ACCELERATE)
    setenv("VECLIB_MAXIMUM_THREADS", std::to_string(threads).c_str(), 1);
#else
    openblas_set_num_threads(threads);
#endif
}

// A OpenBLAS do Homebrew usa OpenMP, cujo limite de threads vale por thread chamador: todo thread
// que calcula precisa desta chamada, ou usará todos os núcleos. No Accelerate o limite é do processo
// e setenv concorrente seria inseguro, então nada acontece aqui.
inline void limitar_thread_atual(int threads) {
#if defined(BLAS_ACCELERATE)
    (void)threads;
#else
    openblas_set_num_threads(threads);
#endif
}

inline std::string descricao_backend() {
#if defined(BLAS_ACCELERATE)
    return "accelerate";
#else
    return openblas_get_config();
#endif
}

}  // namespace blas
