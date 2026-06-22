#pragma once

#include <array>

#include "cards.hpp"

namespace durak {

enum class MoveType : std::uint8_t { AttackPlay, AttackDone, DefendPlay, DefendTake };

// Trivial aggregate: never default-initialized in hot paths (see LegalMoves).
struct Move {
    MoveType type;
    Card card;
    std::uint8_t target;  // index of the attack card being beaten (DefendPlay only)
};

// Upper bound: <=6 uncovered attacks, each beatable by a bounded subset of a hand.
constexpr int MAX_MOVES = 160;

struct LegalMoves {
    std::array<Move, MAX_MOVES> moves;  // intentionally uninitialized; only [0, count) is valid
    int count = 0;

    void add(Move m) { moves[count++] = m; }
    const Move& operator[](int i) const { return moves[i]; }
};

}  // namespace durak
