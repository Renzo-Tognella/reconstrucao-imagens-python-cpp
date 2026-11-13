// Catálogo de modelos lido de manifesto.json: nome, dimensões e arquivo de H de cada modelo.
#pragma once

#include "aplicacao/portas/modelos.hpp"
#include "infraestrutura/matriz_mapeada.hpp"

#include <cstddef>
#include <filesystem>
#include <map>
#include <memory>
#include <string>
#include <vector>

class CatalogoManifesto : public CatalogoModelos {
public:
    // Lança std::runtime_error se o manifesto ou um arquivo H for inválido.
    explicit CatalogoManifesto(const std::filesystem::path& dados);

    const Modelo* procurar(const std::string& nome) const override;
    std::vector<std::string> nomes() const override;
    std::size_t maior_linhas() const override;

private:
    std::map<std::string, std::unique_ptr<ModeloMapeado>> modelos_;
};
