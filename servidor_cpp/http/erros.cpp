#include "http/erros.hpp"

#include <cstdio>

void responder_json(httplib::Response& res, int status, const Json& corpo) {
    res.status = status;
    // replace: o detalhe de 404 ecoa o caminho do pedido, que pode não ser UTF-8 válido.
    res.set_content(corpo.dump(-1, ' ', false, Json::error_handler_t::replace), "application/json");
}

void responder_erro(httplib::Response& res, int status, const std::string& codigo, const std::string& detalhe) {
    responder_json(res, status, Json{{"error", codigo}, {"detail", detalhe}});
}

void responder_tarefa_desconhecida(httplib::Response& res) {
    responder_erro(res, httplib::StatusCode::NotFound_404, "not_found", "tarefa desconhecida");
}

httplib::Server::HandlerResponse tratar_erro_http(const httplib::Request& req, httplib::Response& res) {
    if (!res.body.empty()) {
        return httplib::Server::HandlerResponse::Unhandled;
    }
    if (res.status == httplib::StatusCode::NotFound_404) {
        responder_erro(res, res.status, "not_found", "rota desconhecida: " + req.method + " " + req.path);
    } else if (res.status == httplib::StatusCode::PayloadTooLarge_413) {
        responder_erro(res, res.status, "payload_too_large", "corpo maior que o maior modelo aceito");
    } else {
        responder_erro(res, res.status, "http_error", "pedido HTTP não atendido");
    }
    return httplib::Server::HandlerResponse::Handled;
}

void tratar_excecao(const httplib::Request& req, httplib::Response& res, const std::exception_ptr& ponteiro) {
    std::string detalhe = "exceção desconhecida";
    try {
        std::rethrow_exception(ponteiro);
    } catch (const std::exception& erro) {
        detalhe = erro.what();
    } catch (...) {
    }
    std::fprintf(stderr, "erro em %s %s: %s\n", req.method.c_str(), req.path.c_str(), detalhe.c_str());
    responder_erro(res, httplib::StatusCode::InternalServerError_500, "internal_error", "falha interna do servidor");
}
