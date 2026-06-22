#include "strategies.hpp"

// B1: basic no-memory baseline.
//  - Attack: play the single lowest card; never throw in extra cards.
//  - Defense: beat each card with the lowest sufficient card; take only when
//    some uncovered card cannot be beaten.
// No trump avoidance, no grouping, no same-rank trump preference -- those are
// exactly the heuristics that distinguish B2.
namespace durak {

namespace {

bool classify_defense(const LegalMoves& legal, bool& has_done) {
    has_done = false;
    bool is_defense = false;
    for (int i = 0; i < legal.count; ++i) {
        const MoveType t = legal.moves[i].type;
        if (t == MoveType::DefendPlay || t == MoveType::DefendTake) is_defense = true;
        if (t == MoveType::AttackDone) has_done = true;
    }
    return is_defense;
}

}  // namespace

Move b1_basic(const Observation& o, const LegalMoves& legal, Rng&) {
    bool has_done = false;
    const bool is_defense = classify_defense(legal, has_done);

    if (!is_defense) {
        if (has_done) return {MoveType::AttackDone, NO_CARD, 0};  // no pile-on
        int best = -1;
        Card best_card = NO_CARD;
        for (int i = 0; i < legal.count; ++i) {
            if (legal.moves[i].type != MoveType::AttackPlay) continue;
            if (best < 0 || legal.moves[i].card < best_card) {
                best = i;
                best_card = legal.moves[i].card;
            }
        }
        return best >= 0 ? legal.moves[best] : Move{MoveType::AttackDone, NO_CARD, 0};
    }

    // Defense: take if any uncovered attack cannot be beaten.
    bool coverable[6] = {false, false, false, false, false, false};
    for (int i = 0; i < legal.count; ++i)
        if (legal.moves[i].type == MoveType::DefendPlay) coverable[legal.moves[i].target] = true;
    for (int i = 0; i < o.n_table; ++i)
        if (o.def[i] == NO_CARD && !coverable[i]) return {MoveType::DefendTake, NO_CARD, 0};

    int best = -1;
    Card best_card = NO_CARD;
    for (int i = 0; i < legal.count; ++i) {
        if (legal.moves[i].type != MoveType::DefendPlay) continue;
        if (best < 0 || legal.moves[i].card < best_card) {
            best = i;
            best_card = legal.moves[i].card;
        }
    }
    return best >= 0 ? legal.moves[best] : Move{MoveType::DefendTake, NO_CARD, 0};
}

}  // namespace durak
