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
                   std::size_t running, const Tarefa* tarefa) override;

private:
    std::ofstream arquivo_;
};
