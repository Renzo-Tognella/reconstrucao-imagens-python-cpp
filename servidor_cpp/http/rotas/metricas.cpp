#include "http/erros.hpp"
#include "http/rotas/rotas.hpp"

#include <string>

namespace {

Json corpo_info(const CatalogoModelos& catalogo, const InfoServidor& info) {
    Json corpo;
    corpo["implementation"] = "cpp";
    corpo["language_version"] = "C++" + std::to_string(__cplusplus / 100 % 100) + " (" + __VERSION__ + ")";
    corpo["blas"] = info.blas;
    corpo["workers"] = info.workers;
    corpo["blas_threads"] = info.blas_threads;
    corpo["models"] = catalogo.nomes();
    corpo["aquecimento_s"] = info.aquecimento_s;
    return corpo;
}

}

void registrar_metricas_e_info(httplib::Server& servidor, const Fila& fila, const CatalogoModelos& catalogo,
                               const InfoServidor& info) {
    servidor.Get("/metrics", [&fila](const httplib::Request&, httplib::Response& res) {
        responder_json(res, httplib::StatusCode::OK_200, fila.metricas());
    });
    servidor.Get("/info", [&catalogo, &info](const httplib::Request&, httplib::Response& res) {
        responder_json(res, httplib::StatusCode::OK_200, corpo_info(catalogo, info));
    });
}
