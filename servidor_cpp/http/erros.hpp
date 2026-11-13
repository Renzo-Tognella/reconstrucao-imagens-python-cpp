// Respostas JSON e o formato único de erro {"error", "detail"} de todas as rotas.
#pragma once

#include <httplib.h>

#include <exception>
#include <nlohmann/json.hpp>
#include <string>

using Json = nlohmann::ordered_json;

void responder_json(httplib::Response& res, int status, const Json& corpo);
void responder_erro(httplib::Response& res, int status, const std::string& codigo, const std::string& detalhe);
void responder_tarefa_desconhecida(httplib::Response& res);

// Rota inexistente, corpo grande demais e outros erros que a biblioteca detecta antes da rota.
httplib::Server::HandlerResponse tratar_erro_http(const httplib::Request& req, httplib::Response& res);
// Exceção que escapou de uma rota: vira 500 sem expor o detalhe ao cliente.
void tratar_excecao(const httplib::Request& req, httplib::Response& res, const std::exception_ptr& ponteiro);
