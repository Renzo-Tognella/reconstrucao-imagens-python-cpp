#include "infraestrutura/manifesto.hpp"

#include <algorithm>
#include <fstream>
#include <nlohmann/json.hpp>
#include <stdexcept>
#include <system_error>

namespace {

std::unique_ptr<ModeloMapeado> modelo_do_manifesto(const std::filesystem::path& dados, const std::string& nome,
                                                   const nlohmann::json& campos) {
    const auto linhas = campos.at("linhas").get<std::size_t>();
    const auto colunas = campos.at("colunas").get<std::size_t>();
    const auto largura = campos.at("largura").get<std::size_t>();
    const auto altura = campos.at("altura").get<std::size_t>();
    const auto matriz = dados / campos.at("arquivo").get<std::string>();
    if (linhas == 0 || colunas == 0 || largura * altura != colunas) {
        throw std::runtime_error("dimensões incoerentes no modelo " + nome);
    }
    std::error_code erro;
    const auto tamanho = std::filesystem::file_size(matriz, erro);
    if (erro || tamanho != 8 * linhas * colunas) {
        throw std::runtime_error("arquivo de H inválido no modelo " + nome + ": " + matriz.string());
    }
    return std::make_unique<ModeloMapeado>(nome, linhas, colunas, largura, altura, matriz);
}

}  // namespace

CatalogoManifesto::CatalogoManifesto(const std::filesystem::path& dados) {
    const auto caminho = dados / "manifesto.json";
    std::ifstream arquivo(caminho);
    if (!arquivo) {
        throw std::runtime_error("manifesto não encontrado: " + caminho.string());
    }
    nlohmann::json manifesto;
    try {
        arquivo >> manifesto;
        for (const auto& [nome, campos] : manifesto.at("modelos").items()) {
            modelos_.emplace(nome, modelo_do_manifesto(dados, nome, campos));
        }
    } catch (const nlohmann::json::exception& erro) {
        throw std::runtime_error("manifesto inválido: " + std::string(erro.what()));
    }
    if (modelos_.empty()) {
        throw std::runtime_error("manifesto sem modelos: " + caminho.string());
    }
}

const Modelo* CatalogoManifesto::procurar(const std::string& nome) const {
    const auto item = modelos_.find(nome);
    return item == modelos_.end() ? nullptr : item->second.get();
}

std::vector<std::string> CatalogoManifesto::nomes() const {
    std::vector<std::string> saida;
    for (const auto& [nome, modelo] : modelos_) {
        saida.push_back(nome);
    }
    return saida;
}

std::size_t CatalogoManifesto::maior_linhas() const {
    std::size_t maior = 0;
    for (const auto& [nome, modelo] : modelos_) {
        maior = std::max(maior, modelo->linhas());
    }
    return maior;
}
