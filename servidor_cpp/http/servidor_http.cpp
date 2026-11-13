#include "http/servidor_http.hpp"

#include "http/erros.hpp"
#include "http/rotas/rotas.hpp"

#include <httplib.h>
#include <sys/socket.h>

#include <stdexcept>
#include <string>
#include <utility>

namespace {

// Limitado de propósito: o trabalho pesado fica no pool de reconstrução, e estes threads só
// recebem corpo e respondem consultas.
constexpr std::size_t THREADS_HTTP = 32;
constexpr std::size_t PEDIDOS_EM_ESPERA = 256;
// Conexão ociosa e conexão muito longa devolvem o thread ao pool: sem isso, clientes com
// keep-alive ocupariam todo o pool e os demais nunca seriam atendidos.
constexpr int KEEP_ALIVE_S = 2;
constexpr std::size_t KEEP_ALIVE_MAX_PEDIDOS = 100;
constexpr int TIMEOUT_LEITURA_ESCRITA_S = 5;
constexpr std::size_t FOLGA_CORPO_BYTES = 1024 * 1024;

void configurar_conexoes(httplib::Server& servidor, std::size_t maior_linhas) {
    servidor.new_task_queue = [] { return new httplib::ThreadPool(THREADS_HTTP, PEDIDOS_EM_ESPERA); };
    servidor.set_payload_max_length(8 * maior_linhas + FOLGA_CORPO_BYTES);
    servidor.set_keep_alive_timeout(KEEP_ALIVE_S);
    servidor.set_keep_alive_max_count(KEEP_ALIVE_MAX_PEDIDOS);
    servidor.set_read_timeout(TIMEOUT_LEITURA_ESCRITA_S);
    servidor.set_write_timeout(TIMEOUT_LEITURA_ESCRITA_S);
    servidor.set_tcp_nodelay(true);
    // O padrão da biblioteca usa SO_REUSEPORT, que deixaria dois servidores dividirem a porta em silêncio.
    servidor.set_socket_options([](socket_t soquete) {
        const int ligado = 1;
        setsockopt(soquete, SOL_SOCKET, SO_REUSEADDR, &ligado, sizeof ligado);
    });
}

}  // namespace

struct ServidorHttp::Implementacao {
    const InfoServidor info;
    httplib::Server servidor;

    Implementacao(Fila& fila, const CatalogoModelos& catalogo, InfoServidor i) : info(std::move(i)) {
        configurar_conexoes(servidor, catalogo.maior_linhas());
        servidor.set_error_handler(tratar_erro_http);
        servidor.set_exception_handler(tratar_excecao);
        registrar_envio_de_sinal(servidor, fila, catalogo);
        registrar_consulta_de_pedido(servidor, fila);
        registrar_download_de_resultado(servidor, fila);
        registrar_metricas_e_info(servidor, fila, catalogo, info);
    }
};

ServidorHttp::ServidorHttp(Fila& fila, const CatalogoModelos& catalogo, InfoServidor info)
    : impl_(std::make_unique<Implementacao>(fila, catalogo, std::move(info))) {}

ServidorHttp::~ServidorHttp() = default;

void ServidorHttp::ligar(int porta) {
    if (!impl_->servidor.bind_to_port("127.0.0.1", porta)) {
        throw std::runtime_error("não ligou em 127.0.0.1:" + std::to_string(porta));
    }
}

void ServidorHttp::escutar() { impl_->servidor.listen_after_bind(); }

void ServidorHttp::parar() {
    // stop() antes de o laço de escuta começar seria ignorado e o servidor nunca sairia.
    impl_->servidor.wait_until_ready();
    impl_->servidor.stop();
}
