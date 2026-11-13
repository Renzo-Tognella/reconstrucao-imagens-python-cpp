#include "http/validacao_pedido.hpp"

#include <cmath>
#include <cstring>
#include <utility>
#include <vector>

namespace {

RecusaPedido parametro_invalido(std::string detalhe) { return {"invalid_params", std::move(detalhe)}; }

bool identificador_valido(const std::string& valor) {
    if (valor.empty() || valor.size() > 128) {
        return false;
    }
    for (const char c : valor) {
        const bool alfanumerico = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9');
        if (!alfanumerico && c != '_' && c != '.' && c != '-') {
            return false;
        }
    }
    return true;
}

std::optional<RecusaPedido> copiar_identificador(const char* nome, const std::optional<std::string>& valor,
                                                 std::string& destino) {
    if (!valor.has_value()) {
        return parametro_invalido(std::string(nome) + " ausente");
    }
    if (!identificador_valido(*valor)) {
        return parametro_invalido(std::string(nome) + " aceita só [A-Za-z0-9_.-], de 1 a 128 caracteres");
    }
    destino = *valor;
    return std::nullopt;
}

std::optional<RecusaPedido> decodificar_sinal(const std::string& corpo, const Modelo& modelo,
                                              std::vector<double>& sinal) {
    if (corpo.size() != 8 * modelo.linhas()) {
        return RecusaPedido{"invalid_length", "corpo precisa ter " + std::to_string(8 * modelo.linhas()) + " bytes"};
    }
    sinal.resize(modelo.linhas());
    std::memcpy(sinal.data(), corpo.data(), corpo.size());
    for (const double amostra : sinal) {
        if (!std::isfinite(amostra)) {
            return RecusaPedido{"non_finite", "NaN ou infinito no sinal"};
        }
    }
    return std::nullopt;
}

}

std::variant<PedidoTarefa, RecusaPedido> ler_pedido(const ParametrosPedido& parametros, const std::string& corpo,
                                                    const CatalogoModelos& catalogo) {
    PedidoTarefa pedido;
    if (auto recusa = copiar_identificador("job_id", parametros.job_id, pedido.job_id)) {
        return *recusa;
    }
    if (auto recusa = copiar_identificador("client_id", parametros.client_id, pedido.client_id)) {
        return *recusa;
    }
    if (auto recusa = copiar_identificador("signal_id", parametros.signal_id, pedido.signal_id)) {
        return *recusa;
    }
    if (!parametros.model.has_value() || !parametros.algorithm.has_value() || !parametros.gain.has_value()) {
        return parametro_invalido("model, algorithm e gain são obrigatórios");
    }
    if (*parametros.gain != "0" && *parametros.gain != "1") {
        return parametro_invalido("gain precisa ser 0 ou 1");
    }
    pedido.gain = *parametros.gain == "1";
    pedido.modelo = *parametros.model;
    const Modelo* modelo = catalogo.procurar(pedido.modelo);
    if (modelo == nullptr) {
        return RecusaPedido{"unknown_model", "modelo desconhecido"};
    }
    const auto algoritmo = algoritmo_de_nome(*parametros.algorithm);
    if (!algoritmo.has_value()) {
        return RecusaPedido{"unknown_algorithm", "algoritmo desconhecido"};
    }
    pedido.algoritmo = *algoritmo;
    if (auto recusa = decodificar_sinal(corpo, *modelo, pedido.sinal)) {
        return *recusa;
    }
    return std::move(pedido);
}
