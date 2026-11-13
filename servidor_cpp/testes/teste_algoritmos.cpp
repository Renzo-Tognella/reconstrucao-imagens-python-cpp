#include "dominio/algoritmos/reconstrucao.hpp"
#include "dominio/imagem.hpp"
#include "infraestrutura/arquivos.hpp"
#include "infraestrutura/blas.hpp"
#include "testes/verificacao.hpp"

#include <unistd.h>

#include <algorithm>
#include <cmath>
#include <exception>
#include <filesystem>
#include <limits>
#include <string>
#include <vector>

namespace {

void comparar(const std::vector<double>& obtido, const std::vector<double>& esperado, const std::string& nome) {
    verificar(obtido.size() == esperado.size(), nome + ": tamanho");
    for (std::size_t i = 0; i < obtido.size() && i < esperado.size(); ++i) {
        const double limite = 1e-7 * std::max(1.0, std::fabs(esperado[i]));
        verificar(std::fabs(obtido[i] - esperado[i]) <= limite, nome + "[" + std::to_string(i) + "]");
    }
}

std::vector<double> diagonal_de_quadrados() {
    std::vector<double> H(12 * 12, 0.0);
    for (int i = 0; i < 12; ++i) {
        H[static_cast<std::size_t>(i * 12 + i)] = static_cast<double>((i + 1) * (i + 1));
    }
    return H;
}

std::vector<double> sinal_diagonal() {
    std::vector<double> g(12);
    for (int i = 0; i < 12; ++i) {
        g[static_cast<std::size_t>(i)] = 7.0 * (i + 1);
    }
    return g;
}

void teste_cgnr_para_por_tolerancia_em_sistema_sobredeterminado() {
    const std::vector<double> H{1, 3, 5, 2, 4, 6};
    const auto r = reconstruir(Algoritmo::cgnr, MatrizColunas{H.data(), 3, 2}, {1, 2, 4});
    verificar(r.iterations == 3, "cgnr 3x2: iterations");
    verificar(r.motivo == MotivoParada::tolerance, "cgnr 3x2: motivo");
    comparar(r.f, {0.6666666666666666, 0.08333333333333341}, "cgnr 3x2: f");
    comparar(r.residual_norms, {4.58257569495584, 0.47450879156279396, 0.4082482904638629, 0.40824829046386296},
             "cgnr 3x2: normas");
}

void teste_ambos_param_por_tolerancia_em_sistema_quadrado() {
    const std::vector<double> H{2, 1, 1, 3};
    const auto cgnr = reconstruir(Algoritmo::cgnr, MatrizColunas{H.data(), 2, 2}, {1, 2});
    verificar(cgnr.iterations == 3 && cgnr.motivo == MotivoParada::tolerance, "cgnr 2x2: parada");
    comparar(cgnr.f, {0.2, 0.6}, "cgnr 2x2: f");
    const auto cgne = reconstruir(Algoritmo::cgne, MatrizColunas{H.data(), 2, 2}, {1, 2});
    verificar(cgne.iterations == 3 && cgne.motivo == MotivoParada::tolerance, "cgne 2x2: parada");
    comparar(cgne.f, {0.2, 0.6}, "cgne 2x2: f");
}

void teste_atinge_maximo_de_iteracoes() {
    const auto H = diagonal_de_quadrados();
    const auto cgnr = reconstruir(Algoritmo::cgnr, MatrizColunas{H.data(), 12, 12}, sinal_diagonal());
    verificar(cgnr.iterations == 10 && cgnr.motivo == MotivoParada::max_iterations, "cgnr 12x12: parada");
    comparar(cgnr.f,
             {0.15480071034431006, 1.1356978772747337, 2.578909687767241, 1.7314600194228182, 1.4011790714222057,
              1.1666012594142163, 1.0000031693641696, 0.8749998682560315, 0.7777777823072426, 0.6999999998749166,
              0.6363636362844877, 0.5833333284748722},
             "cgnr 12x12: f");
    comparar(cgnr.residual_norms,
             {178.46568297574746, 101.07563940196485, 72.34976336096061, 56.518626967437484, 46.04107676365266,
              38.27574024623112, 32.02361192037853, 26.632567767657335, 21.685683295722942, 16.86668116293983,
              11.885678050688956},
             "cgnr 12x12: normas");
    const auto cgne = reconstruir(Algoritmo::cgne, MatrizColunas{H.data(), 12, 12}, sinal_diagonal());
    verificar(cgne.iterations == 10 && cgne.motivo == MotivoParada::max_iterations, "cgne 12x12: parada");
    comparar(cgne.f,
             {0.24265698889782394, 1.7574999318194822, 3.711563128455884, 1.404189278876929, 1.4544002910804938,
              1.1603798730099333, 1.0005654874670296, 0.874959861052545, 0.7777799889965592, 0.6999999100620714,
              0.6363636387620346, 0.5833333637759159},
             "cgne 12x12: f");
    comparar(cgne.residual_norms,
             {178.46568297574746, 122.6409941850894, 103.60736184838949, 90.53144879794709, 79.38141218629535,
              68.87027678117047, 58.46612484659648, 47.961198118620764, 37.35636968428956, 26.83481944676882,
              16.75168308713078},
             "cgne 12x12: normas");
}

void teste_sinal_nulo_termina_sem_iteracoes() {
    const std::vector<double> H{1, 3, 5, 2, 4, 6};
    for (const auto algoritmo : {Algoritmo::cgnr, Algoritmo::cgne}) {
        const auto r = reconstruir(algoritmo, MatrizColunas{H.data(), 3, 2}, {0, 0, 0});
        verificar(r.iterations == 0 && r.motivo == MotivoParada::zero_residual, "sinal nulo: parada");
        comparar(r.f, {0, 0}, "sinal nulo: f");
        comparar(r.residual_norms, {0}, "sinal nulo: normas");
    }
}

void teste_valor_nao_finito_vira_falha_numerica() {
    const std::vector<double> H{std::numeric_limits<double>::quiet_NaN(), 3, 5, 2, 4, 6};
    for (const auto algoritmo : {Algoritmo::cgnr, Algoritmo::cgne}) {
        bool falhou = false;
        try {
            reconstruir(algoritmo, MatrizColunas{H.data(), 3, 2}, {1, 2, 4});
        } catch (const FalhaNumerica&) {
            falhou = true;
        }
        verificar(falhou, "NaN em H deve lançar FalhaNumerica");
    }
}

void teste_cgne_com_matriz_nula_e_falha_numerica() {
    const std::vector<double> H(6, 0.0);
    bool falhou = false;
    try {
        reconstruir(Algoritmo::cgne, MatrizColunas{H.data(), 3, 2}, {1, 2, 4});
    } catch (const FalhaNumerica&) {
        falhou = true;
    }
    verificar(falhou, "cgne com H nula: pp == 0");
    const auto cgnr = reconstruir(Algoritmo::cgnr, MatrizColunas{H.data(), 3, 2}, {1, 2, 4});
    verificar(cgnr.iterations == 0 && cgnr.motivo == MotivoParada::zero_residual, "cgnr com H nula: zz == 0");
}

void teste_tamanho_do_sinal_e_exigido() {
    const std::vector<double> H{1, 3, 5, 2, 4, 6};
    bool falhou = false;
    try {
        reconstruir(Algoritmo::cgnr, MatrizColunas{H.data(), 3, 2}, {1, 2});
    } catch (const std::invalid_argument&) {
        falhou = true;
    }
    verificar(falhou, "sinal com tamanho errado");
}

void teste_pgm_coluna_primeiro_com_valor_absoluto() {
    const std::string pgm = imagem_pgm({-1.0, 0.0, 0.5, 0.25}, 2, 2);
    const std::string cabecalho = "P5\n2 2\n255\n";
    verificar(pgm.substr(0, cabecalho.size()) == cabecalho, "pgm: cabeçalho");
    const std::string pixels = pgm.substr(cabecalho.size());
    verificar(pixels.size() == 4, "pgm: tamanho");
    verificar(static_cast<unsigned char>(pixels[0]) == 255, "pgm: (0,0)");
    verificar(static_cast<unsigned char>(pixels[1]) == 128, "pgm: (0,1) arredonda 127.5 para 128");
    verificar(static_cast<unsigned char>(pixels[2]) == 0, "pgm: (1,0)");
    verificar(static_cast<unsigned char>(pixels[3]) == 64, "pgm: (1,1) arredonda 63.75 para 64");
    const std::string nula = imagem_pgm({0.0, 0.0, 0.0, 0.0}, 2, 2);
    verificar(nula.substr(cabecalho.size()) == std::string(4, '\0'), "pgm: f nulo");
}

void teste_escrita_atomica_nao_deixa_temporario_quando_falha() {
    const std::filesystem::path pasta =
        std::filesystem::temp_directory_path() / ("teste_escrita_" + std::to_string(getpid()));
    const std::filesystem::path destino = pasta / "destino_e_pasta";
    std::filesystem::create_directories(destino);
    bool falhou = false;
    try {
        escrever_atomico(destino, "x", 1);
    } catch (const std::exception&) {
        falhou = true;
    }
    verificar(falhou, "rename sobre uma pasta deve falhar");
    verificar(!std::filesystem::exists(pasta / "destino_e_pasta.tmp"), "falha na escrita não deixa .tmp");
    std::error_code ignorado;
    std::filesystem::remove_all(pasta, ignorado);
}

}

int main() {
    blas::configurar_threads(1);
    teste_cgnr_para_por_tolerancia_em_sistema_sobredeterminado();
    teste_ambos_param_por_tolerancia_em_sistema_quadrado();
    teste_atinge_maximo_de_iteracoes();
    teste_sinal_nulo_termina_sem_iteracoes();
    teste_valor_nao_finito_vira_falha_numerica();
    teste_cgne_com_matriz_nula_e_falha_numerica();
    teste_tamanho_do_sinal_e_exigido();
    teste_pgm_coluna_primeiro_com_valor_absoluto();
    teste_escrita_atomica_nao_deixa_temporario_quando_falha();
    return resultado_final("teste_algoritmos");
}
