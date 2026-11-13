#pragma once

#if defined(BLAS_ACCELERATE)
#include <Accelerate/Accelerate.h>
#elif defined(BLAS_OPENBLAS)
#include <cblas.h>
#else
#error "Defina BLAS_OPENBLAS ou BLAS_ACCELERATE"
#endif

#include <cstddef>
#include <limits>
#include <stdexcept>

namespace blas {

inline int dimensao(std::size_t n) {
    if (n > static_cast<std::size_t>(std::numeric_limits<int>::max())) {
        throw std::invalid_argument("dimensão excede o inteiro de 32 bits da BLAS");
    }
    return static_cast<int>(n);
}

}
