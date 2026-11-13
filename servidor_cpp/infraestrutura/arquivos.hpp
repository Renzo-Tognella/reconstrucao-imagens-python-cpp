#pragma once

#include <cstddef>
#include <filesystem>
#include <string>
#include <vector>

void escrever_atomico(const std::filesystem::path& destino, const char* dados, std::size_t tamanho);
std::string ler_arquivo(const std::filesystem::path& caminho);
std::vector<double> ler_vetor_f64(const std::filesystem::path& caminho, std::size_t elementos);
