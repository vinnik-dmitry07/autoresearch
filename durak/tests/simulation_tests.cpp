#include "eval.hpp"
#include "policy_core.hpp"
#include "strategies.hpp"
#include "test_util.hpp"

using namespace durak;

namespace {

double mean_point_rate(StrategyFn chal, StrategyFn opp, long long n, std::uint64_t base = 0) {
    double sum = 0.0;
    for (long long i = 0; i < n; ++i) sum += pair_score(base + std::uint64_t(i), chal, opp);
    return sum / double(n);
}

void test_random_selfplay_balanced() {
    const double pr = mean_point_rate(&b0_random, &b0_random, 4000);
    CHECK(pr > 0.45 && pr < 0.55);
}

void test_paired_symmetry() {
    // Swapping challenger/opponent must mirror the point rate around 0.5.
    const double a = mean_point_rate(&b1_basic, &b0_random, 3000);
    const double b = mean_point_rate(&b0_random, &b1_basic, 3000);
    CHECK(std::abs((a + b) - 1.0) < 1e-9);
}

void test_basic_beats_random() {
    const double pr = mean_point_rate(&b1_basic, &b0_random, 4000);
    CHECK(pr > 0.55);
}

void test_heuristic_selfplay_balanced() {
    const double pr = mean_point_rate(&b2_heuristic, &b2_heuristic, 3000);
    CHECK(pr > 0.45 && pr < 0.55);
}

void test_mem_selfplay_balanced() {
    const double pr = mean_point_rate(&b4_mem, &b4_mem, 3000);
    CHECK(pr > 0.45 && pr < 0.55);
}

void test_heuristic_beats_basic() {
    const double pr = mean_point_rate(&b2_heuristic, &b1_basic, 4000);
    CHECK(pr > 0.50);  // H1-H3 should add value over the basic baseline
}

void test_ablation_sane() {
    // B3 is the same core as B2 with memory enabled (tie-breaks only): near 0.5.
    const double pr = mean_point_rate(&b3_heuristic_mem, &b2_heuristic, 3000);
    CHECK(pr > 0.40 && pr < 0.60);
}

void test_manifest_present() {
    CHECK(heuristic_count() >= 1);
    CHECK(complexity_score() == 100 * heuristic_count() + 10 * parameter_count());
}

}  // namespace

int main() {
    test_random_selfplay_balanced();
    test_paired_symmetry();
    test_basic_beats_random();
    test_heuristic_selfplay_balanced();
    test_mem_selfplay_balanced();
    test_heuristic_beats_basic();
    test_ablation_sane();
    test_manifest_present();
    return durak_test::report("simulation_tests");
}
