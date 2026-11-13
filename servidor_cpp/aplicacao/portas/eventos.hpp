// Linha do tempo das tarefas (accepted, started, finished, failed, rejected). Implementado em
// infraestrutura/eventos_jsonl.hpp.
#pragma once

#include <cstddef>
#include <string>

// Sem trava própria: a Fila só chama registrar() segurando a trava dela.
class RegistroEventos {
public:
    virtual ~RegistroEventos() = default;

    virtual void registrar(const char* evento, const std::string& job_id, std::size_t queue_depth,
                           std::size_t running) = 0;
};
