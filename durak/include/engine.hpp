#pragma once

#include <array>
#include <cstdint>

#include "cards.hpp"
#include "move.hpp"

namespace durak {

enum class GameResult : int { Player0Win = 0, Player1Win = 1, Draw = 2 };

// Per-player belief over card locations. Built by the engine from public events
// only; it never leaks the opponent's hidden hand (only its size).
struct MemoryView {
    CardMask known_discarded = 0;         // bito pile, out of play for good
    CardMask known_in_own_hand = 0;       // this player's hand
    CardMask known_on_table = 0;          // attack + defense cards currently on the table
    CardMask known_in_opponent_hand = 0;  // cards seen entering the opponent's hand (e.g. a take)
    CardMask seen_ever = 0;               // union of everything observed so far (audit)
    int deck_count = 0;
    int opponent_hand_count = 0;          // size only, not identity
    int trump_suit = 0;
    Card trump_card = NO_CARD;            // bottom card, public
};

// Everything a strategy may observe. No-memory strategies ignore `memory`.
struct Observation {
    CardMask hand = 0;
    CardMask table_attack = 0;
    CardMask table_defense = 0;
    std::array<Card, 6> atk{};  // attack cards in play order
    std::array<Card, 6> def{};  // def[i] covers atk[i], or NO_CARD if uncovered
    int n_table = 0;
    int trump_suit = 0;
    Card trump_card = NO_CARD;
    int deck_count = 0;
    int opponent_hand_count = 0;
    bool is_attacker = false;
    const MemoryView* memory = nullptr;
};

// Deterministic splitmix64 stream. The only randomness source a strategy may use
// (B0 only); the no-memory heuristic core never receives it.
struct Rng {
    std::uint64_t s;
    explicit Rng(std::uint64_t seed) : s(seed ? seed : 0x9E3779B97F4A7C15ull) {}
    std::uint64_t next() {
        std::uint64_t z = (s += 0x9E3779B97F4A7C15ull);
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
        return z ^ (z >> 31);
    }
    std::uint32_t bounded(std::uint32_t n) { return n ? std::uint32_t(next() % n) : 0; }
};

using StrategyFn = Move (*)(const Observation&, const LegalMoves&, Rng&);

struct GameState {
    CardMask hands[2] = {0, 0};
    std::array<Card, NUM_CARDS> deck{};
    int deck_count = 0;
    Card trump_card = NO_CARD;
    int trump_suit = 0;

    std::array<Card, 6> atk{};
    std::array<Card, 6> def{};
    int n_table = 0;

    CardMask discarded = 0;
    CardMask known_opp[2] = {0, 0};  // known_opp[p] = cards p knows are in the opponent's hand

    int attacker = 0;
};

struct GameTrace {
    int initial_attacker = 0;
    int trump_rank = 0;
    int trump_suit = 0;
    int initial_trumps[2] = {0, 0};
    int initial_high_trumps[2] = {0, 0};
    int initial_non_trumps[2] = {0, 0};
    int initial_pairs[2] = {0, 0};
    int initial_min_non_trump_rank[2] = {-1, -1};
    int initial_min_trump_rank[2] = {-1, -1};

    int battles = 0;
    int deck_empty_after_battle = -1;
    int attacks_started[2] = {0, 0};
    int successful_defenses[2] = {0, 0};
    int takes[2] = {0, 0};
    int forced_takes[2] = {0, 0};
    int voluntary_takes[2] = {0, 0};
    int voluntary_take_min_cover_trump[2] = {0, 0};
    int voluntary_take_high_trump_deck_ge5[2] = {0, 0};
    int cards_taken[2] = {0, 0};
    int attack_cards[2] = {0, 0};
    int defense_cards[2] = {0, 0};
    int trump_attack_cards[2] = {0, 0};
    int trump_defense_cards[2] = {0, 0};
    int draws[2] = {0, 0};
    int forced_takes_by_phase[2][3] = {};
    int voluntary_takes_by_phase[2][3] = {};
    int cards_taken_by_phase[2][3] = {};
    int trump_attack_cards_by_phase[2][3] = {};
    int successful_defenses_by_phase[2][3] = {};

