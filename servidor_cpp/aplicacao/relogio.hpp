#pragma once

#include <chrono>
#include <cstdio>
#include <ctime>
#include <string>

namespace relogio {

inline double segundos_monotonicos() {
    const auto agora = std::chrono::steady_clock::now().time_since_epoch();
    return std::chrono::duration<double>(agora).count();
}

inline std::string agora_iso() {
    using namespace std::chrono;
    const auto agora = system_clock::now();
    const std::time_t segundos = system_clock::to_time_t(agora);
    const auto ms = duration_cast<milliseconds>(agora.time_since_epoch()).count() % 1000;
    std::tm utc{};
    gmtime_r(&segundos, &utc);
    char data[32];
    std::strftime(data, sizeof data, "%Y-%m-%dT%H:%M:%S", &utc);
    char texto[48];
    std::snprintf(texto, sizeof texto, "%s.%03dZ", data, static_cast<int>(ms));
    return texto;
}

}
