#pragma once

#include <cstdio>
#include <cstdlib>

namespace durak_test {

inline int g_failures = 0;
inline int g_checks = 0;

inline void check(bool cond, const char* expr, const char* file, int line) {
    ++g_checks;
    if (!cond) {
        ++g_failures;
        std::printf("FAIL %s:%d  %s\n", file, line, expr);
    }
}

inline int report(const char* suite) {
    std::printf("[%s] %d checks, %d failures\n", suite, g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}

}  // namespace durak_test

#define CHECK(cond) ::durak_test::check((cond), #cond, __FILE__, __LINE__)
