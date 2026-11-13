#pragma once

#include <sys/resource.h>
#if defined(__APPLE__)
#include <mach/mach.h>
#include <sys/sysctl.h>
#else
#include <unistd.h>

#include <fstream>
#include <sstream>
#endif

#include <cstdint>
#include <cstdio>
#include <stdexcept>
#include <string>

namespace sistema {

inline std::uint64_t memoria_disponivel_bytes() {
#if defined(__APPLE__)
    static const host_t host = mach_host_self();
    vm_statistics64_data_t estatisticas{};
    mach_msg_type_number_t quantidade = HOST_VM_INFO64_COUNT;
    const kern_return_t retorno =
        host_statistics64(host, HOST_VM_INFO64, reinterpret_cast<host_info64_t>(&estatisticas), &quantidade);
    if (retorno != KERN_SUCCESS) {
        std::fprintf(stderr, "host_statistics64 falhou: %d\n", retorno);
        return 0;
    }
    const std::uint64_t paginas = static_cast<std::uint64_t>(estatisticas.free_count) + estatisticas.inactive_count +
                                  estatisticas.purgeable_count;
    return paginas * vm_kernel_page_size;
#else
    std::ifstream meminfo("/proc/meminfo");
    std::string linha;
    while (std::getline(meminfo, linha)) {
        if (linha.rfind("MemAvailable:", 0) == 0) {
            std::istringstream campos(linha.substr(13));
            std::uint64_t kib = 0;
            if (campos >> kib) {
                return kib * 1024;
            }
        }
    }
    std::fprintf(stderr, "MemAvailable não encontrado em /proc/meminfo\n");
    return 0;
#endif
}

inline std::uint64_t memoria_fisica_total_bytes() {
#if defined(__APPLE__)
    std::uint64_t bytes = 0;
    std::size_t tamanho = sizeof bytes;
    if (sysctlbyname("hw.memsize", &bytes, &tamanho, nullptr, 0) != 0) {
        throw std::runtime_error("sysctl hw.memsize falhou");
    }
    return bytes;
#else
    const long paginas = sysconf(_SC_PHYS_PAGES);
    const long tamanho = sysconf(_SC_PAGE_SIZE);
    if (paginas <= 0 || tamanho <= 0) {
        throw std::runtime_error("sysconf não informou a memória física");
    }
    return static_cast<std::uint64_t>(paginas) * static_cast<std::uint64_t>(tamanho);
#endif
}

struct UsoRecursos {
    double pico_rss_mb;
    double cpu_s;
};

inline UsoRecursos uso_recursos() {
    rusage uso{};
    getrusage(RUSAGE_SELF, &uso);
#if defined(__APPLE__)
    const double bytes_por_unidade = 1.0;
#else
    const double bytes_por_unidade = 1024.0;
#endif
    const auto segundos = [](const timeval& t) { return static_cast<double>(t.tv_sec) + static_cast<double>(t.tv_usec) / 1e6; };
    return {static_cast<double>(uso.ru_maxrss) * bytes_por_unidade / (1024.0 * 1024.0),
            segundos(uso.ru_utime) + segundos(uso.ru_stime)};
}

}
