#include "infraestrutura/arquivos.hpp"

#include <fstream>
#include <iterator>
#include <stdexcept>
#include <system_error>

static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__, "Os arquivos .f64 são little-endian e lidos sem conversão");

// Temporário + rename: quem lê o arquivo nunca vê uma escrita pela metade.
void escrever_atomico(const std::filesystem::path& destino, const char* dados, std::size_t tamanho) {
    std::filesystem::path temporario = destino;
    temporario += ".tmp";
    try {
        std::ofstream arquivo(temporario, std::ios::binary | std::ios::trunc);
        arquivo.write(dados, static_cast<std::streamsize>(tamanho));
        arquivo.close();
        if (!arquivo) {
            throw std::runtime_error("falha ao gravar " + temporario.string());
        }
        std::filesystem::rename(temporario, destino);
    } catch (...) {
        std::error_code ignorado;
        std::filesystem::remove(temporario, ignorado);
        throw;
    }
}

std::string ler_arquivo(const std::filesystem::path& caminho) {
    std::ifstream arquivo(caminho, std::ios::binary);
    if (!arquivo) {
        throw std::runtime_error("falha ao abrir " + caminho.string());
    }
    return std::string(std::istreambuf_iterator<char>(arquivo), std::istreambuf_iterator<char>());
}

std::vector<double> ler_vetor_f64(const std::filesystem::path& caminho, std::size_t elementos) {
    std::ifstream arquivo(caminho, std::ios::binary | std::ios::ate);
    if (!arquivo) {
        throw std::runtime_error("não abriu " + caminho.string());
    }
    if (static_cast<std::size_t>(arquivo.tellg()) != 8 * elementos) {
        throw std::runtime_error(caminho.string() + " não tem " + std::to_string(elementos) + " valores float64");
    }
    arquivo.seekg(0);
    std::vector<double> vetor(elementos);
    arquivo.read(reinterpret_cast<char*>(vetor.data()), static_cast<std::streamsize>(8 * elementos));
    if (!arquivo) {
        throw std::runtime_error("falha ao ler " + caminho.string());
    }
    return vetor;
}
