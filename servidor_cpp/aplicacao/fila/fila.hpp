#pragma once

#include "aplicacao/fila/controle_memoria.hpp"
#include "aplicacao/fila/tarefa.hpp"
#include "aplicacao/metricas/contadores.hpp"
#include "aplicacao/portas/eventos.hpp"
#include "aplicacao/portas/modelos.hpp"
#include "aplicacao/portas/resultados.hpp"
#include "dominio/algoritmos/resultado.hpp"

#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
#include <nlohmann/json.hpp>
#include <optional>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

struct ConfiguracaoFila {
    std::size_t workers = 1;
    std::size_t fila_max = 256;
    std::uint64_t fila_max_bytes = 268435456;
    std::uint64_t reserva_bytes = 512ull * 1024 * 1024;
    double espera_mem_max_s = 60.0;
};

struct DependenciasFila {
    const CatalogoModelos& catalogo;
    const ArmazemResultados& resultados;
    RegistroEventos& eventos;
    std::function<std::uint64_t()> memoria_disponivel;
    std::uint64_t memoria_fisica;
    std::function<void()> preparar_worker;
};

enum class DesfechoEnvio { aceito, repetido, conflito, fila_cheia };

struct RespostaEnvio {
    DesfechoEnvio desfecho;
    EstadoTarefa estado;
};

class Fila {
public:
    Fila(ConfiguracaoFila configuracao, DependenciasFila dependencias);
    ~Fila();
    Fila(const Fila&) = delete;
    Fila& operator=(const Fila&) = delete;

    RespostaEnvio enviar(PedidoTarefa pedido);
    std::optional<nlohmann::ordered_json> consultar(const std::string& job_id) const;
    std::optional<EstadoTarefa> estado(const std::string& job_id) const;
    nlohmann::ordered_json metricas() const;
    std::string ler_resultado(const std::string& job_id, const char* extensao) const;

    void parar_despacho();
    void aguardar_fim();

private:
    struct ItemFila {
        Tarefa* tarefa;
        const Modelo* modelo;
        std::vector<double> sinal;
    };

    struct Despacho {
        ItemFila item;
        std::uint64_t custo;
    };

    struct Desfecho {
        EstadoTarefa estado = EstadoTarefa::failed;
        Conclusao conclusao;
    };

    enum class DecisaoCabeca { aguardar_aviso, aguardar_memoria, iniciar, falhar_sem_memoria };

    void laco_despachante();
    DecisaoCabeca avaliar_cabeca();
    ItemFila retirar_cabeca();
    void iniciar_cabeca();
    void falhar_cabeca_sem_memoria(std::unique_lock<std::mutex>& trava);

    void laco_worker();
    Desfecho executar(ItemFila& item);
    std::optional<Resultado> reconstruir_item(ItemFila& item, const Tarefa& tarefa, Desfecho& desfecho);
    void gravar_saidas(Tarefa& tarefa, const std::optional<Resultado>& resultado, const Modelo& modelo,
                       Desfecho& desfecho);
    std::optional<std::string> gravar_json(const Tarefa& tarefa) const;
    static void marcar_falha(Desfecho& desfecho, const std::string& job_id, const char* codigo, const char* detalhe);
    static void aplicar(Tarefa& tarefa, const Desfecho& desfecho);
    void encerrar_execucao(Tarefa& tarefa, const Desfecho& desfecho, std::uint64_t custo);

    void registrar_evento(const char* evento, const std::string& job_id);
    void juntar_threads();

    const ConfiguracaoFila configuracao_;
    const CatalogoModelos& catalogo_;
    const ArmazemResultados& resultados_;
    RegistroEventos& eventos_;
    const std::function<void()> preparar_worker_;
    const double inicio_mono_;

    mutable std::mutex trava_;
    std::condition_variable cv_despachante_;
    std::condition_variable cv_workers_;
    std::unordered_map<std::string, std::unique_ptr<Tarefa>> tarefas_;
    std::deque<ItemFila> fila_;
    std::deque<Despacho> prontos_;
    std::uint64_t bytes_na_fila_ = 0;
    std::size_t em_execucao_ = 0;
    ControleMemoria memoria_;
    Contadores contadores_;
    bool parar_ = false;

    std::vector<std::thread> workers_;
    std::thread despachante_;
};
