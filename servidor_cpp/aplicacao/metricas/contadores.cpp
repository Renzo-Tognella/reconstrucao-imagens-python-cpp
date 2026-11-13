#include "aplicacao/metricas/contadores.hpp"

nlohmann::ordered_json corpo_metricas(const Contadores& contadores, const SituacaoFila& situacao) {
    nlohmann::ordered_json corpo;
    corpo["queue_depth"] = situacao.queue_depth;
    corpo["running"] = situacao.running;
    corpo["accepted"] = contadores.aceitas;
    corpo["completed"] = contadores.concluidas;
    corpo["failed"] = contadores.falhas;
    corpo["rejected"] = contadores.rejeitadas;
    corpo["waiting_memory"] = situacao.waiting_memory;
    corpo["uptime_s"] = situacao.uptime_s;
    return corpo;
}
