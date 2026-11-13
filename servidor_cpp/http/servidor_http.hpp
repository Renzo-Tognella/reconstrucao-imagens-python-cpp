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

    void ligar(int porta);
    void escutar();
    void parar();

private:
    struct Implementacao;
    std::unique_ptr<Implementacao> impl_;
};
