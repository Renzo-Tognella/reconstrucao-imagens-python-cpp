#pragma once

#include <cstddef>
#include <string>

struct Tarefa;

class RegistroEventos {
public:
    virtual ~RegistroEventos() = default;

    virtual void registrar(const char* evento, const std::string& job_id, std::size_t queue_depth,
                           std::size_t running, const Tarefa* tarefa) = 0;
};
