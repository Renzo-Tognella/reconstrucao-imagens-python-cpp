// Uma tarefa de reconstrução: o pedido recebido, o estado e o corpo JSON de GET /jobs/{id}.
#pragma once

#include "dominio/algoritmos/reconstrucao.hpp"

#include <cstddef>
#include <cstdint>
#include <nlohmann/json.hpp>
#include <optional>
#include <string>
#include <vector>

// CRC-32 igual ao zlib.crc32.
std::uint32_t crc32(const void* dados, std::size_t tamanho);

enum class EstadoTarefa { queued, running, done, failed };
const char* nome_do_estado(EstadoTarefa estado);

// Já validado pela camada HTTP. O modelo precisa existir no catálogo.
struct PedidoTarefa {
    std::string job_id;
    std::string client_id;
    std::string signal_id;
    std::string modelo;
    Algoritmo algoritmo = Algoritmo::cgnr;
    bool gain = false;
    std::vector<double> sinal;
};

struct Conclusao {
    std::optional<std::string> finished_at;
    std::optional<double> duration_s;
    std::optional<int> iterations;
    std::optional<std::string> stop_reason;
    std::optional<std::vector<double>> residual_norms;
    std::optional<std::string> error;
};

struct Tarefa {
    std::string job_id;
    std::string client_id;
    std::string signal_id;
    std::string modelo;
    Algoritmo algoritmo = Algoritmo::cgnr;
    bool gain = false;
    std::uint32_t crc = 0;
    EstadoTarefa estado = EstadoTarefa::queued;
    std::string received_at;
    double recebida_mono = 0.0;
    std::optional<std::string> started_at;
    std::optional<double> queue_wait_s;
    Conclusao conclusao;

    static Tarefa recebida(const PedidoTarefa& pedido, std::uint32_t crc);
    bool mesmo_pedido(const PedidoTarefa& pedido, std::uint32_t crc_pedido) const;
};

nlohmann::ordered_json corpo_json(const Tarefa& tarefa);
