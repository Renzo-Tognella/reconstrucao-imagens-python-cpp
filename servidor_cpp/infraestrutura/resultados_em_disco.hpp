#pragma once

#include "aplicacao/portas/resultados.hpp"

#include <filesystem>
#include <string>

class ResultadosEmDisco : public ArmazemResultados {
public:
    explicit ResultadosEmDisco(const std::filesystem::path& saida);

    void gravar_resultado(const std::string& job_id, const Resultado& resultado, const Modelo& modelo) const override;
    void gravar_json(const Tarefa& tarefa) const override;
    std::string ler(const std::string& job_id, const char* extensao) const override;

private:
    std::filesystem::path caminho(const std::string& job_id, const char* extensao) const;

    std::filesystem::path jobs_;
};