    int first_deck0_forced_take_battle[2] = {-1, -1};
    int first_deck0_forced_take_attacker[2] = {-1, -1};
    int first_deck0_forced_take_table_cards[2] = {0, 0};
    int first_deck0_forced_take_uncovered[2] = {0, 0};
    int first_deck0_forced_take_attack_cards[2] = {0, 0};
    int first_deck0_forced_take_defense_cards[2] = {0, 0};
    int first_deck0_forced_take_trump_attacks[2] = {0, 0};
    int first_deck0_forced_take_trump_defenses[2] = {0, 0};
    int first_deck0_forced_take_min_attack_rank[2] = {-1, -1};
    int first_deck0_forced_take_max_attack_rank[2] = {-1, -1};
    int first_deck0_forced_take_defender_hand_count[2] = {0, 0};
    int first_deck0_forced_take_attacker_hand_count[2] = {0, 0};
    int first_deck0_forced_take_defender_trumps[2] = {0, 0};
    int first_deck0_forced_take_attacker_trumps[2] = {0, 0};
    int first_deck0_forced_take_defender_high_trumps[2] = {0, 0};
    int first_deck0_forced_take_attacker_high_trumps[2] = {0, 0};
    int first_deck0_forced_take_attacker_nontrump_throwins[2] = {0, 0};
    int first_deck0_forced_take_attacker_trump_throwins[2] = {0, 0};
    CardMask first_deck0_forced_take_attack_mask[2] = {0, 0};
    CardMask first_deck0_forced_take_defense_mask[2] = {0, 0};
    CardMask first_deck0_forced_take_defender_hand_mask[2] = {0, 0};
    CardMask first_deck0_forced_take_legal_defense_mask[2] = {0, 0};
    int first_deck0_forced_take_legal_defense_cards[2] = {0, 0};
    int first_deck0_forced_take_legal_trump_defenses[2] = {0, 0};
    int first_deck0_forced_take_legal_nontrump_defenses[2] = {0, 0};
    int first_deck0_forced_take_coverable_uncovered[2] = {0, 0};
    int first_deck0_forced_take_uncoverable_uncovered[2] = {0, 0};
    int first_deck0_forced_take_cheapest_cover_rank[2] = {-1, -1};
    int first_deck0_forced_take_cheapest_cover_is_trump[2] = {0, 0};
    int first_deck0_forced_take_opp_later_trump_attack[2] = {0, 0};
    int first_deck0_forced_take_self_later_trump_attack[2] = {0, 0};

    int last_deck0_attack_seen[2] = {0, 0};
    int last_deck0_attack_battle[2] = {-1, -1};
    int last_deck0_attack_slot[2] = {-1, -1};
    int last_deck0_attack_chosen_is_trump[2] = {0, 0};
    int last_deck0_attack_chosen_rank[2] = {-1, -1};
    int last_deck0_attack_chosen_suit[2] = {-1, -1};
    int last_deck0_attack_legal_nontrumps[2] = {0, 0};
    int last_deck0_attack_legal_trumps[2] = {0, 0};
    CardMask last_deck0_attack_legal_attack_mask[2] = {0, 0};
    CardMask last_deck0_attack_legal_trump_attack_mask[2] = {0, 0};
    CardMask last_deck0_attack_legal_nontrump_attack_mask[2] = {0, 0};
    CardMask last_deck0_attack_legal_force_take_attack_mask[2] = {0, 0};
    CardMask last_deck0_attack_legal_force_high_trump_cover_attack_mask[2] = {0, 0};
    int last_deck0_attack_chosen_forces_take[2] = {0, 0};
    int last_deck0_attack_chosen_forces_high_trump_cover[2] = {0, 0};
    int last_deck0_attack_attacker_hand_count[2] = {0, 0};
    int last_deck0_attack_defender_hand_count[2] = {0, 0};
    int last_deck0_attack_attacker_trumps[2] = {0, 0};
    int last_deck0_attack_defender_trumps[2] = {0, 0};
    int last_deck0_attack_defender_high_trumps[2] = {0, 0};
    int last_deck0_attack_covered[2] = {0, 0};
    int last_deck0_attack_cover_is_trump[2] = {0, 0};
    int last_deck0_attack_cover_same_rank[2] = {0, 0};
    int last_deck0_attack_cover_rank[2] = {-1, -1};
    int last_deck0_attack_defender_trumps_after_cover[2] = {0, 0};
    int last_deck0_attack_defender_high_trumps_after_cover[2] = {0, 0};
    int last_deck0_attack_tracking_after_cover[2] = {0, 0};
    int last_deck0_attack_self_attack_cards_after_cover[2] = {0, 0};
    int last_deck0_attack_self_legal_trump_options_after_cover[2] = {0, 0};
    int last_deck0_attack_self_trump_attacks_after_cover[2] = {0, 0};
    int last_deck0_attack_opp_attack_cards_after_cover[2] = {0, 0};
    int last_deck0_attack_opp_trump_attacks_after_cover[2] = {0, 0};
    int last_deck0_attack_opp_high_trump_attacks_after_cover[2] = {0, 0};

