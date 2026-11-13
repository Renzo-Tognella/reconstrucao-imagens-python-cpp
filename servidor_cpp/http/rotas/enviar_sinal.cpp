// POST /jobs: recebe o sinal g e coloca a tarefa na fila.
#include "http/erros.hpp"
#include "http/rotas/rotas.hpp"
#include "http/validacao_pedido.hpp"

#include <optional>
#include <string>
#include <utility>
#include <variant>

namespace {

std::optional<std::string> parametro(const httplib::Request& req, const char* nome) {
    if (!req.has_param(nome)) {
        return std::nullopt;
    }
    return req.get_param_value(nome);
}

ParametrosPedido parametros_do_pedido(const httplib::Request& req) {
    return {parametro(req, "job_id"), parametro(req, "client_id"), parametro(req, "signal_id"),
            parametro(req, "model"),  parametro(req, "algorithm"), parametro(req, "gain")};
}

void responder_envio(httplib::Response& res, const std::string& job_id, const RespostaEnvio& resposta) {
    switch (resposta.desfecho) {
        case DesfechoEnvio::aceito:
            responder_json(res, httplib::StatusCode::Accepted_202, Json{{"job_id", job_id}, {"status", "queued"}});
            return;
        case DesfechoEnvio::repetido:
            responder_json(res, httplib::StatusCode::OK_200,
                           Json{{"job_id", job_id}, {"status", nome_do_estado(resposta.estado)}});
            return;
        case DesfechoEnvio::conflito:
            responder_erro(res, httplib::StatusCode::Conflict_409, "job_conflict",
                           "job_id já usado com corpo ou metadados diferentes");
            return;
        case DesfechoEnvio::fila_cheia:
            responder_erro(res, httplib::StatusCode::ServiceUnavailable_503, "queue_full", "fila cheia");
            return;
    }
}

void enviar_sinal(const httplib::Request& req, httplib::Response& res, Fila& fila, const CatalogoModelos& catalogo) {
    auto lido = ler_pedido(parametros_do_pedido(req), req.body, catalogo);
    if (const auto* recusa = std::get_if<RecusaPedido>(&lido)) {
        responder_erro(res, httplib::StatusCode::BadRequest_400, recusa->codigo, recusa->detalhe);
        return;
    }
    PedidoTarefa& pedido = std::get<PedidoTarefa>(lido);
    const std::string job_id = pedido.job_id;
    responder_envio(res, job_id, fila.enviar(std::move(pedido)));
}

}  // namespace

void registrar_envio_de_sinal(httplib::Server& servidor, Fila& fila, const CatalogoModelos& catalogo) {
    servidor.Post("/jobs", [&fila, &catalogo](const httplib::Request& req, httplib::Response& res) {
        enviar_sinal(req, res, fila, catalogo);
    });
}
