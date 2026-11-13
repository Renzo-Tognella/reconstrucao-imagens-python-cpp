#pragma once

#include "dominio/algoritmos/cblas.hpp"

#include <cstdlib>
#include <string>

namespace blas {

inline void configurar_threads(int threads) {
#if defined(BLAS_ACCELERATE)
    setenv("VECLIB_MAXIMUM_THREADS", std::to_string(threads).c_str(), 1);
#else
    openblas_set_num_threads(threads);
#endif
}

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

}
