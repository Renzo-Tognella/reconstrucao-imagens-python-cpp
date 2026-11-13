// Ponto de entrada: lê a linha de comando, liga cada camada à infraestrutura e roda até SIGTERM.
#include "aplicacao/fila/fila.hpp"
#include "aplicacao/relogio.hpp"
#include "http/servidor_http.hpp"
#include "infraestrutura/blas.hpp"
#include "infraestrutura/eventos_jsonl.hpp"
#include "infraestrutura/log_terminal.hpp"
#include "infraestrutura/manifesto.hpp"
#include "infraestrutura/matriz_mapeada.hpp"
#include "infraestrutura/resultados_em_disco.hpp"
#include "infraestrutura/sistema.hpp"
#include "linha_de_comando.hpp"

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <exception>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {

std::atomic<bool> pedido_encerramento{false};
std::atomic<bool> escuta_terminou{false};
static_assert(std::atomic<bool>::is_always_lock_free, "o handler de sinal só pode usar atômicos sem trava");

extern "C" void ao_receber_sinal(int) { pedido_encerramento.store(true); }

// Valida todos antes de aquecer o primeiro: nome errado falha sem custo de leitura.
double aquecer_modelos(const CatalogoModelos& catalogo, const std::vector<std::string>& nomes) {
    std::vector<const Modelo*> modelos;
    for (const std::string& nome : nomes) {
        const Modelo* modelo = catalogo.procurar(nome);
        if (modelo == nullptr) {
            throw std::invalid_argument("--aquecer: modelo desconhecido: " + nome);
        }
        modelos.push_back(modelo);
    }
    const double inicio = relogio::segundos_monotonicos();
    for (const Modelo* modelo : modelos) {
        aquecer_modelo(*modelo);
    }
    return modelos.empty() ? 0.0 : relogio::segundos_monotonicos() - inicio;
}

ConfiguracaoFila configuracao_da_fila(const Opcoes& opcoes) {
    ConfiguracaoFila configuracao;
    configuracao.workers = opcoes.workers;
    configuracao.fila_max = opcoes.fila_max;
    configuracao.fila_max_bytes = opcoes.fila_max_bytes;
    configuracao.reserva_bytes = opcoes.reserva_mem_mb * 1024 * 1024;
    configuracao.espera_mem_max_s = static_cast<double>(opcoes.espera_mem_max_s);
    return configuracao;
}

std::string juntar(const std::vector<std::string>& nomes) {
    std::string texto;
    for (const std::string& nome : nomes) {
        texto += (texto.empty() ? "" : ", ") + nome;
    }
    return texto;
}

void anunciar(const Opcoes& opcoes, const CatalogoModelos& catalogo, double aquecimento_s, int blas_threads) {
    char aquecimento[32];
    std::snprintf(aquecimento, sizeof aquecimento, "%.2f s", aquecimento_s);
    std::string aquecimento_txt(aquecimento);
    for (char& c : aquecimento_txt) {
        c = c == '.' ? ',' : c;
    }
    const std::string aquecidos =
        opcoes.aquecer.empty() ? "" : "; aquecido: " + juntar(opcoes.aquecer) + " em " + aquecimento_txt;
    for (const std::string& linha : {
             "Servidor C++ em http://127.0.0.1:" + std::to_string(*opcoes.porta) + " (Ctrl+C para parar)",
             "  " + std::to_string(opcoes.workers) + " reconstruções ao mesmo tempo, " + std::to_string(blas_threads) +
                 " thread BLAS em cada uma, BLAS " + blas::descricao_backend(),
             "  Modelos: " + juntar(catalogo.nomes()) + aquecidos,
             "  Eventos também em " + opcoes.saida + "/events.jsonl",
             std::string(),
             log_terminal::cabecalho(),
         }) {
        log_terminal::escrever(linha);
    }
}

// O handler só marca o pedido; parar o servidor aloca e espera, então acontece aqui.
void esperar_encerramento() {
    while (!pedido_encerramento.load() && !escuta_terminou.load()) {
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const Opcoes opcoes = ler_opcoes(argc, argv);

        std::signal(SIGPIPE, SIG_IGN);
        std::signal(SIGTERM, ao_receber_sinal);
        std::signal(SIGINT, ao_receber_sinal);

        const int blas_threads = static_cast<int>(opcoes.blas_threads);
        blas::configurar_threads(blas_threads);

        const CatalogoManifesto catalogo(opcoes.dados);
        const double aquecimento_s = aquecer_modelos(catalogo, opcoes.aquecer);

        const std::uint64_t memoria_fisica = sistema::memoria_fisica_total_bytes();
        const ResultadosEmDisco resultados(opcoes.saida);
        EventosJsonl eventos(opcoes.saida);
        Fila fila(configuracao_da_fila(opcoes),
                  DependenciasFila{catalogo, resultados, eventos, sistema::memoria_disponivel_bytes, memoria_fisica,
                                   [blas_threads] { blas::limitar_thread_atual(blas_threads); }});
        ServidorHttp http(fila, catalogo,
                          InfoServidor{opcoes.workers, blas_threads, aquecimento_s, blas::descricao_backend()});
        http.ligar(*opcoes.porta);
        anunciar(opcoes, catalogo, aquecimento_s, blas_threads);
        std::thread escuta([&http] {
            http.escutar();
            escuta_terminou.store(true);
        });

        esperar_encerramento();
        fila.parar_despacho();
        if (!escuta_terminou.load()) {
            http.parar();
        }
        escuta.join();
        fila.aguardar_fim();
        return pedido_encerramento.load() ? 0 : 1;
    } catch (const std::exception& erro) {
        std::fprintf(stderr, "servidor_cpp: %s\n", erro.what());
        return 1;
    }
}
