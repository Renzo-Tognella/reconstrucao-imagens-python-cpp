#include "aplicacao/fila/fila.hpp"
#include "infraestrutura/blas.hpp"
#include "infraestrutura/eventos_jsonl.hpp"
#include "infraestrutura/manifesto.hpp"
#include "infraestrutura/matriz_mapeada.hpp"
#include "infraestrutura/resultados_em_disco.hpp"
#include "infraestrutura/sistema.hpp"
#include "testes/verificacao.hpp"

#include <unistd.h>

#include <atomic>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <functional>
#include <memory>
#include <nlohmann/json.hpp>
#include <string>
#include <thread>
#include <vector>

namespace {

void teste_crc32_igual_ao_zlib() {
    const std::string texto = "123456789";
    verificar(crc32(texto.data(), texto.size()) == 0xCBF43926u, "crc32 do vetor de teste");
    verificar(crc32(nullptr, 0) == 0u, "crc32 vazio");
}

class ModeloTemporario {
public:
    ModeloTemporario(std::size_t linhas, std::size_t colunas) : linhas_(linhas), colunas_(colunas) {
        pasta_ = std::filesystem::temp_directory_path() /
                 ("teste_fila_" + std::to_string(getpid()) + "_" + std::to_string(contador_++));
        std::filesystem::create_directories(pasta_);
        // Valores pseudoaleatórios fixos: mantêm as 10 iterações do CGNR.
        std::vector<double> H(linhas * colunas);
        std::uint64_t estado = 88172645463325252ull;
        for (double& valor : H) {
            estado ^= estado << 13;
            estado ^= estado >> 7;
            estado ^= estado << 17;
            valor = static_cast<double>(estado % 2000) / 1000.0 - 1.0;
        }
        std::ofstream(pasta_ / "H.f64", std::ios::binary)
            .write(reinterpret_cast<const char*>(H.data()), static_cast<std::streamsize>(8 * H.size()));
        const nlohmann::json manifesto = {
            {"modelos",
             {{"m",
               {{"linhas", linhas}, {"colunas", colunas}, {"largura", 1}, {"altura", colunas}, {"arquivo", "H.f64"}}}}}};
        std::ofstream(pasta_ / "manifesto.json") << manifesto.dump();
    }
    ~ModeloTemporario() {
        std::error_code ignorado;
        std::filesystem::remove_all(pasta_, ignorado);
    }
    ModeloTemporario(const ModeloTemporario&) = delete;
    ModeloTemporario& operator=(const ModeloTemporario&) = delete;

    const std::filesystem::path& pasta() const { return pasta_; }
    std::uint64_t custo() const { return 8 * (2 * linhas_ + 3 * colunas_); }

