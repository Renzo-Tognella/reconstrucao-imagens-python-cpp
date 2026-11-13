#pragma once

#include "aplicacao/portas/modelos.hpp"

#include <atomic>
#include <cstddef>
#include <filesystem>
#include <memory>
#include <mutex>
#include <string>

class MapaSomenteLeitura {
public:
    MapaSomenteLeitura(const std::filesystem::path& caminho, std::size_t bytes_esperados);
    ~MapaSomenteLeitura();
    MapaSomenteLeitura(const MapaSomenteLeitura&) = delete;
    MapaSomenteLeitura& operator=(const MapaSomenteLeitura&) = delete;

    const double* dados() const { return static_cast<const double*>(endereco_); }

private:
    void* endereco_ = nullptr;
    std::size_t bytes_ = 0;
};

class ModeloMapeado : public Modelo {
public:
    ModeloMapeado(std::string nome, std::size_t linhas, std::size_t colunas, std::size_t largura, std::size_t altura,
                  std::filesystem::path arquivo);

    bool mapeado() const override { return mapeado_.load(std::memory_order_acquire); }
    MatrizColunas matriz() const override;

private:
    std::filesystem::path arquivo_;
    mutable std::once_flag uma_vez_;
    mutable std::unique_ptr<MapaSomenteLeitura> mapa_;
    mutable std::atomic<bool> mapeado_{false};
};

void aquecer_modelo(const Modelo& modelo);
