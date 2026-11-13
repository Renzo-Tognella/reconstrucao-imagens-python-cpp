// Etapa 2 do enunciado: MN, aM e Ma com BLAS, conferidos contra os gabaritos MN.csv e aM.csv.
#include "infraestrutura/blas.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

// Matriz lida de CSV, guardada por colunas para o CblasColMajor.
struct Tabela {
    int linhas = 0;
    int colunas = 0;
    std::vector<double> dados;
    double em(int lin, int col) const { return dados[static_cast<std::size_t>(col * linhas + lin)]; }
};

std::vector<std::vector<double>> ler_linhas(const std::filesystem::path& caminho) {
    std::ifstream arquivo(caminho);
    if (!arquivo) {
        throw std::runtime_error("não abriu " + caminho.string());
    }
    std::vector<std::vector<double>> linhas;
    std::string linha;
    while (std::getline(arquivo, linha)) {
        if (!linha.empty() && linha.back() == '\r') {
            linha.pop_back();
        }
        if (linha.empty()) {
            continue;
        }
        std::vector<double> valores;
        std::istringstream campos(linha);
        std::string campo;
        while (std::getline(campos, campo, ';')) {
            std::size_t usados = 0;
            const double valor = std::stod(campo, &usados);
            if (usados != campo.size()) {
                throw std::runtime_error(caminho.string() + ": campo inválido '" + campo + "'");
            }
            valores.push_back(valor);
        }
        linhas.push_back(std::move(valores));
    }
    return linhas;
}

Tabela ler_tabela(const std::filesystem::path& caminho, int linhas_esperadas, int colunas_esperadas) {
    const auto linhas = ler_linhas(caminho);
    if (static_cast<int>(linhas.size()) != linhas_esperadas) {
        throw std::runtime_error(caminho.string() + ": número de linhas inesperado");
    }
    Tabela tabela{linhas_esperadas, colunas_esperadas,
                  std::vector<double>(static_cast<std::size_t>(linhas_esperadas * colunas_esperadas))};
    for (int lin = 0; lin < linhas_esperadas; ++lin) {
        if (static_cast<int>(linhas[static_cast<std::size_t>(lin)].size()) != colunas_esperadas) {
            throw std::runtime_error(caminho.string() + ": número de colunas inesperado");
        }
        for (int col = 0; col < colunas_esperadas; ++col) {
            tabela.dados[static_cast<std::size_t>(col * linhas_esperadas + lin)] =
                linhas[static_cast<std::size_t>(lin)][static_cast<std::size_t>(col)];
        }
    }
    return tabela;
}

double maior_diferenca(const std::vector<double>& x, const std::vector<double>& y) {
    double maior = 0.0;
    for (std::size_t i = 0; i < x.size(); ++i) {
        maior = std::max(maior, std::fabs(x[i] - y[i]));
    }
    return maior;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const std::filesystem::path pasta = argc > 1 ? argv[1] : DADOS_ETAPA2_PADRAO;
        const int n = 10;
        const Tabela M = ler_tabela(pasta / "M.csv", n, n);
        const Tabela N = ler_tabela(pasta / "N.csv", n, n);
        const Tabela MN_gabarito = ler_tabela(pasta / "MN.csv", n, n);
        const std::vector<double> a = ler_tabela(pasta / "a.csv", 1, n).dados;
        const std::vector<double> aM_gabarito = ler_tabela(pasta / "aM.csv", 1, n).dados;

        blas::configurar_threads(1);
        std::printf("blas: %s\n", blas::descricao_backend().c_str());

        std::vector<double> MN(static_cast<std::size_t>(n * n));
        cblas_dgemm(CblasColMajor, CblasNoTrans, CblasNoTrans, n, n, n, 1.0, M.dados.data(), n, N.dados.data(), n, 0.0,
                    MN.data(), n);

        // a é vetor linha: aM = (Mᵀ aᵀ)ᵀ.
        std::vector<double> aM(static_cast<std::size_t>(n));
        cblas_dgemv(CblasColMajor, CblasTrans, n, n, 1.0, M.dados.data(), n, a.data(), 1, 0.0, aM.data(), 1);

        std::vector<double> Ma(static_cast<std::size_t>(n));
        cblas_dgemv(CblasColMajor, CblasNoTrans, n, n, 1.0, M.dados.data(), n, a.data(), 1, 0.0, Ma.data(), 1);

        // MN.csv traz inteiros exatos: a tolerância cobre só o erro de ponto flutuante.
        const double tolerancia_MN = 1e-9;
        // aM.csv tem 2 casas (erro até 0,005) e a.csv tem 5 (erro até 5e-6 por termo, somado ao
        // longo da maior coluna de M).
        double maior_soma_coluna = 0.0;
        for (int col = 0; col < n; ++col) {
            double soma = 0.0;
            for (int lin = 0; lin < n; ++lin) {
                soma += std::fabs(M.em(lin, col));
            }
            maior_soma_coluna = std::max(maior_soma_coluna, soma);
        }
        const double tolerancia_aM = 0.005 + 5e-6 * maior_soma_coluna;

        const double erro_MN = maior_diferenca(MN, MN_gabarito.dados);
        const double erro_aM = maior_diferenca(aM, aM_gabarito);
        const bool ok_MN = erro_MN <= tolerancia_MN;
        const bool ok_aM = erro_aM <= tolerancia_aM;
        std::printf("MN: %s (maior diferença %.3e, tolerância %.3e)\n", ok_MN ? "ok" : "DIVERGE", erro_MN, tolerancia_MN);
        std::printf("aM: %s (maior diferença %.6f, tolerância %.6f)\n", ok_aM ? "ok" : "DIVERGE", erro_aM, tolerancia_aM);
        std::printf("Ma (M * a^T, sem gabarito):");
        for (std::size_t i = 0; i < Ma.size(); ++i) {
            std::printf("%s%.17g", i == 0 ? " " : ";", Ma[i]);
        }
        std::printf("\n");
        return ok_MN && ok_aM ? 0 : 1;
    } catch (const std::exception& erro) {
        std::fprintf(stderr, "operacoes_check: %s\n", erro.what());
        return 2;
    }
}
