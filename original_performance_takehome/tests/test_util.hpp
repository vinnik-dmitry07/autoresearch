#pragma once

#include <cstdint>
#include <cstdio>
#include <exception>

namespace vliw_test {

inline int g_failures = 0;
inline int g_checks = 0;

inline void check(bool cond, const char* expr, const char* file, int line) {
    ++g_checks;
    if (!cond) {
        ++g_failures;
        std::printf("FAIL %s:%d  %s\n", file, line, expr);
    }
}

inline void check_eq(std::uint64_t got, std::uint64_t want, const char* got_expr,
                     const char* want_expr, const char* file, int line) {
    ++g_checks;
    if (got != want) {
        ++g_failures;
        std::printf("FAIL %s:%d  %s == %s  (got %llu, want %llu)\n", file, line, got_expr,
                    want_expr, static_cast<unsigned long long>(got),
                    static_cast<unsigned long long>(want));
    }
}

inline int report(const char* suite) {
    std::printf("[%s] %d checks, %d failures\n", suite, g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}

}  // namespace vliw_test

#define CHECK(cond) ::vliw_test::check(static_cast<bool>(cond), #cond, __FILE__, __LINE__)
#define CHECK_EQ(got, want) \
    ::vliw_test::check_eq(static_cast<std::uint64_t>(got), static_cast<std::uint64_t>(want), #got, \
                          #want, __FILE__, __LINE__)
#define CHECK_THROWS(stmt)                                                         \
    do {                                                                           \
        bool threw = false;                                                        \
        try {                                                                      \
            stmt;                                                                  \
        } catch (const std::exception&) {                                          \
            threw = true;                                                          \
        }                                                                          \
        ::vliw_test::check(threw, "expected throw: " #stmt, __FILE__, __LINE__); \
    } while (0)
