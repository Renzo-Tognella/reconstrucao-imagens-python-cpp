// Monta o servidor HTTP, registra as rotas de http/rotas/ e liga na porta.
// O cabeçalho esconde o cpp-httplib, que é pesado para compilar.
#pragma once

#include "aplicacao/fila/fila.hpp"
#include "aplicacao/portas/modelos.hpp"

#include <cstddef>
#include <memory>
#include <string>

struct InfoServidor {
    std::size_t workers;
    int blas_threads;
    double aquecimento_s;
    std::string blas;
};

class ServidorHttp {
public:
    ServidorHttp(Fila& fila, const CatalogoModelos& catalogo, InfoServidor info);
    ~ServidorHttp();

    // Só em 127.0.0.1; lança std::runtime_error se a porta estiver ocupada.
    void ligar(int porta);
    // Bloqueia até parar().
    void escutar();
    // Fora de handler de sinal: pode alocar e esperar.
    void parar();

private:
    struct Implementacao;
    std::unique_ptr<Implementacao> impl_;
};
