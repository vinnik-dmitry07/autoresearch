#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
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

void print_manifest(std::FILE* out) {
    std::fprintf(out, "strategy=%s  heuristics=%d  parameters=%d  complexity=%d\n", strategy_name(),
                 heuristic_count(), parameter_count(), complexity_score());
}

const char* result_label(GameResult result) {
    if (result == GameResult::Draw) return "draw";
    return (result == GameResult::Player0Win) ? "player0_win" : "player1_win";
}

const char* pair_bucket(double pair_score) {
    if (pair_score > 0.5) return "win";
    if (pair_score < 0.5) return "loss";
    return "split";
}

int trace_for(const int values[2], int seat) {
    return values[seat];
}

int trace_opp(const int values[2], int seat) {
    return values[1 - seat];
}

CardMask trace_mask_for(const CardMask values[2], int seat) {
    return values[seat];
}

CardMask trace_mask_opp(const CardMask values[2], int seat) {
    return values[1 - seat];
}

int trace_phase_for(const int values[2][3], int seat, int phase) {
    return values[seat][phase];
}

int trace_phase_opp(const int values[2][3], int seat, int phase) {
    return values[1 - seat][phase];
}

std::FILE* open_output_file(const char* path) {
#ifdef _MSC_VER
    std::FILE* out = nullptr;
    if (fopen_s(&out, path, "wb") != 0) return nullptr;
    return out;
#else
    return std::fopen(path, "wb");
#endif
}

