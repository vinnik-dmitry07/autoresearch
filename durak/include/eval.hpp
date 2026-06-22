#pragma once

#include <cmath>
#include <cstdint>

#include "engine.hpp"

namespace durak {

inline std::uint64_t splitmix(std::uint64_t x) {
    x += 0x9E3779B97F4A7C15ull;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ull;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBull;
    return x ^ (x >> 31);
}

inline double points_seat(GameResult r, int seat) {
    if (r == GameResult::Draw) return 0.5;
    const bool seat0_won = (r == GameResult::Player0Win);
    return (seat == 0) ? (seat0_won ? 1.0 : 0.0) : (seat0_won ? 0.0 : 1.0);
}

// Paired score for one deal seed: challenger plays both seats against opponent,
// with the same deck. Returns mean challenger points in {0, .25, .5, .75, 1}.
inline double pair_score(std::uint64_t seed, StrategyFn challenger, StrategyFn opponent) {
    const std::uint64_t deck_seed = splitmix(2 * seed + 1);
    const std::uint64_t rng_seed = splitmix(2 * seed + 2);
    const GameResult a = play_game(deck_seed, challenger, opponent, rng_seed);
    const GameResult b = play_game(deck_seed, opponent, challenger, rng_seed);
    return (points_seat(a, 0) + points_seat(b, 1)) / 2.0;
}

}  // namespace durak
