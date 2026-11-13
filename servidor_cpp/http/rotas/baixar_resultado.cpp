// GET /jobs/{id}/image (PGM) e GET /jobs/{id}/vector (f em float64): só com a tarefa em done.
#include "http/erros.hpp"
#include "http/rotas/rotas.hpp"

#include <string>

namespace {

void baixar_resultado(const httplib::Request& req, httplib::Response& res, const Fila& fila, const char* extensao,
                      const char* tipo) {
    const std::string& job_id = req.path_params.at("id");
    const auto estado = fila.estado(job_id);
    if (!estado.has_value()) {
        responder_tarefa_desconhecida(res);
    } else if (*estado == EstadoTarefa::failed) {
        responder_erro(res, httplib::StatusCode::Conflict_409, "failed", "tarefa terminou com falha");
    } else if (*estado != EstadoTarefa::done) {
        responder_erro(res, httplib::StatusCode::Conflict_409, "not_ready", "tarefa ainda não terminou");
    } else {
        res.status = httplib::StatusCode::OK_200;
        res.set_content(fila.ler_resultado(job_id, extensao), tipo);
    }
}

}  // namespace

void registrar_download_de_resultado(httplib::Server& servidor, const Fila& fila) {
    servidor.Get("/jobs/:id/image", [&fila](const httplib::Request& req, httplib::Response& res) {
        baixar_resultado(req, res, fila, ".pgm", "image/x-portable-graymap");
    });
    servidor.Get("/jobs/:id/vector", [&fila](const httplib::Request& req, httplib::Response& res) {
        baixar_resultado(req, res, fila, ".f64", "application/octet-stream");
    });
}
