// Uma linha legível no terminal para cada evento da fila; o registro completo continua em events.jsonl.
#pragma once

#include <cstddef>
#include <string>

struct Tarefa;

namespace log_terminal {

std::string linha_evento(const char* evento, const std::string& job_id, const Tarefa* tarefa,
                         std::size_t fila, std::size_t rodando);
std::string cabecalho();
// Escreve e descarrega na hora; terminal fechado não derruba a fila.
void escrever(const std::string& linha);

}  // namespace log_terminal
