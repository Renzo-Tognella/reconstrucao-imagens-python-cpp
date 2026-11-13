#include "aplicacao/fila/fila.hpp"

#include "aplicacao/relogio.hpp"

#include <cstdio>
#include <stdexcept>
#include <utility>

Fila::Fila(ConfiguracaoFila configuracao, DependenciasFila dependencias)
    : configuracao_(std::move(configuracao)),
      catalogo_(dependencias.catalogo),
      resultados_(dependencias.resultados),
      eventos_(dependencias.eventos),
      preparar_worker_(std::move(dependencias.preparar_worker)),
      inicio_mono_(relogio::segundos_monotonicos()),
      memoria_(std::move(dependencias.memoria_disponivel), dependencias.memoria_fisica, configuracao_.reserva_bytes,
               configuracao_.espera_mem_max_s) {
    try {
        workers_.reserve(configuracao_.workers);
        for (std::size_t i = 0; i < configuracao_.workers; ++i) {
            workers_.emplace_back(&Fila::laco_worker, this);
        }
        despachante_ = std::thread(&Fila::laco_despachante, this);
    } catch (...) {
        parar_despacho();
        juntar_threads();
        throw;
    }
}

Fila::~Fila() {
    parar_despacho();
    aguardar_fim();
}

RespostaEnvio Fila::enviar(PedidoTarefa pedido) {
    const std::uint64_t bytes = pedido.sinal.size() * sizeof(double);
    const std::uint32_t crc = crc32(pedido.sinal.data(), bytes);
    const Modelo* modelo = catalogo_.procurar(pedido.modelo);
    if (modelo == nullptr) {
        throw std::invalid_argument("modelo desconhecido: " + pedido.modelo);
    }

    const std::lock_guard<std::mutex> guarda(trava_);
    const auto existente = tarefas_.find(pedido.job_id);
    if (existente != tarefas_.end()) {
        const Tarefa& tarefa = *existente->second;
        return {tarefa.mesmo_pedido(pedido, crc) ? DesfechoEnvio::repetido : DesfechoEnvio::conflito, tarefa.estado};
    }
    if (fila_.size() >= configuracao_.fila_max || bytes_na_fila_ + bytes > configuracao_.fila_max_bytes) {
        ++contadores_.rejeitadas;
        registrar_evento("rejected", pedido.job_id);
        return {DesfechoEnvio::fila_cheia, EstadoTarefa::queued};
    }

    auto tarefa = std::make_unique<Tarefa>(Tarefa::recebida(pedido, crc));
    Tarefa& registrada = *tarefa;
    tarefas_.emplace(registrada.job_id, std::move(tarefa));
    fila_.push_back(ItemFila{&registrada, modelo, std::move(pedido.sinal)});
    bytes_na_fila_ += bytes;
    ++contadores_.aceitas;
    registrar_evento("accepted", registrada.job_id);
    cv_despachante_.notify_one();
    return {DesfechoEnvio::aceito, EstadoTarefa::queued};
}

std::optional<nlohmann::ordered_json> Fila::consultar(const std::string& job_id) const {
    const std::lock_guard<std::mutex> guarda(trava_);
    const auto item = tarefas_.find(job_id);
    if (item == tarefas_.end()) {
        return std::nullopt;
    }
    return corpo_json(*item->second);
}

std::optional<EstadoTarefa> Fila::estado(const std::string& job_id) const {
    const std::lock_guard<std::mutex> guarda(trava_);
    const auto item = tarefas_.find(job_id);
    if (item == tarefas_.end()) {
        return std::nullopt;
    }
    return item->second->estado;
}

nlohmann::ordered_json Fila::metricas() const {
    const std::lock_guard<std::mutex> guarda(trava_);
    const SituacaoFila situacao{fila_.size(), em_execucao_, memoria_.esperando(),
                                relogio::segundos_monotonicos() - inicio_mono_};
    return corpo_metricas(contadores_, situacao);
}

std::string Fila::ler_resultado(const std::string& job_id, const char* extensao) const {
    return resultados_.ler(job_id, extensao);
}

void Fila::parar_despacho() {
    const std::lock_guard<std::mutex> guarda(trava_);
    parar_ = true;
    cv_despachante_.notify_all();
    cv_workers_.notify_all();
}

void Fila::aguardar_fim() {
    if (!despachante_.joinable()) {
        return;  // já esperou
    }
    juntar_threads();
    const std::lock_guard<std::mutex> guarda(trava_);
    if (!fila_.empty()) {
        std::fprintf(stderr, "encerrando com %zu tarefas não iniciadas\n", fila_.size());
    }
}

void Fila::juntar_threads() {
    if (despachante_.joinable()) {
        despachante_.join();
    }
    for (auto& worker : workers_) {
        if (worker.joinable()) {
            worker.join();
        }
    }
}

void Fila::registrar_evento(const char* evento, const std::string& job_id) {
    const auto tarefa = tarefas_.find(job_id);
    eventos_.registrar(evento, job_id, fila_.size(), em_execucao_,
                       tarefa == tarefas_.end() ? nullptr : tarefa->second.get());
}
