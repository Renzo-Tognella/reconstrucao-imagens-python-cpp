#pragma once

#include <httplib.h>

#include <exception>
#include <nlohmann/json.hpp>
#include <string>

using Json = nlohmann::ordered_json;

void responder_json(httplib::Response& res, int status, const Json& corpo);
void responder_erro(httplib::Response& res, int status, const std::string& codigo, const std::string& detalhe);
void responder_tarefa_desconhecida(httplib::Response& res);

httplib::Server::HandlerResponse tratar_erro_http(const httplib::Request& req, httplib::Response& res);
void tratar_excecao(const httplib::Request& req, httplib::Response& res, const std::exception_ptr& ponteiro);