void print_features_header(std::FILE* out) {
    std::fprintf(
        out,
        "seed\tgame_in_pair\tdeck_seed\trng_seed\tchallenger\topponent\tchallenger_seat\t"
        "result\tchallenger_points\tpair_score\tpair_bucket\tinitial_attacker\t"
        "challenger_attacked_first\ttrump_rank\ttrump_suit\tchal_initial_trumps\t"
        "opp_initial_trumps\tchal_initial_high_trumps\topp_initial_high_trumps\t"
        "chal_initial_non_trumps\topp_initial_non_trumps\tchal_initial_pairs\t"
        "opp_initial_pairs\tchal_initial_min_non_trump_rank\topp_initial_min_non_trump_rank\t"
        "chal_initial_min_trump_rank\topp_initial_min_trump_rank\tbattles\t"
        "deck_empty_after_battle\tchal_attacks_started\topp_attacks_started\t"
        "chal_successful_defenses\topp_successful_defenses\tchal_takes\topp_takes\t"
        "chal_forced_takes\topp_forced_takes\tchal_voluntary_takes\topp_voluntary_takes\t"
        "chal_forced_takes_deck_ge5\topp_forced_takes_deck_ge5\t"
        "chal_forced_takes_deck_1_4\topp_forced_takes_deck_1_4\t"
        "chal_forced_takes_deck_0\topp_forced_takes_deck_0\t"
        "chal_voluntary_takes_deck_ge5\topp_voluntary_takes_deck_ge5\t"
        "chal_voluntary_takes_deck_1_4\topp_voluntary_takes_deck_1_4\t"
        "chal_voluntary_takes_deck_0\topp_voluntary_takes_deck_0\t"
        "chal_vol_take_min_cover_trump\topp_vol_take_min_cover_trump\t"
        "chal_vol_take_high_trump_deck_ge5\topp_vol_take_high_trump_deck_ge5\t"
        "chal_cards_taken\topp_cards_taken\tchal_attack_cards\topp_attack_cards\t"
        "chal_defense_cards\topp_defense_cards\tchal_trump_attack_cards\t"
        "opp_trump_attack_cards\tchal_trump_defense_cards\topp_trump_defense_cards\t"
        "chal_cards_taken_deck_ge5\topp_cards_taken_deck_ge5\t"
        "chal_cards_taken_deck_1_4\topp_cards_taken_deck_1_4\t"
        "chal_cards_taken_deck_0\topp_cards_taken_deck_0\t"
        "chal_trump_attack_cards_deck_ge5\topp_trump_attack_cards_deck_ge5\t"
        "chal_trump_attack_cards_deck_1_4\topp_trump_attack_cards_deck_1_4\t"
        "chal_trump_attack_cards_deck_0\topp_trump_attack_cards_deck_0\t"
        "chal_successful_defenses_deck_ge5\topp_successful_defenses_deck_ge5\t"
        "chal_successful_defenses_deck_1_4\topp_successful_defenses_deck_1_4\t"
        "chal_successful_defenses_deck_0\topp_successful_defenses_deck_0\t"
        "chal_first_deck0_forced_take\topp_first_deck0_forced_take\t"
        "chal_first_deck0_forced_take_battle\topp_first_deck0_forced_take_battle\t"
        "chal_first_deck0_forced_take_attacker\topp_first_deck0_forced_take_attacker\t"
        "chal_first_deck0_forced_take_table_cards\topp_first_deck0_forced_take_table_cards\t"
        "chal_first_deck0_forced_take_uncovered\topp_first_deck0_forced_take_uncovered\t"
        "chal_first_deck0_forced_take_attack_cards\topp_first_deck0_forced_take_attack_cards\t"
        "chal_first_deck0_forced_take_defense_cards\topp_first_deck0_forced_take_defense_cards\t"
        "chal_first_deck0_forced_take_trump_attacks\topp_first_deck0_forced_take_trump_attacks\t"
        "chal_first_deck0_forced_take_trump_defenses\topp_first_deck0_forced_take_trump_defenses\t"
        "chal_first_deck0_forced_take_min_attack_rank\topp_first_deck0_forced_take_min_attack_rank\t"
        "chal_first_deck0_forced_take_max_attack_rank\topp_first_deck0_forced_take_max_attack_rank\t"
        "chal_first_deck0_forced_take_defender_hand_count\t"
        "opp_first_deck0_forced_take_defender_hand_count\t"
        "chal_first_deck0_forced_take_attacker_hand_count\t"
        "opp_first_deck0_forced_take_attacker_hand_count\t"
        "chal_first_deck0_forced_take_defender_trumps\t"
        "opp_first_deck0_forced_take_defender_trumps\t"
        "chal_first_deck0_forced_take_attacker_trumps\t"
        "opp_first_deck0_forced_take_attacker_trumps\t"
        "chal_first_deck0_forced_take_defender_high_trumps\t"
        "opp_first_deck0_forced_take_defender_high_trumps\t"
        "chal_first_deck0_forced_take_attacker_high_trumps\t"
        "opp_first_deck0_forced_take_attacker_high_trumps\t"
        "chal_first_deck0_forced_take_attacker_nontrump_throwins\t"
        "opp_first_deck0_forced_take_attacker_nontrump_throwins\t"
        "chal_first_deck0_forced_take_attacker_trump_throwins\t"
        "opp_first_deck0_forced_take_attacker_trump_throwins\t"
        "chal_first_deck0_forced_take_attack_mask\topp_first_deck0_forced_take_attack_mask\t"
        "chal_first_deck0_forced_take_defense_mask\topp_first_deck0_forced_take_defense_mask\t"
        "chal_first_deck0_forced_take_defender_hand_mask\t"
        "opp_first_deck0_forced_take_defender_hand_mask\t"
        "chal_first_deck0_forced_take_legal_defense_mask\t"
        "opp_first_deck0_forced_take_legal_defense_mask\t"
        "chal_first_deck0_forced_take_legal_defense_cards\t"
        "opp_first_deck0_forced_take_legal_defense_cards\t"
        "chal_first_deck0_forced_take_legal_trump_defenses\t"
        "opp_first_deck0_forced_take_legal_trump_defenses\t"
        "chal_first_deck0_forced_take_legal_nontrump_defenses\t"
        "opp_first_deck0_forced_take_legal_nontrump_defenses\t"
        "chal_first_deck0_forced_take_coverable_uncovered\t"
        "opp_first_deck0_forced_take_coverable_uncovered\t"
        "chal_first_deck0_forced_take_uncoverable_uncovered\t"
        "opp_first_deck0_forced_take_uncoverable_uncovered\t"
        "chal_first_deck0_forced_take_cheapest_cover_rank\t"
        "opp_first_deck0_forced_take_cheapest_cover_rank\t"
        "chal_first_deck0_forced_take_cheapest_cover_is_trump\t"
        "opp_first_deck0_forced_take_cheapest_cover_is_trump\t"
        "chal_first_deck0_forced_take_opp_later_trump_attack\t"
        "opp_first_deck0_forced_take_opp_later_trump_attack\t"
        "chal_first_deck0_forced_take_self_later_trump_attack\t"
        "opp_first_deck0_forced_take_self_later_trump_attack\t"
        "chal_first_deck0_forced_take_prior_attack_seen\t"
        "opp_first_deck0_forced_take_prior_attack_seen\t"
        "chal_first_deck0_forced_take_prior_attack_battle\t"
        "opp_first_deck0_forced_take_prior_attack_battle\t"
        "chal_first_deck0_forced_take_prior_attack_chosen_is_trump\t"
        "opp_first_deck0_forced_take_prior_attack_chosen_is_trump\t"
        "chal_first_deck0_forced_take_prior_attack_chosen_rank\t"
        "opp_first_deck0_forced_take_prior_attack_chosen_rank\t"
        "chal_first_deck0_forced_take_prior_attack_chosen_suit\t"
        "opp_first_deck0_forced_take_prior_attack_chosen_suit\t"
        "chal_first_deck0_forced_take_prior_attack_legal_nontrumps\t"
        "opp_first_deck0_forced_take_prior_attack_legal_nontrumps\t"
        "chal_first_deck0_forced_take_prior_attack_legal_trumps\t"
        "opp_first_deck0_forced_take_prior_attack_legal_trumps\t"
        "chal_first_deck0_forced_take_prior_attack_legal_attack_mask\t"
        "opp_first_deck0_forced_take_prior_attack_legal_attack_mask\t"
        "chal_first_deck0_forced_take_prior_attack_legal_trump_attack_mask\t"
        "opp_first_deck0_forced_take_prior_attack_legal_trump_attack_mask\t"
        "chal_first_deck0_forced_take_prior_attack_legal_nontrump_attack_mask\t"
        "opp_first_deck0_forced_take_prior_attack_legal_nontrump_attack_mask\t"
        "chal_first_deck0_forced_take_prior_attack_legal_force_take_attack_mask\t"
        "opp_first_deck0_forced_take_prior_attack_legal_force_take_attack_mask\t"
        "chal_first_deck0_forced_take_prior_attack_legal_force_high_trump_cover_attack_mask\t"
        "opp_first_deck0_forced_take_prior_attack_legal_force_high_trump_cover_attack_mask\t"
        "chal_first_deck0_forced_take_prior_attack_chosen_forces_take\t"
        "opp_first_deck0_forced_take_prior_attack_chosen_forces_take\t"
        "chal_first_deck0_forced_take_prior_attack_chosen_forces_high_trump_cover\t"
        "opp_first_deck0_forced_take_prior_attack_chosen_forces_high_trump_cover\t"
        "chal_first_deck0_forced_take_prior_attack_attacker_hand_count\t"
        "opp_first_deck0_forced_take_prior_attack_attacker_hand_count\t"
        "chal_first_deck0_forced_take_prior_attack_defender_hand_count\t"
        "opp_first_deck0_forced_take_prior_attack_defender_hand_count\t"
        "chal_first_deck0_forced_take_prior_attack_attacker_trumps\t"
        "opp_first_deck0_forced_take_prior_attack_attacker_trumps\t"
        "chal_first_deck0_forced_take_prior_attack_defender_trumps\t"
        "opp_first_deck0_forced_take_prior_attack_defender_trumps\t"
        "chal_first_deck0_forced_take_prior_attack_defender_high_trumps\t"
        "opp_first_deck0_forced_take_prior_attack_defender_high_trumps\t"
        "chal_first_deck0_forced_take_prior_attack_covered\t"
        "opp_first_deck0_forced_take_prior_attack_covered\t"
        "chal_first_deck0_forced_take_prior_attack_cover_is_trump\t"
        "opp_first_deck0_forced_take_prior_attack_cover_is_trump\t"
        "chal_first_deck0_forced_take_prior_attack_cover_same_rank\t"
        "opp_first_deck0_forced_take_prior_attack_cover_same_rank\t"
        "chal_first_deck0_forced_take_prior_attack_cover_rank\t"
        "opp_first_deck0_forced_take_prior_attack_cover_rank\t"
        "chal_first_deck0_forced_take_prior_attack_defender_trumps_after_cover\t"
        "opp_first_deck0_forced_take_prior_attack_defender_trumps_after_cover\t"
        "chal_first_deck0_forced_take_prior_attack_defender_high_trumps_after_cover\t"
        "opp_first_deck0_forced_take_prior_attack_defender_high_trumps_after_cover\t"
        "chal_first_deck0_forced_take_prior_attack_battles_until_forced_take\t"
        "opp_first_deck0_forced_take_prior_attack_battles_until_forced_take\t"
        "chal_first_deck0_forced_take_prior_attack_self_attack_cards_after_cover\t"
        "opp_first_deck0_forced_take_prior_attack_self_attack_cards_after_cover\t"
        "chal_first_deck0_forced_take_prior_attack_self_legal_trump_options_after_cover\t"
        "opp_first_deck0_forced_take_prior_attack_self_legal_trump_options_after_cover\t"
        "chal_first_deck0_forced_take_prior_attack_self_trump_attacks_after_cover\t"
        "opp_first_deck0_forced_take_prior_attack_self_trump_attacks_after_cover\t"
        "chal_first_deck0_forced_take_prior_attack_opp_attack_cards_after_cover\t"
        "opp_first_deck0_forced_take_prior_attack_opp_attack_cards_after_cover\t"
        "chal_first_deck0_forced_take_prior_attack_opp_trump_attacks_after_cover\t"
        "opp_first_deck0_forced_take_prior_attack_opp_trump_attacks_after_cover\t"
        "chal_first_deck0_forced_take_prior_attack_opp_high_trump_attacks_after_cover\t"
        "opp_first_deck0_forced_take_prior_attack_opp_high_trump_attacks_after_cover\t"
        "chal_deck0_attack_decisions\topp_deck0_attack_decisions\t"
        "chal_deck0_attack_passes_with_trump\topp_deck0_attack_passes_with_trump\t"
        "chal_deck0_attack_nontrump_with_trump\topp_deck0_attack_nontrump_with_trump\t"
        "chal_deck0_attack_trump_with_trump\topp_deck0_attack_trump_with_trump\t"
        "chal_deck0_legal_trump_attack_options\topp_deck0_legal_trump_attack_options\t"
        "chal_deck0_legal_high_trump_attack_options\t"
        "opp_deck0_legal_high_trump_attack_options\t"
        "chal_deck0_high_trump_attacks\topp_deck0_high_trump_attacks\t"
        "chal_deck0_last_two_attack_count\topp_deck0_last_two_attack_count\t"
        "chal_deck0_last_two_passes_with_trump\topp_deck0_last_two_passes_with_trump\t"
        "chal_deck0_last_two_nontrump_with_trump\topp_deck0_last_two_nontrump_with_trump\t"
        "chal_deck0_last_two_trump_with_trump\topp_deck0_last_two_trump_with_trump\t"
        "chal_deck0_last_decision_seen\topp_deck0_last_decision_seen\t"
        "chal_deck0_last_decision_battle\topp_deck0_last_decision_battle\t"
        "chal_deck0_last_decision_code\topp_deck0_last_decision_code\t"
        "chal_deck0_last_decision_attack_done_available\t"
        "opp_deck0_last_decision_attack_done_available\t"
        "chal_deck0_last_decision_opponent_hand_count\t"
        "opp_deck0_last_decision_opponent_hand_count\t"
        "chal_deck0_last_decision_chosen_rank\topp_deck0_last_decision_chosen_rank\t"
        "chal_deck0_last_decision_chosen_suit\topp_deck0_last_decision_chosen_suit\t"
        "chal_deck0_last_decision_chosen_is_trump\t"
        "opp_deck0_last_decision_chosen_is_trump\t"
        "chal_deck0_last_decision_hand_mask\topp_deck0_last_decision_hand_mask\t"
        "chal_deck0_last_decision_legal_attack_mask\t"
        "opp_deck0_last_decision_legal_attack_mask\t"
        "chal_deck0_last_decision_legal_trump_attack_mask\t"
        "opp_deck0_last_decision_legal_trump_attack_mask\t"
        "chal_deck0_last_decision_legal_high_trump_attack_mask\t"
        "opp_deck0_last_decision_legal_high_trump_attack_mask\t"
        "chal_deck0_last_decision_legal_nontrump_attack_mask\t"
        "opp_deck0_last_decision_legal_nontrump_attack_mask\t"
        "chal_deck0_tiny_high_trump_opportunities\t"
        "opp_deck0_tiny_high_trump_opportunities\t"
        "chal_deck0_tiny_high_trump_chosen_high\t"
        "opp_deck0_tiny_high_trump_chosen_high\t"
        "chal_deck0_tiny_high_trump_chosen_other\t"
        "opp_deck0_tiny_high_trump_chosen_other\t"
        "chal_deck0_tiny_high_trump_legal_nontrump_options\t"
        "opp_deck0_tiny_high_trump_legal_nontrump_options\t"
        "chal_deck0_tiny_high_trump_last_seen\t"
        "opp_deck0_tiny_high_trump_last_seen\t"
        "chal_deck0_tiny_high_trump_last_hand_count\t"
        "opp_deck0_tiny_high_trump_last_hand_count\t"
        "chal_deck0_tiny_high_trump_last_opponent_hand_count\t"
        "opp_deck0_tiny_high_trump_last_opponent_hand_count\t"
        "chal_deck0_tiny_high_trump_last_chosen_rank\t"
        "opp_deck0_tiny_high_trump_last_chosen_rank\t"
        "chal_deck0_tiny_high_trump_last_chosen_suit\t"
        "opp_deck0_tiny_high_trump_last_chosen_suit\t"
        "chal_deck0_tiny_high_trump_last_chosen_is_trump\t"
        "opp_deck0_tiny_high_trump_last_chosen_is_trump\t"
        "chal_deck0_tiny_high_trump_last_hand_mask\t"
        "opp_deck0_tiny_high_trump_last_hand_mask\t"
        "chal_deck0_tiny_high_trump_last_legal_attack_mask\t"
        "opp_deck0_tiny_high_trump_last_legal_attack_mask\t"
        "chal_deck0_tiny_high_trump_last_legal_high_trump_attack_mask\t"
        "opp_deck0_tiny_high_trump_last_legal_high_trump_attack_mask\t"
        "chal_deck0_tiny_high_trump_last_legal_nontrump_attack_mask\t"
        "opp_deck0_tiny_high_trump_last_legal_nontrump_attack_mask\t"
        "chal_deck0_attack_play_count\topp_deck0_attack_play_count\t"
        "chal_deck0_self_played_rank_mask\topp_deck0_self_played_rank_mask\t"
        "chal_deck0_opp_played_rank_mask\topp_deck0_opp_played_rank_mask\t"
        "chal_deck0_last_two_play_count\topp_deck0_last_two_play_count\t"
        "chal_deck0_last_play_rank\topp_deck0_last_play_rank\t"
        "chal_deck0_last_play_suit\topp_deck0_last_play_suit\t"
        "chal_deck0_last_play_is_trump\topp_deck0_last_play_is_trump\t"
        "chal_deck0_last_play_opponent_hand_count\t"
        "opp_deck0_last_play_opponent_hand_count\t"
        "chal_deck0_last_play_attack_done_available\t"
        "opp_deck0_last_play_attack_done_available\t"
        "chal_deck0_prev_play_rank\topp_deck0_prev_play_rank\t"
        "chal_deck0_prev_play_suit\topp_deck0_prev_play_suit\t"
        "chal_deck0_prev_play_is_trump\topp_deck0_prev_play_is_trump\t"
        "chal_deck0_prev_play_opponent_hand_count\t"
        "opp_deck0_prev_play_opponent_hand_count\t"
        "chal_deck0_prev_play_attack_done_available\t"
        "opp_deck0_prev_play_attack_done_available\t"
        "chal_deck0_last_play_hand_mask\topp_deck0_last_play_hand_mask\t"
        "chal_deck0_last_play_legal_attack_mask\t"
        "opp_deck0_last_play_legal_attack_mask\t"
        "chal_deck0_last_play_legal_trump_attack_mask\t"
        "opp_deck0_last_play_legal_trump_attack_mask\t"
        "chal_deck0_last_play_legal_high_trump_attack_mask\t"
        "opp_deck0_last_play_legal_high_trump_attack_mask\t"
        "chal_deck0_last_play_legal_nontrump_attack_mask\t"
        "opp_deck0_last_play_legal_nontrump_attack_mask\t"
        "chal_deck0_prev_play_hand_mask\topp_deck0_prev_play_hand_mask\t"
        "chal_deck0_prev_play_legal_attack_mask\t"
        "opp_deck0_prev_play_legal_attack_mask\t"
        "chal_deck0_prev_play_legal_trump_attack_mask\t"
        "opp_deck0_prev_play_legal_trump_attack_mask\t"
        "chal_deck0_prev_play_legal_high_trump_attack_mask\t"
        "opp_deck0_prev_play_legal_high_trump_attack_mask\t"
        "chal_deck0_prev_play_legal_nontrump_attack_mask\t"
        "opp_deck0_prev_play_legal_nontrump_attack_mask\t"
        "chal_draws\topp_draws\tmax_table_cards\tmax_cards_taken\ttable_cards_total\t"
        "discarded_cards\tfinal_deck_count\tchal_final_hand_count\topp_final_hand_count\t"
        "chal_final_trumps\topp_final_trumps\tchal_final_high_trumps\topp_final_high_trumps\t"
        "chal_final_non_trumps\topp_final_non_trumps\t"
        "chal_final_min_trump_rank\topp_final_min_trump_rank\t"
        "chal_final_min_non_trump_rank\topp_final_min_non_trump_rank\t"
        "chal_final_max_trump_rank\topp_final_max_trump_rank\t"
        "chal_final_max_non_trump_rank\topp_final_max_non_trump_rank\t"
        "chal_final_hand_mask\topp_final_hand_mask\t"
        "final_attacker\n");
}

