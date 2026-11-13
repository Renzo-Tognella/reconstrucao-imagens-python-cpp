#include "infraestrutura/resultados_em_disco.hpp"

#include "dominio/imagem.hpp"
#include "infraestrutura/arquivos.hpp"

ResultadosEmDisco::ResultadosEmDisco(const std::filesystem::path& saida) : jobs_(saida / "jobs") {
    std::filesystem::create_directories(jobs_);
}

std::filesystem::path ResultadosEmDisco::caminho(const std::string& job_id, const char* extensao) const {
    return jobs_ / (job_id + extensao);
}

void ResultadosEmDisco::gravar_resultado(const std::string& job_id, const Resultado& resultado,
                                         const Modelo& modelo) const {
    escrever_atomico(caminho(job_id, ".f64"), reinterpret_cast<const char*>(resultado.f.data()),
                     resultado.f.size() * sizeof(double));
    const std::string pgm = imagem_pgm(resultado.f, modelo.largura(), modelo.altura());
    escrever_atomico(caminho(job_id, ".pgm"), pgm.data(), pgm.size());
}

void ResultadosEmDisco::gravar_json(const Tarefa& tarefa) const {
    const std::string texto = corpo_json(tarefa).dump();
    escrever_atomico(caminho(tarefa.job_id, ".json"), texto.data(), texto.size());
}

std::string ResultadosEmDisco::ler(const std::string& job_id, const char* extensao) const {
    return ler_arquivo(caminho(job_id, extensao));
}
