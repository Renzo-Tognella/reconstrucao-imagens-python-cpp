#include "infraestrutura/log_terminal.hpp"

#include "aplicacao/fila/tarefa.hpp"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <optional>

namespace log_terminal {
namespace {

std::string segundos(const std::optional<double>& valor) {
    if (!valor.has_value()) {
        return "—";
    }
    char texto[32];
    std::snprintf(texto, sizeof texto, "%.3f s", *valor);
    std::string resultado(texto);
    std::replace(resultado.begin(), resultado.end(), '.', ',');
    return resultado;
}

std::string maiusculas(std::string texto) {
    std::transform(texto.begin(), texto.end(), texto.begin(),
                   [](unsigned char c) { return static_cast<char>(std::toupper(c)); });
    return texto;
}

std::string rotulo(const char* evento) {
    if (std::strcmp(evento, "accepted") == 0) return "recebido";
    if (std::strcmp(evento, "rejected") == 0) return "recusado";
    if (std::strcmp(evento, "started") == 0) return "iniciado";
    if (std::strcmp(evento, "finished") == 0) return "concluído";
    if (std::strcmp(evento, "failed") == 0) return "falhou";
    return evento;
}

std::string parada(const std::optional<std::string>& motivo) {
    if (!motivo.has_value()) return "?";
    if (*motivo == "tolerance") return "convergiu";
    if (*motivo == "max_iterations") return "limite";
    return *motivo;
}

std::string detalhe(const char* evento, const Tarefa* tarefa) {
    if (std::strcmp(evento, "rejected") == 0) {
        return "fila cheia, respondeu 503";
    }
    if (tarefa == nullptr) {
        return "";
    }
    if (std::strcmp(evento, "accepted") == 0) {
        return tarefa->client_id + "  " + tarefa->modelo + "  " + maiusculas(nome_do_algoritmo(tarefa->algoritmo)) +
               "  ganho " + (tarefa->gain ? "sim" : "não");
    }
    if (std::strcmp(evento, "started") == 0) {
        return "esperou " + segundos(tarefa->queue_wait_s) + " na fila";
    }
    if (std::strcmp(evento, "finished") == 0) {
        const auto& c = tarefa->conclusao;
        return "reconstruiu em " + segundos(c.duration_s) + ", " +
               (c.iterations ? std::to_string(*c.iterations) : std::string("?")) + " iterações (" +
               parada(c.stop_reason) + ")";
    }
    if (std::strcmp(evento, "failed") == 0) {
        return "erro: " + tarefa->conclusao.error.value_or("?");
    }
    return "";
}

std::string completar(const std::string& texto, std::size_t largura) {
    std::size_t caracteres = 0;
    for (const unsigned char c : texto) {
        caracteres += (c & 0xC0) != 0x80;
    }
    return caracteres >= largura ? texto : texto + std::string(largura - caracteres, ' ');
}

std::string hora_local() {
    const std::time_t agora = std::time(nullptr);
    std::tm local{};
    localtime_r(&agora, &local);
    char texto[16];
    std::strftime(texto, sizeof texto, "%H:%M:%S", &local);
    return texto;
}

}

std::string linha_evento(const char* evento, const std::string& job_id, const Tarefa* tarefa,
                         std::size_t fila, std::size_t rodando) {
    return hora_local() + "  " + completar(rotulo(evento), 9) + "  " + completar(job_id, 17) + "  " +
           completar(detalhe(evento, tarefa), 48) + "  fila " + std::to_string(fila) + ", rodando " +
           std::to_string(rodando);
}

std::string cabecalho() {
    return completar("hora", 8) + "  " + completar("evento", 9) + "  " + completar("pedido", 17) + "  " +
           completar("detalhe", 48) + "  estado do servidor";
}

void escrever(const std::string& linha) {
    std::fputs(linha.c_str(), stdout);
    std::fputc('\n', stdout);
    std::fflush(stdout);
}

}