    PedidoTarefa pedido(const std::string& job_id) const {
        PedidoTarefa pedido;
        pedido.job_id = job_id;
        pedido.client_id = "c";
        pedido.signal_id = "s";
        pedido.modelo = "m";
        pedido.sinal.resize(linhas_);
        for (std::size_t i = 0; i < linhas_; ++i) {
            pedido.sinal[i] = 1000.0 + static_cast<double>(i % 97);
        }
        return pedido;
    }

private:
    static inline int contador_ = 0;
    std::size_t linhas_;
    std::size_t colunas_;
    std::filesystem::path pasta_;
};

nlohmann::ordered_json aguardar_tarefa(const Fila& fila, const std::string& job_id, double limite_s) {
    const auto fim = std::chrono::steady_clock::now() + std::chrono::duration<double>(limite_s);
    while (std::chrono::steady_clock::now() < fim) {
        const auto corpo = fila.consultar(job_id);
        if (corpo.has_value() && ((*corpo)["status"] == "done" || (*corpo)["status"] == "failed")) {
            return *corpo;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    return nullptr;
}

bool terminou_com(const nlohmann::ordered_json& corpo, const char* status, const char* erro) {
    if (corpo.is_null() || corpo["status"] != status) {
        return false;
    }
    return erro == nullptr ? corpo["error"].is_null() : corpo["error"] == erro;
}

struct CenarioFila {
    ConfiguracaoFila configuracao;
    std::filesystem::path saida;
    std::function<std::uint64_t()> memoria_disponivel = sistema::memoria_disponivel_bytes;
};

CenarioFila cenario_de_teste(const ModeloTemporario& modelo) {
    CenarioFila cenario;
    cenario.saida = modelo.pasta() / "saida";
    cenario.configuracao.reserva_bytes = 0;
    return cenario;
}

// Mesma infraestrutura do servidor; o cenário só troca a fonte de memória.
struct FilaDeTeste {
    ResultadosEmDisco resultados;
    EventosJsonl eventos;
    Fila fila;

    FilaDeTeste(const CenarioFila& cenario, const CatalogoModelos& catalogo)
        : resultados(cenario.saida),
          eventos(cenario.saida),
          fila(cenario.configuracao,
               DependenciasFila{catalogo, resultados, eventos, cenario.memoria_disponivel,
                                sistema::memoria_fisica_total_bytes(), [] { blas::limitar_thread_atual(1); }}) {}
};

void teste_custo_nao_inclui_H() {
    const ModeloTemporario modelo(40, 20);
    const CatalogoManifesto catalogo(modelo.pasta());
    auto cenario = cenario_de_teste(modelo);
    cenario.configuracao.espera_mem_max_s = 0.05;
    const std::uint64_t custo = modelo.custo();
    cenario.memoria_disponivel = [custo] { return custo; };
    FilaDeTeste teste(cenario, catalogo);
    Fila& fila = teste.fila;
    fila.enviar(modelo.pedido("cabe_exato"));
    verificar(terminou_com(aguardar_tarefa(fila, "cabe_exato", 5.0), "done", nullptr),
              "memória igual ao custo, sem H, deve bastar");
}

void teste_um_byte_a_menos_espera_e_falha() {
    const ModeloTemporario modelo(40, 20);
    const CatalogoManifesto catalogo(modelo.pasta());
    auto cenario = cenario_de_teste(modelo);
    cenario.configuracao.espera_mem_max_s = 0.05;
    const std::uint64_t custo = modelo.custo();
    cenario.memoria_disponivel = [custo] { return custo - 1; };
    FilaDeTeste teste(cenario, catalogo);
    Fila& fila = teste.fila;
    fila.enviar(modelo.pedido("falta_um"));
    const auto corpo = aguardar_tarefa(fila, "falta_um", 5.0);
    verificar(terminou_com(corpo, "failed", "insufficient_memory"), "um byte a menos falha por memória");
    verificar(!corpo.is_null() && corpo["started_at"].is_null() && corpo["queue_wait_s"].is_null() &&
                  !corpo["finished_at"].is_null(),
              "recusa por memória: finished_at preenchido, started_at e queue_wait_s nulos");
}

void teste_H_maior_que_a_memoria_fisica_falha_na_hora() {
    const ModeloTemporario modelo(40, 20);
    const CatalogoManifesto catalogo(modelo.pasta());
    auto cenario = cenario_de_teste(modelo);
    cenario.configuracao.reserva_bytes = 1ull << 60;
    cenario.configuracao.espera_mem_max_s = 3600.0;
    FilaDeTeste teste(cenario, catalogo);
    Fila& fila = teste.fila;
    fila.enviar(modelo.pedido("nunca_cabe"));
    verificar(terminou_com(aguardar_tarefa(fila, "nunca_cabe", 3.0), "failed", "insufficient_memory"),
              "H maior que física - reserva falha sem esperar o prazo");
}

void teste_H_ja_mapeada_nao_falha_na_hora() {
    const ModeloTemporario modelo(40, 20);
    const CatalogoManifesto catalogo(modelo.pasta());
    catalogo.procurar("m")->matriz();
    auto cenario = cenario_de_teste(modelo);
    cenario.configuracao.reserva_bytes = 1ull << 60;
    cenario.configuracao.espera_mem_max_s = 0.4;
    FilaDeTeste teste(cenario, catalogo);
    Fila& fila = teste.fila;
    fila.enviar(modelo.pedido("espera_prazo"));
    std::this_thread::sleep_for(std::chrono::milliseconds(150));
    const auto parcial = fila.consultar("espera_prazo");
    verificar(parcial.has_value() && (*parcial)["status"] == "queued", "H já mapeada: espera o prazo");
    verificar(fila.metricas()["waiting_memory"] == true, "waiting_memory durante a espera");
    verificar(terminou_com(aguardar_tarefa(fila, "espera_prazo", 5.0), "failed", "insufficient_memory"),
              "H já mapeada: falha ao vencer o prazo");
}

// A cabeça espera enquanto a outra tarefa roda. O prazo só pode começar quando running chega a zero:
// mede a distância entre o fim de "longa" e a falha de "sem_memoria" nos t_mono de events.jsonl.
void teste_prazo_de_memoria_so_conta_com_nada_em_execucao() {
    const ModeloTemporario modelo(4000, 2000);
    const CatalogoManifesto catalogo(modelo.pasta());
    const double prazo = 0.01;
    auto cenario = cenario_de_teste(modelo);
    cenario.configuracao.workers = 2;
    cenario.configuracao.espera_mem_max_s = prazo;
    auto chamadas = std::make_shared<std::atomic<int>>(0);
    cenario.memoria_disponivel = [chamadas]() -> std::uint64_t { return chamadas->fetch_add(1) == 0 ? 1ull << 40 : 0; };
    double duracao_longa = 0.0;
    {
        FilaDeTeste teste(cenario, catalogo);
        Fila& fila = teste.fila;
        fila.enviar(modelo.pedido("longa"));
        while (chamadas->load() == 0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        fila.enviar(modelo.pedido("sem_memoria"));
        const auto longa = aguardar_tarefa(fila, "longa", 30.0);
        verificar(terminou_com(longa, "done", nullptr), "tarefa longa conclui");
        if (!longa.is_null() && longa["duration_s"].is_number()) {
            duracao_longa = longa["duration_s"].get<double>();
        }
        verificar(terminou_com(aguardar_tarefa(fila, "sem_memoria", 5.0), "failed", "insufficient_memory"),
                  "cabeça falha ao vencer o prazo");
    }
    verificar(duracao_longa > prazo, "pré-condição do teste: a tarefa longa dura mais que o prazo");
    double fim_longa = -1.0;
    double falha = -1.0;
    std::ifstream eventos(modelo.pasta() / "saida" / "events.jsonl");
    std::string linha;
    while (std::getline(eventos, linha)) {
        const auto evento = nlohmann::json::parse(linha);
        if (evento["event"] == "finished" && evento["job_id"] == "longa") {
            fim_longa = evento["t_mono"].get<double>();
        } else if (evento["event"] == "failed" && evento["job_id"] == "sem_memoria") {
            falha = evento["t_mono"].get<double>();
        }
    }
    verificar(fim_longa > 0.0 && falha > 0.0, "eventos da tarefa longa e da falha");
    verificar(falha - fim_longa >= prazo, "prazo zera enquanto há tarefa em execução (distância medida: " +
                                              std::to_string(falha - fim_longa) + " s)");
}

void teste_aquecer_mapeia_o_modelo() {
    const ModeloTemporario modelo(40, 20);
    const CatalogoManifesto catalogo(modelo.pasta());
    const Modelo* m = catalogo.procurar("m");
    verificar(!m->mapeado(), "modelo começa sem mapeamento");
    aquecer_modelo(*m);
    verificar(m->mapeado(), "aquecer mapeia H");
}

}  // namespace

int main() {
    blas::configurar_threads(1);
    teste_crc32_igual_ao_zlib();
    teste_custo_nao_inclui_H();
    teste_um_byte_a_menos_espera_e_falha();
    teste_H_maior_que_a_memoria_fisica_falha_na_hora();
    teste_H_ja_mapeada_nao_falha_na_hora();
    teste_prazo_de_memoria_so_conta_com_nada_em_execucao();
    teste_aquecer_mapeia_o_modelo();
    return resultado_final("teste_fila");
}
