#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "eval.hpp"
#include "policy_core.hpp"
#include "strategies.hpp"

using namespace durak;

namespace {

enum class CiMode { Normal, Bootstrap };

struct EvalOut {
    double point_rate = 0.0;
    double lo = 0.0;
    double hi = 0.0;
    double win = 0.0;   // P(pair_score > 0.5)
    double loss = 0.0;  // P(pair_score < 0.5)
    double split = 0.0;
    long long seeds = 0;
    double seconds = 0.0;
};

double now_seconds(std::chrono::steady_clock::time_point t0) {
    using namespace std::chrono;
    return duration_cast<duration<double>>(steady_clock::now() - t0).count();
}

EvalOut run_eval(StrategyFn chal, StrategyFn opp, std::uint64_t seed_base, long long n,
                 long long batch, const char* label, CiMode ci, int resamples) {
    double sum = 0.0, sumsq = 0.0;
    long long win = 0, loss = 0, split = 0;
    std::vector<float> scores;
    if (ci == CiMode::Bootstrap) scores.reserve(std::size_t(n));

    const auto t0 = std::chrono::steady_clock::now();
    for (long long i = 0; i < n; ++i) {
        const double pr = pair_score(seed_base + std::uint64_t(i), chal, opp);
        sum += pr;
        sumsq += pr * pr;
        if (pr > 0.5) ++win;
        else if (pr < 0.5) ++loss;
        else ++split;
        if (ci == CiMode::Bootstrap) scores.push_back(float(pr));

        if (batch > 0 && (i + 1) % batch == 0) {
            const double secs = now_seconds(t0);
            const long long done = i + 1;
            const double games = double(done) * 2.0;
            std::printf("  [%s] seeds=%lld games=%.0f point_rate=%.5f games/s=%.0f\n", label, done,
                        games, sum / double(done), secs > 0 ? games / secs : 0.0);
            std::fflush(stdout);
        }
    }

    EvalOut out;
    out.seeds = n;
    out.seconds = now_seconds(t0);
    out.point_rate = (n > 0) ? sum / double(n) : 0.0;
    out.win = (n > 0) ? double(win) / double(n) : 0.0;
    out.loss = (n > 0) ? double(loss) / double(n) : 0.0;
    out.split = (n > 0) ? double(split) / double(n) : 0.0;

    if (ci == CiMode::Normal) {
        if (n > 1) {
            const double mean = out.point_rate;
            const double var = (sumsq - sum * sum / double(n)) / double(n - 1);
            const double se = std::sqrt(std::max(0.0, var) / double(n));
            out.lo = mean - 1.96 * se;
            out.hi = mean + 1.96 * se;
        } else {
            out.lo = out.hi = out.point_rate;
        }
    } else {
        Rng rng(0xC0FFEEu + std::uint64_t(n));
        std::vector<double> means;
        means.reserve(std::size_t(resamples));
        for (int r = 0; r < resamples; ++r) {
            double s = 0.0;
            for (long long k = 0; k < n; ++k) s += scores[rng.bounded(std::uint32_t(n))];
            means.push_back(s / double(n));
        }
        std::sort(means.begin(), means.end());
        out.lo = means[std::size_t(0.025 * resamples)];
        out.hi = means[std::size_t(std::min<double>(resamples - 1, 0.975 * resamples))];
    }
    return out;
}

void print_eval(const char* title, const EvalOut& e) {
    std::printf("%-18s point_rate=%.5f  ci95=[%.5f, %.5f]  win=%.4f loss=%.4f split=%.4f  (%lld seeds, %.1fs)\n",
                title, e.point_rate, e.lo, e.hi, e.win, e.loss, e.split, e.seeds, e.seconds);
    std::fflush(stdout);
}

const char* arg_value(int argc, char** argv, const char* key, const char* def) {
    for (int i = 1; i < argc - 1; ++i)
        if (std::strcmp(argv[i], key) == 0) return argv[i + 1];
    return def;
}

void print_manifest() {
    std::printf("strategy=%s  heuristics=%d  parameters=%d  complexity=%d\n", strategy_name(),
                heuristic_count(), parameter_count(), complexity_score());
}

}  // namespace