    int first_deck0_forced_take_prior_attack_seen[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_battle[2] = {-1, -1};
    int first_deck0_forced_take_prior_attack_chosen_is_trump[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_chosen_rank[2] = {-1, -1};
    int first_deck0_forced_take_prior_attack_chosen_suit[2] = {-1, -1};
    int first_deck0_forced_take_prior_attack_legal_nontrumps[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_legal_trumps[2] = {0, 0};
    CardMask first_deck0_forced_take_prior_attack_legal_attack_mask[2] = {0, 0};
    CardMask first_deck0_forced_take_prior_attack_legal_trump_attack_mask[2] = {0, 0};
    CardMask first_deck0_forced_take_prior_attack_legal_nontrump_attack_mask[2] = {0, 0};
    CardMask first_deck0_forced_take_prior_attack_legal_force_take_attack_mask[2] = {0, 0};
    CardMask first_deck0_forced_take_prior_attack_legal_force_high_trump_cover_attack_mask[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_chosen_forces_take[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_chosen_forces_high_trump_cover[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_attacker_hand_count[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_defender_hand_count[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_attacker_trumps[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_defender_trumps[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_defender_high_trumps[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_covered[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_cover_is_trump[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_cover_same_rank[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_cover_rank[2] = {-1, -1};
    int first_deck0_forced_take_prior_attack_defender_trumps_after_cover[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_defender_high_trumps_after_cover[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_battles_until_forced_take[2] = {-1, -1};
    int first_deck0_forced_take_prior_attack_self_attack_cards_after_cover[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_self_legal_trump_options_after_cover[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_self_trump_attacks_after_cover[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_opp_attack_cards_after_cover[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_opp_trump_attacks_after_cover[2] = {0, 0};
    int first_deck0_forced_take_prior_attack_opp_high_trump_attacks_after_cover[2] = {0, 0};

    int deck0_attack_decisions[2] = {0, 0};
    int deck0_attack_passes_with_trump[2] = {0, 0};
    int deck0_attack_nontrump_with_trump[2] = {0, 0};
    int deck0_attack_trump_with_trump[2] = {0, 0};
    int deck0_legal_trump_attack_options[2] = {0, 0};
    int deck0_legal_high_trump_attack_options[2] = {0, 0};
    int deck0_high_trump_attacks[2] = {0, 0};
    int deck0_last_two_attack_count[2] = {0, 0};
    int deck0_last_two_attack_codes[2][2] = {};
    int deck0_last_two_passes_with_trump[2] = {0, 0};
    int deck0_last_two_nontrump_with_trump[2] = {0, 0};
    int deck0_last_two_trump_with_trump[2] = {0, 0};
    int deck0_last_decision_seen[2] = {0, 0};
    int deck0_last_decision_battle[2] = {-1, -1};
    int deck0_last_decision_code[2] = {-1, -1};
    int deck0_last_decision_attack_done_available[2] = {0, 0};
    int deck0_last_decision_opponent_hand_count[2] = {0, 0};
    int deck0_last_decision_chosen_rank[2] = {-1, -1};
    int deck0_last_decision_chosen_suit[2] = {-1, -1};
    int deck0_last_decision_chosen_is_trump[2] = {0, 0};
    CardMask deck0_last_decision_hand_mask[2] = {0, 0};
    CardMask deck0_last_decision_legal_attack_mask[2] = {0, 0};
    CardMask deck0_last_decision_legal_trump_attack_mask[2] = {0, 0};
    CardMask deck0_last_decision_legal_high_trump_attack_mask[2] = {0, 0};
    CardMask deck0_last_decision_legal_nontrump_attack_mask[2] = {0, 0};
    int deck0_tiny_high_trump_opportunities[2] = {0, 0};
    int deck0_tiny_high_trump_chosen_high[2] = {0, 0};
    int deck0_tiny_high_trump_chosen_other[2] = {0, 0};
    int deck0_tiny_high_trump_legal_nontrump_options[2] = {0, 0};
    int deck0_tiny_high_trump_last_seen[2] = {0, 0};
    int deck0_tiny_high_trump_last_hand_count[2] = {0, 0};
    int deck0_tiny_high_trump_last_opponent_hand_count[2] = {0, 0};
    int deck0_tiny_high_trump_last_chosen_rank[2] = {-1, -1};
    int deck0_tiny_high_trump_last_chosen_suit[2] = {-1, -1};
    int deck0_tiny_high_trump_last_chosen_is_trump[2] = {0, 0};
    CardMask deck0_tiny_high_trump_last_hand_mask[2] = {0, 0};
    CardMask deck0_tiny_high_trump_last_legal_attack_mask[2] = {0, 0};
    CardMask deck0_tiny_high_trump_last_legal_high_trump_attack_mask[2] = {0, 0};
    CardMask deck0_tiny_high_trump_last_legal_nontrump_attack_mask[2] = {0, 0};
    int deck0_attack_play_count[2] = {0, 0};
    int deck0_self_played_rank_mask[2] = {0, 0};
    int deck0_opp_played_rank_mask[2] = {0, 0};
    int deck0_last_two_play_count[2] = {0, 0};
    int deck0_last_two_play_rank[2][2] = {};
    int deck0_last_two_play_suit[2][2] = {};
    int deck0_last_two_play_is_trump[2][2] = {};
    int deck0_last_two_play_opponent_hand_count[2][2] = {};
    int deck0_last_two_play_attack_done_available[2][2] = {};
    CardMask deck0_last_two_play_hand_mask[2][2] = {};
    CardMask deck0_last_two_play_legal_attack_mask[2][2] = {};
    CardMask deck0_last_two_play_legal_trump_attack_mask[2][2] = {};
    CardMask deck0_last_two_play_legal_high_trump_attack_mask[2][2] = {};
    CardMask deck0_last_two_play_legal_nontrump_attack_mask[2][2] = {};

    int max_table_cards = 0;
    int max_cards_taken = 0;
    int table_cards_total = 0;
    int discarded_cards = 0;
    int final_deck_count = 0;
    int final_hand_count[2] = {0, 0};
    int final_trumps[2] = {0, 0};
    int final_high_trumps[2] = {0, 0};
    int final_non_trumps[2] = {0, 0};
    int final_min_trump_rank[2] = {-1, -1};
    int final_min_non_trump_rank[2] = {-1, -1};
    int final_max_trump_rank[2] = {-1, -1};
    int final_max_non_trump_rank[2] = {-1, -1};
    CardMask final_hand_mask[2] = {0, 0};
    int final_attacker = 0;
};

// --- Engine primitives (also exercised directly by golden tests) ---
void reset_table(GameState& st);
LegalMoves gen_attack_moves(const GameState& st, int attacker, int limit);
LegalMoves gen_defense_moves(const GameState& st, int defender);
int first_attacker(const GameState& st);
GameState new_game(std::uint64_t deck_seed);
void draw_to_six(GameState& st, int player);

// Runs a single battle. Returns true if the defender took the cards.
bool run_battle(GameState& st, StrategyFn seat0, StrategyFn seat1, Rng& rng);

GameResult play_from_state(GameState st, StrategyFn seat0, StrategyFn seat1, Rng& rng);
GameResult play_game(std::uint64_t deck_seed, StrategyFn seat0, StrategyFn seat1, std::uint64_t rng_seed);
GameResult play_game_traced(std::uint64_t deck_seed, StrategyFn seat0, StrategyFn seat1,
                            std::uint64_t rng_seed, GameTrace& trace);

}  // namespace durak
