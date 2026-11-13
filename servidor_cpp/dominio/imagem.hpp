// Converte o vetor f reconstruído na imagem PGM entregue ao cliente.
#pragma once

#include <cstddef>
#include <string>
#include <vector>

// f está por colunas (f[col*altura + lin]); o PGM vai por linhas, de cima para baixo.
std::string imagem_pgm(const std::vector<double>& f, std::size_t largura, std::size_t altura);
