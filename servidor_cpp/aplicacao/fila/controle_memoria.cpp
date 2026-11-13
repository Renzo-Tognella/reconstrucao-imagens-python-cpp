#include "aplicacao/fila/controle_memoria.hpp"

#include "aplicacao/relogio.hpp"

#include <utility>

std::uint64_t custo_em_bytes(const Modelo& modelo) {
    return 8 * (2 * static_cast<std::uint64_t>(modelo.linhas()) + 3 * static_cast<std::uint64_t>(modelo.colunas()));
}

ControleMemoria::ControleMemoria(std::function<std::uint64_t()> memoria_disponivel, std::uint64_t memoria_fisica,
                                 std::uint64_t reserva, double espera_max_s)
    : memoria_disponivel_(std::move(memoria_disponivel)),
      memoria_fisica_(memoria_fisica),
      reserva_(reserva),
      espera_max_s_(espera_max_s) {}

// Nem esperando caberia, então a tarefa falha sem gastar o prazo. Soma em vez de subtração: a
// reserva pode passar da memória física.
bool ControleMemoria::nunca_cabe(const Modelo& modelo) const {
    if (modelo.mapeado()) {
        return false;
    }
    return 8 * static_cast<std::uint64_t>(modelo.linhas()) * modelo.colunas() + reserva_ > memoria_fisica_;
}

DecisaoMemoria ControleMemoria::avaliar(const Modelo& modelo, std::size_t em_execucao) {
    if (memoria_disponivel_() >= reservado_ + custo_em_bytes(modelo) + reserva_) {
        encerrar_espera();
        return DecisaoMemoria::iniciar;
    }
    esperando_ = true;
    // O prazo conta só o tempo contínuo sem nada em execução: a tarefa que termina devolve
    // memória, e a cabeça merece o prazo inteiro depois disso.
    if (em_execucao > 0) {
        sem_execucao_desde_.reset();
        return DecisaoMemoria::aguardar;
    }
    if (prazo_vencido()) {
        encerrar_espera();
        return DecisaoMemoria::falhar;
    }
    return DecisaoMemoria::aguardar;
}

void ControleMemoria::encerrar_espera() {
    esperando_ = false;
    sem_execucao_desde_.reset();
}

bool ControleMemoria::prazo_vencido() {
    const double agora = relogio::segundos_monotonicos();
    if (!sem_execucao_desde_.has_value()) {
        sem_execucao_desde_ = agora;
    }
    return agora - *sem_execucao_desde_ > espera_max_s_;
}
