#pragma once

#include "dominio/algoritmos/produtos.hpp"

#include <cstddef>
#include <string>
#include <utility>
#include <vector>

class Modelo {
public:
    Modelo(std::string nome, std::size_t linhas, std::size_t colunas, std::size_t largura, std::size_t altura)
        : nome_(std::move(nome)), linhas_(linhas), colunas_(colunas), largura_(largura), altura_(altura) {}
    virtual ~Modelo() = default;
    Modelo(const Modelo&) = delete;
    Modelo& operator=(const Modelo&) = delete;

    const std::string& nome() const { return nome_; }
    std::size_t linhas() const { return linhas_; }
    std::size_t colunas() const { return colunas_; }
    std::size_t largura() const { return largura_; }
    std::size_t altura() const { return altura_; }

    virtual bool mapeado() const = 0;
    virtual MatrizColunas matriz() const = 0;

private:
    std::string nome_;
    std::size_t linhas_;
    std::size_t colunas_;
    std::size_t largura_;
    std::size_t altura_;
};

class CatalogoModelos {
public:
    virtual ~CatalogoModelos() = default;

    virtual const Modelo* procurar(const std::string& nome) const = 0;
    virtual std::vector<std::string> nomes() const = 0;
    virtual std::size_t maior_linhas() const = 0;
};
