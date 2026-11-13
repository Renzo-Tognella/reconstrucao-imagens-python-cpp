// Threads worker: rodam a reconstrução, gravam os arquivos e marcam a tarefa como done ou failed.
#include "aplicacao/fila/fila.hpp"

#include "aplicacao/relogio.hpp"
#include "dominio/algoritmos/reconstrucao.hpp"

#include <cstdio>
#include <exception>
#include <new>
#include <utility>

void Fila::laco_worker() {
    std::unique_lock<std::mutex> trava(trava_);
    // Sob a trava: limitar as threads da OpenBLAS também ajusta buffers globais dela.
    if (preparar_worker_) {
        preparar_worker_();
    }
    while (true) {
        cv_workers_.wait(trava, [this] { return parar_ || !prontos_.empty(); });
        if (prontos_.empty()) {
            return;
        }
        Despacho despacho = std::move(prontos_.front());
        prontos_.pop_front();
        trava.unlock();

        const Desfecho desfecho = executar(despacho.item);

        trava.lock();
        encerrar_execucao(*despacho.item.tarefa, desfecho, despacho.custo);
    }
}

Fila::Desfecho Fila::executar(ItemFila& item) {
    Tarefa tarefa;
    {
        // Campos de identificação e início: lidos sob trava, porque consultas concorrem.
        const std::lock_guard<std::mutex> guarda(trava_);
        tarefa = *item.tarefa;
    }
    Desfecho desfecho;
    const std::optional<Resultado> resultado = reconstruir_item(item, tarefa, desfecho);
    desfecho.conclusao.finished_at = relogio::agora_iso();
    gravar_saidas(tarefa, resultado, *item.modelo, desfecho);
    return desfecho;
}

std::optional<Resultado> Fila::reconstruir_item(ItemFila& item, const Tarefa& tarefa, Desfecho& desfecho) {
    try {
        const MatrizColunas H = item.modelo->matriz();
        const double inicio = relogio::segundos_monotonicos();
        Resultado resultado = reconstruir(tarefa.algoritmo, H, std::move(item.sinal));
        desfecho.conclusao.duration_s = relogio::segundos_monotonicos() - inicio;
        return resultado;
    } catch (const FalhaNumerica& erro) {
        marcar_falha(desfecho, tarefa.job_id, "numerical_failure", erro.what());
    } catch (const std::bad_alloc& erro) {
        marcar_falha(desfecho, tarefa.job_id, "insufficient_memory", erro.what());
    } catch (const std::exception& erro) {
        marcar_falha(desfecho, tarefa.job_id, "internal_error", erro.what());
    }
    return std::nullopt;
}

void Fila::gravar_saidas(Tarefa& tarefa, const std::optional<Resultado>& resultado, const Modelo& modelo,
                         Desfecho& desfecho) {
    if (resultado.has_value()) {
        desfecho.estado = EstadoTarefa::done;
        desfecho.conclusao.iterations = resultado->iterations;
        desfecho.conclusao.stop_reason = nome_do_motivo(resultado->motivo);
        desfecho.conclusao.residual_norms = resultado->residual_norms;
        try {
            // O status só vira done depois dos arquivos: quem vê done já consegue baixar o resultado.
            resultados_.gravar_resultado(tarefa.job_id, *resultado, modelo);
        } catch (const std::exception& erro) {
            marcar_falha(desfecho, tarefa.job_id, "output_write_failed", erro.what());
        }
    }
    aplicar(tarefa, desfecho);
    const std::optional<std::string> erro_json = gravar_json(tarefa);
    if (erro_json.has_value() && desfecho.estado == EstadoTarefa::done) {
        marcar_falha(desfecho, tarefa.job_id, "output_write_failed", erro_json->c_str());
    }
}

std::optional<std::string> Fila::gravar_json(const Tarefa& tarefa) const {
    try {
        resultados_.gravar_json(tarefa);
        return std::nullopt;
    } catch (const std::exception& erro) {
        std::fprintf(stderr, "tarefa %s: JSON não gravado: %s\n", tarefa.job_id.c_str(), erro.what());
        return erro.what();
    }
}

void Fila::marcar_falha(Desfecho& desfecho, const std::string& job_id, const char* codigo, const char* detalhe) {
    std::fprintf(stderr, "tarefa %s falhou (%s): %s\n", job_id.c_str(), codigo, detalhe);
    desfecho.estado = EstadoTarefa::failed;
    desfecho.conclusao.error = codigo;
}

void Fila::aplicar(Tarefa& tarefa, const Desfecho& desfecho) {
    tarefa.estado = desfecho.estado;
    tarefa.conclusao = desfecho.conclusao;
}

void Fila::encerrar_execucao(Tarefa& tarefa, const Desfecho& desfecho, std::uint64_t custo) {
    aplicar(tarefa, desfecho);
    memoria_.devolver(custo);
    --em_execucao_;
    if (desfecho.estado == EstadoTarefa::done) {
        ++contadores_.concluidas;
        registrar_evento("finished", tarefa.job_id);
    } else {
        ++contadores_.falhas;
        registrar_evento("failed", tarefa.job_id);
    }
    cv_despachante_.notify_one();
}
