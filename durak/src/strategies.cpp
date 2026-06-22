#include "strategies.hpp"

#include <cstring>

namespace durak {

StrategyFn strategy_by_name(const char* name) {
    if (std::strcmp(name, "B0") == 0) return &b0_random;
    if (std::strcmp(name, "B1") == 0) return &b1_basic;
    if (std::strcmp(name, "B2") == 0) return &b2_heuristic;
    if (std::strcmp(name, "B3") == 0) return &b3_heuristic_mem;
    if (std::strcmp(name, "B4") == 0) return &b4_mem;
    return nullptr;
}

const char* strategy_label(StrategyFn fn) {
    if (fn == &b0_random) return "B0";
    if (fn == &b1_basic) return "B1";
    if (fn == &b2_heuristic) return "B2";
    if (fn == &b3_heuristic_mem) return "B3";
    if (fn == &b4_mem) return "B4";
    return "??";
}

}  // namespace durak
