#include "http/erros.hpp"
#include "http/rotas/rotas.hpp"

namespace {

void consultar_pedido(const httplib::Request& req, httplib::Response& res, const Fila& fila) {
    const auto corpo = fila.consultar(req.path_params.at("id"));
    if (!corpo.has_value()) {
        responder_tarefa_desconhecida(res);
        return;
    }
    responder_json(res, httplib::StatusCode::OK_200, *corpo);
}

}

void registrar_consulta_de_pedido(httplib::Server& servidor, const Fila& fila) {
    servidor.Get("/jobs/:id", [&fila](const httplib::Request& req, httplib::Response& res) {
        consultar_pedido(req, res, fila);
    });
}
