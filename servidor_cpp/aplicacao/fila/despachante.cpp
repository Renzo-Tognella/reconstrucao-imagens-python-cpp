// Thread despachante: olha a tarefa da frente da fila e decide se ela começa, espera ou falha.
#include "aplicacao/fila/fila.hpp"

#include "aplicacao/relogio.hpp"

#include <chrono>
#include <utility>

namespace {

constexpr auto INTERVALO_MEMORIA = std::chrono::milliseconds(100);

}  // namespace

void Fila::laco_despachante() {
    std::unique_lock<std::mutex> trava(trava_);
    while (!parar_) {
        switch (avaliar_cabeca()) {
            case DecisaoCabeca::aguardar_aviso:
                cv_despachante_.wait(trava);
                break;
            case DecisaoCabeca::aguardar_memoria:
                cv_despachante_.wait_for(trava, INTERVALO_MEMORIA);
                break;
            case DecisaoCabeca::iniciar:
                iniciar_cabeca();
                break;
            case DecisaoCabeca::falhar_sem_memoria:
                falhar_cabeca_sem_memoria(trava);
                break;
        }
    }
}

Fila::DecisaoCabeca Fila::avaliar_cabeca() {
    if (fila_.empty()) {
        return DecisaoCabeca::aguardar_aviso;
    }
    const Modelo& modelo = *fila_.front().modelo;
    if (memoria_.nunca_cabe(modelo)) {
        memoria_.encerrar_espera();
        return DecisaoCabeca::falhar_sem_memoria;
    }
    if (em_execucao_ >= configuracao_.workers) {
        return DecisaoCabeca::aguardar_aviso;
    }
    switch (memoria_.avaliar(modelo, em_execucao_)) {
        case DecisaoMemoria::iniciar: return DecisaoCabeca::iniciar;
        case DecisaoMemoria::aguardar: return DecisaoCabeca::aguardar_memoria;
        case DecisaoMemoria::falhar: return DecisaoCabeca::falhar_sem_memoria;
    }
    return DecisaoCabeca::aguardar_memoria;
}

Fila::ItemFila Fila::retirar_cabeca() {
    ItemFila item = std::move(fila_.front());
    fila_.pop_front();
    bytes_na_fila_ -= item.sinal.size() * sizeof(double);
    return item;
}

void Fila::iniciar_cabeca() {
    const std::uint64_t custo = custo_em_bytes(*fila_.front().modelo);
    ItemFila item = retirar_cabeca();
    memoria_.reservar(custo);
    ++em_execucao_;
    Tarefa& tarefa = *item.tarefa;
    tarefa.estado = EstadoTarefa::running;
    tarefa.started_at = relogio::agora_iso();
    tarefa.queue_wait_s = relogio::segundos_monotonicos() - tarefa.recebida_mono;
    registrar_evento("started", tarefa.job_id);
    prontos_.push_back(Despacho{std::move(item), custo});
    cv_workers_.notify_one();
}

void Fila::falhar_cabeca_sem_memoria(std::unique_lock<std::mutex>& trava) {
    const ItemFila item = retirar_cabeca();
    Tarefa& tarefa = *item.tarefa;
    tarefa.estado = EstadoTarefa::failed;
    tarefa.conclusao.finished_at = relogio::agora_iso();
    tarefa.conclusao.error = "insufficient_memory";
    ++contadores_.falhas;
    registrar_evento("failed", tarefa.job_id);
    const Tarefa copia = tarefa;
    trava.unlock();
    gravar_json(copia);
    trava.lock();
}
