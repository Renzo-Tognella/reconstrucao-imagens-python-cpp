#pragma once

#include "aplicacao/fila/tarefa.hpp"
#include "aplicacao/portas/modelos.hpp"
#include "dominio/algoritmos/resultado.hpp"

#include <string>

class ArmazemResultados {
public:
    virtual ~ArmazemResultados() = default;

    virtual void gravar_resultado(const std::string& job_id, const Resultado& resultado, const Modelo& modelo) const = 0;
    virtual void gravar_json(const Tarefa& tarefa) const = 0;
    virtual std::string ler(const std::string& job_id, const char* extensao) const = 0;
};
