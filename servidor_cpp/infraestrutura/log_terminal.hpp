#pragma once

#include <cstddef>
#include <string>

struct Tarefa;

namespace log_terminal {

std::string linha_evento(const char* evento, const std::string& job_id, const Tarefa* tarefa,
                         std::size_t fila, std::size_t rodando);
std::string cabecalho();
void escrever(const std::string& linha);

}
