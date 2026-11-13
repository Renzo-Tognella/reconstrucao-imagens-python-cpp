#include "linha_de_comando.hpp"

#include <exception>
#include <sstream>
#include <stdexcept>

namespace {

// Limites altos o bastante para qualquer uso e baixos o bastante para somas e
// multiplicações em bytes não estourarem 64 bits.
constexpr std::uint64_t MAXIMO_BYTES = 1ull << 60;
constexpr std::uint64_t MAXIMO_MB = 1ull << 40;
constexpr std::uint64_t MAXIMO_ESPERA_S = 1ull << 40;
constexpr std::uint64_t MAXIMO_THREADS = 1024;

std::vector<std::string> separar_por_virgula(const std::string& texto) {
    std::vector<std::string> partes;
    std::istringstream campos(texto);
    std::string parte;
    while (std::getline(campos, parte, ',')) {
        partes.push_back(parte);
    }
    return partes;
}

std::uint64_t ler_inteiro(const std::string& nome, const std::string& texto, std::uint64_t minimo,
                          std::uint64_t maximo) {
    std::size_t usados = 0;
    unsigned long long valor = 0;
    try {
        if (!texto.empty() && texto[0] == '-') {
            throw std::invalid_argument(texto);
        }
        valor = std::stoull(texto, &usados);
    } catch (const std::exception&) {
        throw std::invalid_argument(nome + " precisa ser inteiro: " + texto);
    }
    if (usados != texto.size() || valor < minimo || valor > maximo) {
        throw std::invalid_argument(nome + " fora do intervalo: " + texto);
    }
    return valor;
}

void aplicar_opcao(Opcoes& opcoes, const std::string& nome, const std::string& valor) {
    if (nome == "--porta") {
        opcoes.porta = static_cast<int>(ler_inteiro(nome, valor, 0, 65535));
    } else if (nome == "--dados") {
        opcoes.dados = valor;
    } else if (nome == "--saida") {
        opcoes.saida = valor;
    } else if (nome == "--workers") {
        opcoes.workers = ler_inteiro(nome, valor, 1, MAXIMO_THREADS);
    } else if (nome == "--blas-threads") {
        opcoes.blas_threads = ler_inteiro(nome, valor, 1, MAXIMO_THREADS);
    } else if (nome == "--fila-max") {
        opcoes.fila_max = ler_inteiro(nome, valor, 1, MAXIMO_BYTES);
    } else if (nome == "--fila-max-bytes") {
        opcoes.fila_max_bytes = ler_inteiro(nome, valor, 1, MAXIMO_BYTES);
    } else if (nome == "--reserva-mem-mb") {
        opcoes.reserva_mem_mb = ler_inteiro(nome, valor, 0, MAXIMO_MB);
    } else if (nome == "--espera-mem-max-s") {
        opcoes.espera_mem_max_s = ler_inteiro(nome, valor, 0, MAXIMO_ESPERA_S);
    } else if (nome == "--aquecer") {
        opcoes.aquecer = separar_por_virgula(valor);
    } else {
        throw std::invalid_argument("opção desconhecida: " + nome);
    }
}

}  // namespace

Opcoes ler_opcoes(int argc, char** argv) {
    Opcoes opcoes;
    for (int i = 1; i < argc; i += 2) {
        const std::string nome = argv[i];
        if (i + 1 >= argc) {
            throw std::invalid_argument(nome + " sem valor");
        }
        aplicar_opcao(opcoes, nome, argv[i + 1]);
    }
    if (!opcoes.porta.has_value() || opcoes.dados.empty() || opcoes.saida.empty()) {
        throw std::invalid_argument("--porta, --dados e --saida são obrigatórios");
    }
    return opcoes;
}
