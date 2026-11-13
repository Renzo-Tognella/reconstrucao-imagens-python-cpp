// Contadores da fila e o corpo JSON de GET /metrics.
#pragma once

#include <cstddef>
#include <cstdint>
#include <nlohmann/json.hpp>

// Sem trava própria: a Fila só mexe aqui segurando a trava dela.
struct Contadores {
    std::uint64_t aceitas = 0;
    std::uint64_t concluidas = 0;
    std::uint64_t falhas = 0;
    std::uint64_t rejeitadas = 0;
};

struct SituacaoFila {
    std::size_t queue_depth;
    std::size_t running;
    bool waiting_memory;
    double uptime_s;
};

nlohmann::ordered_json corpo_metricas(const Contadores& contadores, const SituacaoFila& situacao);
