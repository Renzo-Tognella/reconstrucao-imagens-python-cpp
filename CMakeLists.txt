cmake_minimum_required(VERSION 3.25)
project(reconstrucao_ultrassom LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# O SciPy dos wheels de macOS usa Accelerate: a comparação com Python precisa rodar
# com a mesma BLAS e também com a OpenBLAS. Cada backend fica em seu diretório de build.
set(BLAS_BACKEND openblas CACHE STRING "BLAS usada: openblas ou accelerate")
set_property(CACHE BLAS_BACKEND PROPERTY STRINGS openblas accelerate)

add_library(blas_escolhida INTERFACE)
if(BLAS_BACKEND STREQUAL "openblas")
  # Procura openblas_config.h, não cblas.h: no macOS o cblas.h do vecLib viria antes e não
  # declara openblas_set_num_threads.
  find_path(OPENBLAS_INCLUDE openblas_config.h
    HINTS /opt/homebrew/opt/openblas /usr/local/opt/openblas
    PATH_SUFFIXES include include/openblas include/x86_64-linux-gnu/openblas-pthread
    NO_CACHE REQUIRED)
  find_library(OPENBLAS_LIB openblas
    HINTS /opt/homebrew/opt/openblas /usr/local/opt/openblas
    PATH_SUFFIXES lib REQUIRED)
  target_include_directories(blas_escolhida SYSTEM INTERFACE ${OPENBLAS_INCLUDE})
  target_link_libraries(blas_escolhida INTERFACE ${OPENBLAS_LIB})
  target_compile_definitions(blas_escolhida INTERFACE BLAS_OPENBLAS)
elseif(BLAS_BACKEND STREQUAL "accelerate")
  if(NOT APPLE)
    message(FATAL_ERROR "BLAS_BACKEND=accelerate exige macOS")
  endif()
  target_link_libraries(blas_escolhida INTERFACE "-framework Accelerate")
  target_compile_definitions(blas_escolhida INTERFACE BLAS_ACCELERATE ACCELERATE_NEW_LAPACK)
else()
  message(FATAL_ERROR "BLAS_BACKEND inválido: ${BLAS_BACKEND} (use openblas ou accelerate)")
endif()

include(FetchContent)
set(JSON_BuildTests OFF CACHE INTERNAL "")
set(HTTPLIB_USE_OPENSSL_IF_AVAILABLE OFF CACHE INTERNAL "")
set(HTTPLIB_USE_ZLIB_IF_AVAILABLE OFF CACHE INTERNAL "")
set(HTTPLIB_USE_BROTLI_IF_AVAILABLE OFF CACHE INTERNAL "")
set(HTTPLIB_USE_ZSTD_IF_AVAILABLE OFF CACHE INTERNAL "")
set(HTTPLIB_INSTALL OFF CACHE INTERNAL "")
set(JSON_Install OFF CACHE INTERNAL "")
FetchContent_Declare(httplib
  URL https://github.com/yhirose/cpp-httplib/archive/refs/tags/v0.20.1.tar.gz
  URL_HASH SHA256=b74b1c2c150be2841eba80192f64d93e9a6711985b3ae8aaa1a9cec4863d1dd9
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
  SYSTEM)
FetchContent_Declare(json
  URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz
  URL_HASH SHA256=42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
  SYSTEM)
FetchContent_MakeAvailable(httplib json)

find_package(Threads REQUIRED)

add_library(opcoes_comuns INTERFACE)
target_compile_options(opcoes_comuns INTERFACE -O3 -Wall -Wextra)
target_include_directories(opcoes_comuns INTERFACE ${CMAKE_SOURCE_DIR}/servidor_cpp)
target_link_libraries(opcoes_comuns INTERFACE blas_escolhida Threads::Threads nlohmann_json::nlohmann_json)

# Uma biblioteca por camada, cada uma ligada só às camadas de dentro: domínio <- aplicação <- infraestrutura.
add_library(camada_dominio STATIC
  servidor_cpp/dominio/imagem.cpp
  servidor_cpp/dominio/algoritmos/cgne.cpp
  servidor_cpp/dominio/algoritmos/cgnr.cpp
  servidor_cpp/dominio/algoritmos/produtos.cpp
  servidor_cpp/dominio/algoritmos/reconstrucao.cpp
  servidor_cpp/dominio/algoritmos/resultado.cpp)
target_link_libraries(camada_dominio PUBLIC opcoes_comuns)

add_library(camada_aplicacao STATIC
  servidor_cpp/aplicacao/fila/controle_memoria.cpp
  servidor_cpp/aplicacao/fila/despachante.cpp
  servidor_cpp/aplicacao/fila/execucao.cpp
  servidor_cpp/aplicacao/fila/fila.cpp
  servidor_cpp/aplicacao/fila/tarefa.cpp
  servidor_cpp/aplicacao/metricas/contadores.cpp)
target_link_libraries(camada_aplicacao PUBLIC camada_dominio)

add_library(camada_infraestrutura STATIC
  servidor_cpp/infraestrutura/arquivos.cpp
  servidor_cpp/infraestrutura/eventos_jsonl.cpp
  servidor_cpp/infraestrutura/manifesto.cpp
  servidor_cpp/infraestrutura/matriz_mapeada.cpp
  servidor_cpp/infraestrutura/resultados_em_disco.cpp)
target_link_libraries(camada_infraestrutura PUBLIC camada_aplicacao)

add_executable(servidor_cpp
  servidor_cpp/main.cpp
  servidor_cpp/linha_de_comando.cpp
  servidor_cpp/http/erros.cpp
  servidor_cpp/http/servidor_http.cpp
  servidor_cpp/http/validacao_pedido.cpp
  servidor_cpp/http/rotas/baixar_resultado.cpp
  servidor_cpp/http/rotas/consultar_pedido.cpp
  servidor_cpp/http/rotas/enviar_sinal.cpp
  servidor_cpp/http/rotas/metricas.cpp)
target_link_libraries(servidor_cpp PRIVATE camada_infraestrutura httplib::httplib)
# Igual ao padrão do uvicorn. O 5 da biblioteca distorce rajadas e testes de saturação no macOS.
target_compile_definitions(servidor_cpp PRIVATE CPPHTTPLIB_LISTEN_BACKLOG=2048)

add_executable(prototipo_cpp servidor_cpp/etapas/prototipo.cpp)
target_link_libraries(prototipo_cpp PRIVATE camada_infraestrutura)

# Dados da etapa 2 do enunciado, extraídos no build.
set(DADOS_ZIP "${CMAKE_SOURCE_DIR}/dados-fornecidos/Dados.zip")
set(DADOS_ETAPA2 "${CMAKE_BINARY_DIR}/dados_etapa2")
if(NOT EXISTS "${DADOS_ZIP}")
  message(FATAL_ERROR "Dados.zip não encontrado: ${DADOS_ZIP}")
endif()
file(ARCHIVE_EXTRACT INPUT "${DADOS_ZIP}" DESTINATION "${DADOS_ETAPA2}")

add_executable(operacoes_check servidor_cpp/etapas/operacoes_check.cpp)
target_link_libraries(operacoes_check PRIVATE opcoes_comuns)
target_compile_definitions(operacoes_check PRIVATE DADOS_ETAPA2_PADRAO="${DADOS_ETAPA2}")

enable_testing()
add_executable(teste_algoritmos servidor_cpp/testes/teste_algoritmos.cpp)
target_link_libraries(teste_algoritmos PRIVATE camada_infraestrutura)
add_test(NAME teste_algoritmos COMMAND teste_algoritmos)
add_executable(teste_fila servidor_cpp/testes/teste_fila.cpp)
target_link_libraries(teste_fila PRIVATE camada_infraestrutura)
add_test(NAME teste_fila COMMAND teste_fila)
add_test(NAME operacoes_check COMMAND operacoes_check)
