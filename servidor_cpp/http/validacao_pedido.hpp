// Confere os parâmetros e o corpo de POST /jobs e monta o pedido da tarefa, ou diz o motivo da recusa.
#pragma once

#include "aplicacao/fila/tarefa.hpp"
#include "aplicacao/portas/modelos.hpp"

#include <optional>
#include <string>
#include <variant>

struct ParametrosPedido {
    std::optional<std::string> job_id;
    std::optional<std::string> client_id;
    std::optional<std::string> signal_id;
    std::optional<std::string> model;
    std::optional<std::string> algorithm;
    std::optional<std::string> gain;
};

struct RecusaPedido {
    std::string codigo;
    std::string detalhe;
};

std::variant<PedidoTarefa, RecusaPedido> ler_pedido(const ParametrosPedido& parametros, const std::string& corpo,
                                                    const CatalogoModelos& catalogo);