void print_game_features(std::FILE* out, std::uint64_t seed, int game_in_pair,
                         std::uint64_t deck_seed, std::uint64_t rng_seed,
                         const char* challenger_name, const char* opponent_name, int challenger_seat,
                         GameResult result, double challenger_points, double paired_score,
                         const GameTrace& trace) {
    const int c = challenger_seat;
    std::fprintf(out, "%llu", (unsigned long long)seed);
    std::fprintf(out, "\t%d", game_in_pair);
    std::fprintf(out, "\t%llu", (unsigned long long)deck_seed);
    std::fprintf(out, "\t%llu", (unsigned long long)rng_seed);
    std::fprintf(out, "\t%s", challenger_name);
    std::fprintf(out, "\t%s", opponent_name);
    std::fprintf(out, "\t%d", challenger_seat);
    std::fprintf(out, "\t%s", result_label(result));
    std::fprintf(out, "\t%.1f", challenger_points);
    std::fprintf(out, "\t%.2f", paired_score);
    std::fprintf(out, "\t%s", pair_bucket(paired_score));
    std::fprintf(out, "\t%d", trace.initial_attacker);
    std::fprintf(out, "\t%d", trace.initial_attacker == c ? 1 : 0);
    std::fprintf(out, "\t%d", trace.trump_rank);
    std::fprintf(out, "\t%d", trace.trump_suit);
    std::fprintf(out, "\t%d", trace_for(trace.initial_trumps, c));
    std::fprintf(out, "\t%d", trace_opp(trace.initial_trumps, c));
    std::fprintf(out, "\t%d", trace_for(trace.initial_high_trumps, c));
    std::fprintf(out, "\t%d", trace_opp(trace.initial_high_trumps, c));
    std::fprintf(out, "\t%d", trace_for(trace.initial_non_trumps, c));
    std::fprintf(out, "\t%d", trace_opp(trace.initial_non_trumps, c));
    std::fprintf(out, "\t%d", trace_for(trace.initial_pairs, c));
    std::fprintf(out, "\t%d", trace_opp(trace.initial_pairs, c));
    std::fprintf(out, "\t%d", trace_for(trace.initial_min_non_trump_rank, c));
    std::fprintf(out, "\t%d", trace_opp(trace.initial_min_non_trump_rank, c));
    std::fprintf(out, "\t%d", trace_for(trace.initial_min_trump_rank, c));
    std::fprintf(out, "\t%d", trace_opp(trace.initial_min_trump_rank, c));
    std::fprintf(out, "\t%d", trace.battles);
    std::fprintf(out, "\t%d", trace.deck_empty_after_battle);
    std::fprintf(out, "\t%d", trace_for(trace.attacks_started, c));
    std::fprintf(out, "\t%d", trace_opp(trace.attacks_started, c));
    std::fprintf(out, "\t%d", trace_for(trace.successful_defenses, c));
    std::fprintf(out, "\t%d", trace_opp(trace.successful_defenses, c));
    std::fprintf(out, "\t%d", trace_for(trace.takes, c));
    std::fprintf(out, "\t%d", trace_opp(trace.takes, c));
    std::fprintf(out, "\t%d", trace_for(trace.forced_takes, c));
    std::fprintf(out, "\t%d", trace_opp(trace.forced_takes, c));
    std::fprintf(out, "\t%d", trace_for(trace.voluntary_takes, c));
    std::fprintf(out, "\t%d", trace_opp(trace.voluntary_takes, c));
    for (int phase = 0; phase < 3; ++phase) {
        std::fprintf(out, "\t%d", trace_phase_for(trace.forced_takes_by_phase, c, phase));
        std::fprintf(out, "\t%d", trace_phase_opp(trace.forced_takes_by_phase, c, phase));
    }
    for (int phase = 0; phase < 3; ++phase) {
        std::fprintf(out, "\t%d", trace_phase_for(trace.voluntary_takes_by_phase, c, phase));
        std::fprintf(out, "\t%d", trace_phase_opp(trace.voluntary_takes_by_phase, c, phase));
    }
    std::fprintf(out, "\t%d", trace_for(trace.voluntary_take_min_cover_trump, c));
    std::fprintf(out, "\t%d", trace_opp(trace.voluntary_take_min_cover_trump, c));
    std::fprintf(out, "\t%d", trace_for(trace.voluntary_take_high_trump_deck_ge5, c));
    std::fprintf(out, "\t%d", trace_opp(trace.voluntary_take_high_trump_deck_ge5, c));
    std::fprintf(out, "\t%d", trace_for(trace.cards_taken, c));
    std::fprintf(out, "\t%d", trace_opp(trace.cards_taken, c));
    std::fprintf(out, "\t%d", trace_for(trace.attack_cards, c));
    std::fprintf(out, "\t%d", trace_opp(trace.attack_cards, c));
    std::fprintf(out, "\t%d", trace_for(trace.defense_cards, c));
    std::fprintf(out, "\t%d", trace_opp(trace.defense_cards, c));
    std::fprintf(out, "\t%d", trace_for(trace.trump_attack_cards, c));
    std::fprintf(out, "\t%d", trace_opp(trace.trump_attack_cards, c));
    std::fprintf(out, "\t%d", trace_for(trace.trump_defense_cards, c));
    std::fprintf(out, "\t%d", trace_opp(trace.trump_defense_cards, c));
    for (int phase = 0; phase < 3; ++phase) {
        std::fprintf(out, "\t%d", trace_phase_for(trace.cards_taken_by_phase, c, phase));
        std::fprintf(out, "\t%d", trace_phase_opp(trace.cards_taken_by_phase, c, phase));
    }
    for (int phase = 0; phase < 3; ++phase) {
        std::fprintf(out, "\t%d", trace_phase_for(trace.trump_attack_cards_by_phase, c, phase));
        std::fprintf(out, "\t%d", trace_phase_opp(trace.trump_attack_cards_by_phase, c, phase));
    }
    for (int phase = 0; phase < 3; ++phase) {
        std::fprintf(out, "\t%d", trace_phase_for(trace.successful_defenses_by_phase, c, phase));
        std::fprintf(out, "\t%d", trace_phase_opp(trace.successful_defenses_by_phase, c, phase));
    }
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_battle, c) >= 0 ? 1 : 0);
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_battle, c) >= 0 ? 1 : 0);
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_battle, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_battle, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_attacker, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_attacker, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_table_cards, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_table_cards, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_uncovered, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_uncovered, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_attack_cards, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_attack_cards, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_defense_cards, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_defense_cards, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_trump_attacks, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_trump_attacks, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_trump_defenses, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_trump_defenses, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_min_attack_rank, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_min_attack_rank, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_max_attack_rank, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_max_attack_rank, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_defender_hand_count, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_defender_hand_count, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_attacker_hand_count, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_attacker_hand_count, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_defender_trumps, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_defender_trumps, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_attacker_trumps, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_attacker_trumps, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_defender_high_trumps, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_defender_high_trumps, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_attacker_high_trumps, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_attacker_high_trumps, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_attacker_nontrump_throwins, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_attacker_nontrump_throwins, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_attacker_trump_throwins, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_attacker_trump_throwins, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(trace.first_deck0_forced_take_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(trace.first_deck0_forced_take_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(trace.first_deck0_forced_take_defense_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(trace.first_deck0_forced_take_defense_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(trace.first_deck0_forced_take_defender_hand_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(trace.first_deck0_forced_take_defender_hand_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(trace.first_deck0_forced_take_legal_defense_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(trace.first_deck0_forced_take_legal_defense_mask, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_legal_defense_cards, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_legal_defense_cards, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_legal_trump_defenses, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_legal_trump_defenses, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_legal_nontrump_defenses, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_legal_nontrump_defenses, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_coverable_uncovered, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_coverable_uncovered, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_uncoverable_uncovered, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_uncoverable_uncovered, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_cheapest_cover_rank, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_cheapest_cover_rank, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_cheapest_cover_is_trump, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_cheapest_cover_is_trump, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_opp_later_trump_attack, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_opp_later_trump_attack, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_self_later_trump_attack, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_self_later_trump_attack, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_prior_attack_seen, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_prior_attack_seen, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_prior_attack_battle, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_prior_attack_battle, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_prior_attack_chosen_is_trump, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_prior_attack_chosen_is_trump, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_prior_attack_chosen_rank, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_prior_attack_chosen_rank, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_prior_attack_chosen_suit, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_prior_attack_chosen_suit, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_prior_attack_legal_nontrumps, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_prior_attack_legal_nontrumps, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_prior_attack_legal_trumps, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_prior_attack_legal_trumps, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(
                     trace.first_deck0_forced_take_prior_attack_legal_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(
                     trace.first_deck0_forced_take_prior_attack_legal_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(
                     trace.first_deck0_forced_take_prior_attack_legal_trump_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(
                     trace.first_deck0_forced_take_prior_attack_legal_trump_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(
                     trace.first_deck0_forced_take_prior_attack_legal_nontrump_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(
                     trace.first_deck0_forced_take_prior_attack_legal_nontrump_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(
                     trace.first_deck0_forced_take_prior_attack_legal_force_take_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(
                     trace.first_deck0_forced_take_prior_attack_legal_force_take_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(
                     trace.first_deck0_forced_take_prior_attack_legal_force_high_trump_cover_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(
                     trace.first_deck0_forced_take_prior_attack_legal_force_high_trump_cover_attack_mask, c));
    std::fprintf(out, "\t%d",
                 trace_for(trace.first_deck0_forced_take_prior_attack_chosen_forces_take, c));
    std::fprintf(out, "\t%d",
                 trace_opp(trace.first_deck0_forced_take_prior_attack_chosen_forces_take, c));
    std::fprintf(out, "\t%d",
                 trace_for(trace.first_deck0_forced_take_prior_attack_chosen_forces_high_trump_cover, c));
    std::fprintf(out, "\t%d",
                 trace_opp(trace.first_deck0_forced_take_prior_attack_chosen_forces_high_trump_cover, c));
    std::fprintf(out, "\t%d",
                 trace_for(trace.first_deck0_forced_take_prior_attack_attacker_hand_count, c));
    std::fprintf(out, "\t%d",
                 trace_opp(trace.first_deck0_forced_take_prior_attack_attacker_hand_count, c));
    std::fprintf(out, "\t%d",
                 trace_for(trace.first_deck0_forced_take_prior_attack_defender_hand_count, c));
    std::fprintf(out, "\t%d",
                 trace_opp(trace.first_deck0_forced_take_prior_attack_defender_hand_count, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_prior_attack_attacker_trumps, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_prior_attack_attacker_trumps, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_prior_attack_defender_trumps, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_prior_attack_defender_trumps, c));
    std::fprintf(out, "\t%d",
                 trace_for(trace.first_deck0_forced_take_prior_attack_defender_high_trumps, c));
    std::fprintf(out, "\t%d",
                 trace_opp(trace.first_deck0_forced_take_prior_attack_defender_high_trumps, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_prior_attack_covered, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_prior_attack_covered, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_prior_attack_cover_is_trump, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_prior_attack_cover_is_trump, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_prior_attack_cover_same_rank, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_prior_attack_cover_same_rank, c));
    std::fprintf(out, "\t%d", trace_for(trace.first_deck0_forced_take_prior_attack_cover_rank, c));
    std::fprintf(out, "\t%d", trace_opp(trace.first_deck0_forced_take_prior_attack_cover_rank, c));
    std::fprintf(out, "\t%d",
                 trace_for(trace.first_deck0_forced_take_prior_attack_defender_trumps_after_cover, c));
    std::fprintf(out, "\t%d",
                 trace_opp(trace.first_deck0_forced_take_prior_attack_defender_trumps_after_cover, c));
    std::fprintf(out, "\t%d",
                 trace_for(trace.first_deck0_forced_take_prior_attack_defender_high_trumps_after_cover, c));
    std::fprintf(out, "\t%d",
                 trace_opp(trace.first_deck0_forced_take_prior_attack_defender_high_trumps_after_cover, c));
    std::fprintf(out, "\t%d",
                 trace_for(trace.first_deck0_forced_take_prior_attack_battles_until_forced_take, c));
    std::fprintf(out, "\t%d",
                 trace_opp(trace.first_deck0_forced_take_prior_attack_battles_until_forced_take, c));
    std::fprintf(out, "\t%d",
                 trace_for(trace.first_deck0_forced_take_prior_attack_self_attack_cards_after_cover, c));
    std::fprintf(out, "\t%d",
                 trace_opp(trace.first_deck0_forced_take_prior_attack_self_attack_cards_after_cover, c));
    std::fprintf(out, "\t%d",
                 trace_for(trace.first_deck0_forced_take_prior_attack_self_legal_trump_options_after_cover, c));
    std::fprintf(out, "\t%d",
                 trace_opp(trace.first_deck0_forced_take_prior_attack_self_legal_trump_options_after_cover, c));
    std::fprintf(out, "\t%d",
                 trace_for(trace.first_deck0_forced_take_prior_attack_self_trump_attacks_after_cover, c));
    std::fprintf(out, "\t%d",
                 trace_opp(trace.first_deck0_forced_take_prior_attack_self_trump_attacks_after_cover, c));
    std::fprintf(out, "\t%d",
                 trace_for(trace.first_deck0_forced_take_prior_attack_opp_attack_cards_after_cover, c));
    std::fprintf(out, "\t%d",
                 trace_opp(trace.first_deck0_forced_take_prior_attack_opp_attack_cards_after_cover, c));
    std::fprintf(out, "\t%d",
                 trace_for(trace.first_deck0_forced_take_prior_attack_opp_trump_attacks_after_cover, c));
    std::fprintf(out, "\t%d",
                 trace_opp(trace.first_deck0_forced_take_prior_attack_opp_trump_attacks_after_cover, c));
    std::fprintf(out, "\t%d",
                 trace_for(trace.first_deck0_forced_take_prior_attack_opp_high_trump_attacks_after_cover, c));
    std::fprintf(out, "\t%d",
                 trace_opp(trace.first_deck0_forced_take_prior_attack_opp_high_trump_attacks_after_cover, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_attack_decisions, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_attack_decisions, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_attack_passes_with_trump, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_attack_passes_with_trump, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_attack_nontrump_with_trump, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_attack_nontrump_with_trump, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_attack_trump_with_trump, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_attack_trump_with_trump, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_legal_trump_attack_options, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_legal_trump_attack_options, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_legal_high_trump_attack_options, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_legal_high_trump_attack_options, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_high_trump_attacks, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_high_trump_attacks, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_last_two_attack_count, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_last_two_attack_count, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_last_two_passes_with_trump, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_last_two_passes_with_trump, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_last_two_nontrump_with_trump, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_last_two_nontrump_with_trump, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_last_two_trump_with_trump, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_last_two_trump_with_trump, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_last_decision_seen, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_last_decision_seen, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_last_decision_battle, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_last_decision_battle, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_last_decision_code, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_last_decision_code, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_last_decision_attack_done_available, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_last_decision_attack_done_available, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_last_decision_opponent_hand_count, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_last_decision_opponent_hand_count, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_last_decision_chosen_rank, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_last_decision_chosen_rank, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_last_decision_chosen_suit, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_last_decision_chosen_suit, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_last_decision_chosen_is_trump, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_last_decision_chosen_is_trump, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(trace.deck0_last_decision_hand_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(trace.deck0_last_decision_hand_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(trace.deck0_last_decision_legal_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(trace.deck0_last_decision_legal_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(trace.deck0_last_decision_legal_trump_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(trace.deck0_last_decision_legal_trump_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(trace.deck0_last_decision_legal_high_trump_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(trace.deck0_last_decision_legal_high_trump_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(trace.deck0_last_decision_legal_nontrump_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(trace.deck0_last_decision_legal_nontrump_attack_mask, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_tiny_high_trump_opportunities, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_tiny_high_trump_opportunities, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_tiny_high_trump_chosen_high, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_tiny_high_trump_chosen_high, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_tiny_high_trump_chosen_other, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_tiny_high_trump_chosen_other, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_tiny_high_trump_legal_nontrump_options, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_tiny_high_trump_legal_nontrump_options, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_tiny_high_trump_last_seen, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_tiny_high_trump_last_seen, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_tiny_high_trump_last_hand_count, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_tiny_high_trump_last_hand_count, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_tiny_high_trump_last_opponent_hand_count, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_tiny_high_trump_last_opponent_hand_count, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_tiny_high_trump_last_chosen_rank, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_tiny_high_trump_last_chosen_rank, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_tiny_high_trump_last_chosen_suit, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_tiny_high_trump_last_chosen_suit, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_tiny_high_trump_last_chosen_is_trump, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_tiny_high_trump_last_chosen_is_trump, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(trace.deck0_tiny_high_trump_last_hand_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(trace.deck0_tiny_high_trump_last_hand_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(trace.deck0_tiny_high_trump_last_legal_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(trace.deck0_tiny_high_trump_last_legal_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(
                     trace.deck0_tiny_high_trump_last_legal_high_trump_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(
                     trace.deck0_tiny_high_trump_last_legal_high_trump_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_for(
                     trace.deck0_tiny_high_trump_last_legal_nontrump_attack_mask, c));
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace_mask_opp(
                     trace.deck0_tiny_high_trump_last_legal_nontrump_attack_mask, c));
    const int o = 1 - c;
    const int c_last_slot = trace.deck0_last_two_play_count[c] > 1 ? 1 : 0;
    const int o_last_slot = trace.deck0_last_two_play_count[o] > 1 ? 1 : 0;
    const int c_prev_slot = trace.deck0_last_two_play_count[c] > 1 ? 0 : 1;
    const int o_prev_slot = trace.deck0_last_two_play_count[o] > 1 ? 0 : 1;
    std::fprintf(out, "\t%d", trace_for(trace.deck0_attack_play_count, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_attack_play_count, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_self_played_rank_mask, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_self_played_rank_mask, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_opp_played_rank_mask, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_opp_played_rank_mask, c));
    std::fprintf(out, "\t%d", trace_for(trace.deck0_last_two_play_count, c));
    std::fprintf(out, "\t%d", trace_opp(trace.deck0_last_two_play_count, c));
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[c] > 0 ?
                     trace.deck0_last_two_play_rank[c][c_last_slot] : -1);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[o] > 0 ?
                     trace.deck0_last_two_play_rank[o][o_last_slot] : -1);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[c] > 0 ?
                     trace.deck0_last_two_play_suit[c][c_last_slot] : -1);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[o] > 0 ?
                     trace.deck0_last_two_play_suit[o][o_last_slot] : -1);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[c] > 0 ?
                     trace.deck0_last_two_play_is_trump[c][c_last_slot] : 0);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[o] > 0 ?
                     trace.deck0_last_two_play_is_trump[o][o_last_slot] : 0);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[c] > 0 ?
                     trace.deck0_last_two_play_opponent_hand_count[c][c_last_slot] : 0);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[o] > 0 ?
                     trace.deck0_last_two_play_opponent_hand_count[o][o_last_slot] : 0);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[c] > 0 ?
                     trace.deck0_last_two_play_attack_done_available[c][c_last_slot] : 0);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[o] > 0 ?
                     trace.deck0_last_two_play_attack_done_available[o][o_last_slot] : 0);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[c] > 1 ?
                     trace.deck0_last_two_play_rank[c][c_prev_slot] : -1);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[o] > 1 ?
                     trace.deck0_last_two_play_rank[o][o_prev_slot] : -1);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[c] > 1 ?
                     trace.deck0_last_two_play_suit[c][c_prev_slot] : -1);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[o] > 1 ?
                     trace.deck0_last_two_play_suit[o][o_prev_slot] : -1);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[c] > 1 ?
                     trace.deck0_last_two_play_is_trump[c][c_prev_slot] : 0);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[o] > 1 ?
                     trace.deck0_last_two_play_is_trump[o][o_prev_slot] : 0);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[c] > 1 ?
                     trace.deck0_last_two_play_opponent_hand_count[c][c_prev_slot] : 0);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[o] > 1 ?
                     trace.deck0_last_two_play_opponent_hand_count[o][o_prev_slot] : 0);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[c] > 1 ?
                     trace.deck0_last_two_play_attack_done_available[c][c_prev_slot] : 0);
    std::fprintf(out, "\t%d",
                 trace.deck0_last_two_play_count[o] > 1 ?
                     trace.deck0_last_two_play_attack_done_available[o][o_prev_slot] : 0);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_hand_mask[c][c_last_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_hand_mask[o][o_last_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_legal_attack_mask[c][c_last_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_legal_attack_mask[o][o_last_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_legal_trump_attack_mask[c][c_last_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_legal_trump_attack_mask[o][o_last_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_legal_high_trump_attack_mask[c][c_last_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_legal_high_trump_attack_mask[o][o_last_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_legal_nontrump_attack_mask[c][c_last_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_legal_nontrump_attack_mask[o][o_last_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_hand_mask[c][c_prev_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_hand_mask[o][o_prev_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_legal_attack_mask[c][c_prev_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_legal_attack_mask[o][o_prev_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_legal_trump_attack_mask[c][c_prev_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_legal_trump_attack_mask[o][o_prev_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_legal_high_trump_attack_mask[c][c_prev_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_legal_high_trump_attack_mask[o][o_prev_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_legal_nontrump_attack_mask[c][c_prev_slot]);
    std::fprintf(out, "\t%llu",
                 (unsigned long long)trace.deck0_last_two_play_legal_nontrump_attack_mask[o][o_prev_slot]);
    std::fprintf(out, "\t%d", trace_for(trace.draws, c));
    std::fprintf(out, "\t%d", trace_opp(trace.draws, c));
    std::fprintf(out, "\t%d", trace.max_table_cards);
    std::fprintf(out, "\t%d", trace.max_cards_taken);
    std::fprintf(out, "\t%d", trace.table_cards_total);
    std::fprintf(out, "\t%d", trace.discarded_cards);
    std::fprintf(out, "\t%d", trace.final_deck_count);
    std::fprintf(out, "\t%d", trace_for(trace.final_hand_count, c));
    std::fprintf(out, "\t%d", trace_opp(trace.final_hand_count, c));
    std::fprintf(out, "\t%d", trace_for(trace.final_trumps, c));
    std::fprintf(out, "\t%d", trace_opp(trace.final_trumps, c));
    std::fprintf(out, "\t%d", trace_for(trace.final_high_trumps, c));
    std::fprintf(out, "\t%d", trace_opp(trace.final_high_trumps, c));
    std::fprintf(out, "\t%d", trace_for(trace.final_non_trumps, c));
    std::fprintf(out, "\t%d", trace_opp(trace.final_non_trumps, c));
    std::fprintf(out, "\t%d", trace_for(trace.final_min_trump_rank, c));
    std::fprintf(out, "\t%d", trace_opp(trace.final_min_trump_rank, c));
    std::fprintf(out, "\t%d", trace_for(trace.final_min_non_trump_rank, c));
    std::fprintf(out, "\t%d", trace_opp(trace.final_min_non_trump_rank, c));
    std::fprintf(out, "\t%d", trace_for(trace.final_max_trump_rank, c));
    std::fprintf(out, "\t%d", trace_opp(trace.final_max_trump_rank, c));
    std::fprintf(out, "\t%d", trace_for(trace.final_max_non_trump_rank, c));
    std::fprintf(out, "\t%d", trace_opp(trace.final_max_non_trump_rank, c));
    std::fprintf(out, "\t%llu", (unsigned long long)trace_mask_for(trace.final_hand_mask, c));
    std::fprintf(out, "\t%llu", (unsigned long long)trace_mask_opp(trace.final_hand_mask, c));
    std::fprintf(out, "\t%d\n", trace.final_attacker);
}

EvalOut run_feature_eval(StrategyFn chal, StrategyFn opp, std::uint64_t seed_base, long long n,
                        long long batch, std::FILE* out) {
    double sum = 0.0, sumsq = 0.0;
    long long win = 0, loss = 0, split = 0;
    const char* challenger_name = strategy_label(chal);
    const char* opponent_name = strategy_label(opp);

    print_features_header(out);
    const auto t0 = std::chrono::steady_clock::now();
    for (long long i = 0; i < n; ++i) {
        const std::uint64_t seed = seed_base + std::uint64_t(i);
        const std::uint64_t deck_seed = splitmix(2 * seed + 1);
        const std::uint64_t rng_seed = splitmix(2 * seed + 2);

        GameTrace a_trace;
        GameTrace b_trace;
        const GameResult a = play_game_traced(deck_seed, chal, opp, rng_seed, a_trace);
        const GameResult b = play_game_traced(deck_seed, opp, chal, rng_seed, b_trace);
        const double a_points = points_seat(a, 0);
        const double b_points = points_seat(b, 1);
        const double paired_score = (a_points + b_points) / 2.0;

        sum += paired_score;
        sumsq += paired_score * paired_score;
        if (paired_score > 0.5) ++win;
        else if (paired_score < 0.5) ++loss;
        else ++split;

        print_game_features(out, seed, 0, deck_seed, rng_seed, challenger_name, opponent_name, 0, a,
                            a_points, paired_score, a_trace);
        print_game_features(out, seed, 1, deck_seed, rng_seed, challenger_name, opponent_name, 1, b,
                            b_points, paired_score, b_trace);

        if (batch > 0 && (i + 1) % batch == 0) {
            const double secs = now_seconds(t0);
            const long long done = i + 1;
            const double games = double(done) * 2.0;
            std::fprintf(stderr,
                         "  [features] seeds=%lld rows=%lld point_rate=%.5f games/s=%.0f\n",
                         done, done * 2, sum / double(done),
                         secs > 0 ? games / secs : 0.0);
            std::fflush(stderr);
            std::fflush(out);
        }
    }

    EvalOut eval;
    eval.seeds = n;
    eval.seconds = now_seconds(t0);
    eval.point_rate = (n > 0) ? sum / double(n) : 0.0;
    eval.win = (n > 0) ? double(win) / double(n) : 0.0;
    eval.loss = (n > 0) ? double(loss) / double(n) : 0.0;
    eval.split = (n > 0) ? double(split) / double(n) : 0.0;
    if (n > 1) {
        const double var = (sumsq - sum * sum / double(n)) / double(n - 1);
        const double se = std::sqrt(std::max(0.0, var) / double(n));
        eval.lo = eval.point_rate - 1.96 * se;
        eval.hi = eval.point_rate + 1.96 * se;
    } else {
        eval.lo = eval.hi = eval.point_rate;
    }
    return eval;
}

}  // namespace

int main(int argc, char** argv) {
    const std::string mode = arg_value(argc, argv, "--mode", "ladder");
    const std::string eval = arg_value(argc, argv, "--eval", mode == "features" ? "quick" : "full");
    const std::uint64_t seed_base = std::strtoull(arg_value(argc, argv, "--seed-base", "0"), nullptr, 10);
    const std::string ci_s = arg_value(argc, argv, "--ci", "normal");
    const int resamples = std::atoi(arg_value(argc, argv, "--bootstrap-resamples", "1000"));
    const CiMode ci = (ci_s == "bootstrap") ? CiMode::Bootstrap : CiMode::Normal;

    long long seeds = (eval == "quick") ? 100000 : 5000000;
    if (const char* s = arg_value(argc, argv, "--seeds", nullptr)) seeds = std::atoll(s);
    long long batch = std::atoll(arg_value(argc, argv, "--batch", "5000"));

    std::FILE* banner = (mode == "features") ? stderr : stdout;
    std::fprintf(banner, "=== Durak simulate ===\nmode=%s eval=%s seeds=%lld ci=%s seed_base=%llu\n",
                 mode.c_str(), eval.c_str(), seeds, ci_s.c_str(), (unsigned long long)seed_base);
    print_manifest(banner);

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
    } else if (mode == "features") {
        StrategyFn chal = strategy_by_name(arg_value(argc, argv, "--challenger", "B2"));
        StrategyFn opp = strategy_by_name(arg_value(argc, argv, "--opponent", "B4"));
        if (!chal || !opp) {
            std::fprintf(stderr, "unknown strategy\n");
            return 1;
        }
        const char* features_out = arg_value(argc, argv, "--features-out", "-");
        std::FILE* out = stdout;
        if (std::strcmp(features_out, "-") != 0) {
            out = open_output_file(features_out);
            if (!out) {
                std::fprintf(stderr, "could not open features output: %s\n", features_out);
                return 1;
            }
        }
        EvalOut e = run_feature_eval(chal, opp, seed_base, seeds, batch, out);
        if (out != stdout) std::fclose(out);
        std::fprintf(stderr, "\n--- feature results ---\n");
        std::fprintf(stderr,
                     "%s vs %s point_rate=%.5f  ci95=[%.5f, %.5f]  win=%.4f loss=%.4f "
                     "split=%.4f  (%lld seeds, %.1fs)\n",
                     strategy_label(chal), strategy_label(opp), e.point_rate, e.lo, e.hi, e.win,
                     e.loss, e.split, e.seeds, e.seconds);
    } else {
        std::printf("unknown mode: %s\n", mode.c_str());
        return 1;
    }
    return 0;
}
