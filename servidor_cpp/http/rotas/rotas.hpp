#pragma once

#include "aplicacao/fila/fila.hpp"
#include "aplicacao/portas/modelos.hpp"
#include "http/servidor_http.hpp"

#include <httplib.h>

void registrar_envio_de_sinal(httplib::Server& servidor, Fila& fila, const CatalogoModelos& catalogo);
void registrar_consulta_de_pedido(httplib::Server& servidor, const Fila& fila);
void registrar_download_de_resultado(httplib::Server& servidor, const Fila& fila);
void registrar_metricas_e_info(httplib::Server& servidor, const Fila& fila, const CatalogoModelos& catalogo,
                               const InfoServidor& info);
