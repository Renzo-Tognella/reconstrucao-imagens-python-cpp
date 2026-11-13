// Cada rota mora no seu arquivo e se registra no servidor por uma destas funções.
#pragma once

#include "aplicacao/fila/fila.hpp"
#include "aplicacao/portas/modelos.hpp"
#include "http/servidor_http.hpp"

#include <httplib.h>

// POST /jobs (enviar_sinal.cpp)
void registrar_envio_de_sinal(httplib::Server& servidor, Fila& fila, const CatalogoModelos& catalogo);
// GET /jobs/{id} (consultar_pedido.cpp)
void registrar_consulta_de_pedido(httplib::Server& servidor, const Fila& fila);
// GET /jobs/{id}/image e /jobs/{id}/vector (baixar_resultado.cpp)
void registrar_download_de_resultado(httplib::Server& servidor, const Fila& fila);
// GET /metrics e GET /info (metricas.cpp)
void registrar_metricas_e_info(httplib::Server& servidor, const Fila& fila, const CatalogoModelos& catalogo,
                               const InfoServidor& info);
