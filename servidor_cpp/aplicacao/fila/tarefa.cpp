#include "aplicacao/fila/tarefa.hpp"

#include "aplicacao/relogio.hpp"

#include <array>

namespace {

constexpr std::array<std::uint32_t, 256> gerar_tabela_crc() {
    std::array<std::uint32_t, 256> tabela{};
    for (std::uint32_t i = 0; i < 256; ++i) {
        std::uint32_t valor = i;
        for (int bit = 0; bit < 8; ++bit) {
            valor = (valor & 1u) != 0 ? 0xEDB88320u ^ (valor >> 1) : valor >> 1;
        }
        tabela[i] = valor;
    }
    return tabela;
}

constexpr auto TABELA_CRC = gerar_tabela_crc();

template <typename T>
nlohmann::ordered_json opcional_json(const std::optional<T>& valor) {
    return valor.has_value() ? nlohmann::ordered_json(*valor) : nlohmann::ordered_json(nullptr);
}

}  // namespace

std::uint32_t crc32(const void* dados, std::size_t tamanho) {
    const auto* bytes = static_cast<const unsigned char*>(dados);
    std::uint32_t crc = 0xFFFFFFFFu;
    for (std::size_t i = 0; i < tamanho; ++i) {
        crc = TABELA_CRC[(crc ^ bytes[i]) & 0xFFu] ^ (crc >> 8);
    }
    return crc ^ 0xFFFFFFFFu;
}

const char* nome_do_estado(EstadoTarefa estado) {
    switch (estado) {
        case EstadoTarefa::queued: return "queued";
        case EstadoTarefa::running: return "running";
        case EstadoTarefa::done: return "done";
        case EstadoTarefa::failed: return "failed";
    }
    return "failed";
}

Tarefa Tarefa::recebida(const PedidoTarefa& pedido, std::uint32_t crc) {
    Tarefa tarefa;
    tarefa.job_id = pedido.job_id;
    tarefa.client_id = pedido.client_id;
    tarefa.signal_id = pedido.signal_id;
    tarefa.modelo = pedido.modelo;
    tarefa.algoritmo = pedido.algoritmo;
    tarefa.gain = pedido.gain;
    tarefa.crc = crc;
    tarefa.received_at = relogio::agora_iso();
    tarefa.recebida_mono = relogio::segundos_monotonicos();
    return tarefa;
}

bool Tarefa::mesmo_pedido(const PedidoTarefa& pedido, std::uint32_t crc_pedido) const {
    return crc == crc_pedido && client_id == pedido.client_id && signal_id == pedido.signal_id &&
           modelo == pedido.modelo && algoritmo == pedido.algoritmo && gain == pedido.gain;
}

nlohmann::ordered_json corpo_json(const Tarefa& tarefa) {
    const Conclusao& conclusao = tarefa.conclusao;
    nlohmann::ordered_json corpo;
    corpo["job_id"] = tarefa.job_id;
    corpo["client_id"] = tarefa.client_id;
    corpo["signal_id"] = tarefa.signal_id;
    corpo["model"] = tarefa.modelo;
    corpo["algorithm"] = nome_do_algoritmo(tarefa.algoritmo);
    corpo["gain"] = tarefa.gain;
    corpo["status"] = nome_do_estado(tarefa.estado);
    corpo["received_at"] = tarefa.received_at;
    corpo["started_at"] = opcional_json(tarefa.started_at);
    corpo["finished_at"] = opcional_json(conclusao.finished_at);
    corpo["queue_wait_s"] = opcional_json(tarefa.queue_wait_s);
    corpo["duration_s"] = opcional_json(conclusao.duration_s);
    corpo["iterations"] = opcional_json(conclusao.iterations);
    corpo["stop_reason"] = opcional_json(conclusao.stop_reason);
    corpo["residual_norms"] = opcional_json(conclusao.residual_norms);
    corpo["error"] = opcional_json(conclusao.error);
    return corpo;
}