int main(int argc, char** argv) {
    const std::string mode = arg_value(argc, argv, "--mode", "ladder");
    const std::string eval = arg_value(argc, argv, "--eval", "full");
    const std::uint64_t seed_base = std::strtoull(arg_value(argc, argv, "--seed-base", "0"), nullptr, 10);
    const std::string ci_s = arg_value(argc, argv, "--ci", "normal");
    const int resamples = std::atoi(arg_value(argc, argv, "--bootstrap-resamples", "1000"));
    const CiMode ci = (ci_s == "bootstrap") ? CiMode::Bootstrap : CiMode::Normal;

    long long seeds = (eval == "quick") ? 100000 : 5000000;
    if (const char* s = arg_value(argc, argv, "--seeds", nullptr)) seeds = std::atoll(s);
    long long batch = std::atoll(arg_value(argc, argv, "--batch", "5000"));

    std::printf("=== Durak simulate ===\nmode=%s eval=%s seeds=%lld ci=%s seed_base=%llu\n",
                mode.c_str(), eval.c_str(), seeds, ci_s.c_str(), (unsigned long long)seed_base);
    print_manifest();

    if (mode == "ladder") {
        StrategyFn chal = strategy_by_name(arg_value(argc, argv, "--challenger", "B2"));
        EvalOut e4 = run_eval(chal, &b4_mem, seed_base, seeds, batch, "vs B4", ci, resamples);
        EvalOut e1 = run_eval(chal, &b1_basic, seed_base, seeds, batch, "vs B1", ci, resamples);
        EvalOut e0 = run_eval(chal, &b0_random, seed_base, seeds, batch, "vs B0", ci, resamples);
        std::printf("\n--- ladder results ---\n");
        print_eval("B2 vs B4", e4);
        print_eval("B2 vs B1", e1);
        print_eval("B2 vs B0", e0);
        const double penalty = double(complexity_score()) / 10000.0;
        const double search = 0.50 * e4.point_rate + 0.30 * e1.point_rate + 0.20 * e0.point_rate - penalty;
        std::printf("search_score=%.5f  (0.5*B4 + 0.3*B1 + 0.2*B0 - complexity/10000)\n", search);
        std::printf("reporting_point_rate_vs_B4=%.5f  lower_ci=%.5f  complexity=%d\n",
                    e4.point_rate, e4.lo, complexity_score());
    } else if (mode == "match") {
        StrategyFn chal = strategy_by_name(arg_value(argc, argv, "--challenger", "B2"));
        StrategyFn opp = strategy_by_name(arg_value(argc, argv, "--opponent", "B4"));
        if (!chal || !opp) { std::printf("unknown strategy\n"); return 1; }
        EvalOut e = run_eval(chal, opp, seed_base, seeds, batch, "match", ci, resamples);
        std::printf("\n--- match results ---\n");
        std::string title = std::string(strategy_label(chal)) + " vs " + strategy_label(opp);
        print_eval(title.c_str(), e);
    } else if (mode == "ablate") {
        // B3 (same core + memory) vs B2 (same core, no memory).
        EvalOut e = run_eval(&b3_heuristic_mem, &b2_heuristic, seed_base, seeds, batch, "B3 vs B2", ci, resamples);
        std::printf("\n--- memory ablation (B3 vs B2) ---\n");
        print_eval("B3 vs B2", e);
        std::printf("memory_value_point_rate=%.5f  lower_ci=%.5f  (0.5 means memory adds nothing)\n",
                    e.point_rate, e.lo);
    } else if (mode == "selfplay") {
        StrategyFn s = strategy_by_name(arg_value(argc, argv, "--strategy", "B2"));
        if (!s) { std::printf("unknown strategy\n"); return 1; }
        EvalOut e = run_eval(s, s, seed_base, seeds, batch, "selfplay", ci, resamples);
        std::printf("\n--- selfplay (expect ~0.5) ---\n");
        print_eval(strategy_label(s), e);
    } else {
        std::printf("unknown mode: %s\n", mode.c_str());
        return 1;
    }
    return 0;
}
