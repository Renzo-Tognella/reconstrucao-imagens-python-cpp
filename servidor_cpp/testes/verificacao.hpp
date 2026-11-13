#pragma once

#include <cstdio>
#include <string>

inline int falhas = 0;

inline void verificar(bool condicao, const std::string& descricao) {
    if (!condicao) {
        std::fprintf(stderr, "FALHOU: %s\n", descricao.c_str());
        ++falhas;
    }
}

inline int resultado_final(const char* nome) {
    if (falhas != 0) {
        std::fprintf(stderr, "%d verificações falharam\n", falhas);
        return 1;
    }
    std::printf("%s: ok\n", nome);
    return 0;
}
