#include "dominio/imagem.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace {

double maior_modulo(const std::vector<double>& f) {
    double maximo = 0.0;
    for (const double valor : f) {
        maximo = std::max(maximo, std::fabs(valor));
    }
    return maximo;
}

}

std::string imagem_pgm(const std::vector<double>& f, std::size_t largura, std::size_t altura) {
    if (f.size() != largura * altura) {
        throw std::invalid_argument("vetor f não corresponde a largura x altura");
    }
    const double maximo = maior_modulo(f);
    std::string pgm = "P5\n" + std::to_string(largura) + " " + std::to_string(altura) + "\n255\n";
    pgm.reserve(pgm.size() + f.size());
    for (std::size_t lin = 0; lin < altura; ++lin) {
        for (std::size_t col = 0; col < largura; ++col) {
            const double pixel = maximo == 0.0 ? 0.0 : std::floor(std::fabs(f[col * altura + lin]) / maximo * 255.0 + 0.5);
            pgm.push_back(static_cast<char>(static_cast<unsigned char>(pixel)));
        }
    }
    return pgm;
}
