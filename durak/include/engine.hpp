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

}  // namespace durak
