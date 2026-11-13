#pragma once

#include "aplicacao/portas/modelos.hpp"

#include <cstddef>
#include <cstdint>
#include <functional>
#include <optional>

std::uint64_t custo_em_bytes(const Modelo& modelo);

enum class DecisaoMemoria { iniciar, aguardar, falhar };

class ControleMemoria {
public:
    ControleMemoria(std::function<std::uint64_t()> memoria_disponivel, std::uint64_t memoria_fisica,
                    std::uint64_t reserva, double espera_max_s);

    bool nunca_cabe(const Modelo& modelo) const;
    DecisaoMemoria avaliar(const Modelo& modelo, std::size_t em_execucao);
    void reservar(std::uint64_t custo) { reservado_ += custo; }
    void devolver(std::uint64_t custo) { reservado_ -= custo; }
    void encerrar_espera();
    bool esperando() const { return esperando_; }

private:
    bool prazo_vencido();

    const std::function<std::uint64_t()> memoria_disponivel_;
    const std::uint64_t memoria_fisica_;
    const std::uint64_t reserva_;
    const double espera_max_s_;
    std::uint64_t reservado_ = 0;
    bool esperando_ = false;
    std::optional<double> sem_execucao_desde_;
};
