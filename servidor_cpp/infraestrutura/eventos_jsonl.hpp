// Linha do tempo das tarefas em <saida>/events.jsonl, um JSON por linha.
#pragma once

#include "aplicacao/portas/eventos.hpp"

#include <cstddef>
#include <filesystem>
#include <fstream>
#include <string>

class EventosJsonl : public RegistroEventos {
public:
    explicit EventosJsonl(const std::filesystem::path& saida);

    void registrar(const char* evento, const std::string& job_id, std::size_t queue_depth,
                   std::size_t running) override;

private:
    std::ofstream arquivo_;
};
