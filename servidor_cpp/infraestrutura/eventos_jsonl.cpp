#include "infraestrutura/eventos_jsonl.hpp"

#include "aplicacao/fila/tarefa.hpp"
#include "aplicacao/relogio.hpp"
#include "infraestrutura/log_terminal.hpp"

#include <cstdio>
#include <nlohmann/json.hpp>
#include <stdexcept>

EventosJsonl::EventosJsonl(const std::filesystem::path& saida)
    : arquivo_(saida / "events.jsonl", std::ios::app) {
    if (!arquivo_) {
        throw std::runtime_error("não abriu events.jsonl em " + saida.string());
    }
}

void EventosJsonl::registrar(const char* evento, const std::string& job_id, std::size_t queue_depth,
                            std::size_t running, const Tarefa* tarefa) {
    log_terminal::escrever(log_terminal::linha_evento(evento, job_id, tarefa, queue_depth, running));
    nlohmann::ordered_json linha;
    linha["t_wall"] = relogio::agora_iso();
    linha["t_mono"] = relogio::segundos_monotonicos();
    linha["event"] = evento;
    linha["job_id"] = job_id;
    linha["queue_depth"] = queue_depth;
    linha["running"] = running;
    arquivo_ << linha.dump() << '\n';
    arquivo_.flush();
    if (!arquivo_) {
        std::fprintf(stderr, "falha ao gravar events.jsonl (evento %s de %s)\n", evento, job_id.c_str());
        arquivo_.clear();
    }
}
