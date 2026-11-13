#include "infraestrutura/matriz_mapeada.hpp"

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cerrno>
#include <cstring>
#include <stdexcept>
#include <utility>
#include <vector>

static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__, "Os arquivos .f64 são little-endian e lidos sem conversão");

namespace {

class DescritorArquivo {
public:
    explicit DescritorArquivo(int descritor) : descritor_(descritor) {}
    ~DescritorArquivo() {
        if (descritor_ >= 0) {
            close(descritor_);
        }
    }
    DescritorArquivo(const DescritorArquivo&) = delete;
    DescritorArquivo& operator=(const DescritorArquivo&) = delete;
    int valor() const { return descritor_; }

private:
    int descritor_;
};

void ler_todas_as_paginas(const MatrizColunas& H) {
    const auto* bytes = reinterpret_cast<const unsigned char*>(H.dados);
    const auto pagina = static_cast<std::size_t>(sysconf(_SC_PAGESIZE));
    const std::size_t total = 8 * H.linhas * H.colunas;
    volatile unsigned char lido = 0;
    for (std::size_t posicao = 0; posicao < total; posicao += pagina) {
        lido = bytes[posicao];
    }
    (void)lido;
}

}

MapaSomenteLeitura::MapaSomenteLeitura(const std::filesystem::path& caminho, std::size_t bytes_esperados)
    : bytes_(bytes_esperados) {
    const DescritorArquivo arquivo(open(caminho.c_str(), O_RDONLY));
    if (arquivo.valor() < 0) {
        throw std::runtime_error("não abriu " + caminho.string() + ": " + std::strerror(errno));
    }
    struct stat info {};
    if (fstat(arquivo.valor(), &info) != 0) {
        throw std::runtime_error("fstat falhou em " + caminho.string() + ": " + std::strerror(errno));
    }
    if (static_cast<std::size_t>(info.st_size) != bytes_esperados) {
        throw std::runtime_error(caminho.string() + " tem " + std::to_string(info.st_size) + " bytes, esperados " +
                                 std::to_string(bytes_esperados));
    }
    endereco_ = mmap(nullptr, bytes_, PROT_READ, MAP_SHARED, arquivo.valor(), 0);
    if (endereco_ == MAP_FAILED) {
        endereco_ = nullptr;
        throw std::runtime_error("mmap falhou em " + caminho.string() + ": " + std::strerror(errno));
    }
}

MapaSomenteLeitura::~MapaSomenteLeitura() {
    if (endereco_ != nullptr) {
        munmap(endereco_, bytes_);
    }
}

ModeloMapeado::ModeloMapeado(std::string nome, std::size_t linhas, std::size_t colunas, std::size_t largura,
                             std::size_t altura, std::filesystem::path arquivo)
    : Modelo(std::move(nome), linhas, colunas, largura, altura), arquivo_(std::move(arquivo)) {}

MatrizColunas ModeloMapeado::matriz() const {
    std::call_once(uma_vez_, [this] {
        mapa_ = std::make_unique<MapaSomenteLeitura>(arquivo_, 8 * linhas() * colunas());
        mapeado_.store(true, std::memory_order_release);
    });
    return MatrizColunas{mapa_->dados(), linhas(), colunas()};
}

void aquecer_modelo(const Modelo& modelo) {
    const MatrizColunas H = modelo.matriz();
    ler_todas_as_paginas(H);
    std::vector<double> saida_linhas(H.linhas);
    std::vector<double> saida_colunas(H.colunas);
    multiplicar(H, std::vector<double>(H.colunas, 1.0), saida_linhas);
    multiplicar_transposta(H, std::vector<double>(H.linhas, 1.0), saida_colunas);
}
