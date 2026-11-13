#include "aplicacao/relogio.hpp"
#include "dominio/algoritmos/reconstrucao.hpp"
#include "dominio/imagem.hpp"
#include "infraestrutura/arquivos.hpp"
#include "infraestrutura/blas.hpp"
#include "infraestrutura/manifesto.hpp"
#include "infraestrutura/sistema.hpp"

#include <cstdio>
#include <nlohmann/json.hpp>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct Argumentos {
    std::string dados;
    std::string modelo;
    std::string sinal;
    std::string algoritmo;
    int repeticoes = 1;
    int blas_threads = 1;
    std::optional<std::string> saida;
};

int inteiro_positivo(const char* nome, const std::string& texto) {
    std::size_t usados = 0;
    const int valor = std::stoi(texto, &usados);
    if (usados != texto.size() || valor < 1) {
        throw std::invalid_argument(std::string(nome) + " precisa ser inteiro positivo");
    }
    return valor;
}

Argumentos ler_argumentos(int argc, char** argv) {
    Argumentos args;
    for (int i = 1; i < argc; i += 2) {
        const std::string nome = argv[i];
        if (i + 1 >= argc) {
            throw std::invalid_argument(nome + " sem valor");
        }
        const std::string valor = argv[i + 1];
        if (nome == "--dados") {
            args.dados = valor;
        } else if (nome == "--modelo") {
            args.modelo = valor;
        } else if (nome == "--sinal") {
            args.sinal = valor;
        } else if (nome == "--algoritmo") {
            args.algoritmo = valor;
        } else if (nome == "--repeticoes") {
            args.repeticoes = inteiro_positivo("--repeticoes", valor);
        } else if (nome == "--blas-threads") {
            args.blas_threads = inteiro_positivo("--blas-threads", valor);
        } else if (nome == "--saida") {
            args.saida = valor;
        } else {
            throw std::invalid_argument("opção desconhecida: " + nome);
        }
    }
    if (args.dados.empty() || args.modelo.empty() || args.sinal.empty() || args.algoritmo.empty()) {
        throw std::invalid_argument(
            "uso: prototipo_cpp --dados DIR --modelo NOME --sinal ARQ.f64 --algoritmo cgnr|cgne "
            "[--repeticoes N] [--blas-threads B] [--saida x.pgm]");
    }
    return args;
}

}

int main(int argc, char** argv) {
    try {
        const Argumentos args = ler_argumentos(argc, argv);
        const auto algoritmo = algoritmo_de_nome(args.algoritmo);
        if (!algoritmo.has_value()) {
            throw std::invalid_argument("algoritmo desconhecido: " + args.algoritmo);
        }
        blas::configurar_threads(args.blas_threads);

        const CatalogoManifesto catalogo(args.dados);
        const Modelo* modelo = catalogo.procurar(args.modelo);
        if (modelo == nullptr) {
            throw std::invalid_argument("modelo desconhecido: " + args.modelo);
        }

        const double antes_carga = relogio::segundos_monotonicos();
        const MatrizColunas H = modelo->matriz();
        const double carga_h_s = relogio::segundos_monotonicos() - antes_carga;
        const std::vector<double> g = ler_vetor_f64(args.sinal, modelo->linhas());

        for (int repeticao = 0; repeticao < args.repeticoes; ++repeticao) {
            const double cpu_antes = sistema::uso_recursos().cpu_s;
            const double inicio = relogio::segundos_monotonicos();
            const Resultado resultado = reconstruir(*algoritmo, H, g);
            const double duracao = relogio::segundos_monotonicos() - inicio;
            const sistema::UsoRecursos uso = sistema::uso_recursos();

            nlohmann::ordered_json linha;
            linha["iterations"] = resultado.iterations;
            linha["stop_reason"] = nome_do_motivo(resultado.motivo);
            linha["residual_norms"] = resultado.residual_norms;
            linha["duration_s"] = duracao;
            linha["rss_mb"] = uso.pico_rss_mb;
            linha["cpu_s"] = uso.cpu_s - cpu_antes;
            linha["carga_h_s"] = carga_h_s;
            std::puts(linha.dump().c_str());
            std::fflush(stdout);

            if (args.saida.has_value() && repeticao + 1 == args.repeticoes) {
                const std::string pgm = imagem_pgm(resultado.f, modelo->largura(), modelo->altura());
                escrever_atomico(*args.saida, pgm.data(), pgm.size());
            }
        }
        return 0;
    } catch (const FalhaNumerica& erro) {
        std::fprintf(stderr, "falha numérica: %s\n", erro.what());
        return 1;
    } catch (const std::exception& erro) {
        std::fprintf(stderr, "prototipo_cpp: %s\n", erro.what());
        return 2;
    }
}
