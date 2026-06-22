#include "strategies.hpp"

// B4: independent memory-counting baseline (the sparring partner for reporting).
// Uses a per-player belief (MemoryView) but is NOT a full hidden-state solver.
//
// Memory is used in two clear ways:
//   1. Attack selection scores cards by how many of their potential beaters are
//      still unaccounted for (an unknown card could be in the opponent's hand).
//   2. Defense may voluntarily take to preserve a high trump early, when many
//      trumps are still unknown.
// Otherwise it follows sensible play: dump low non-trump cards, group low cards,
// beat with the minimal sufficient card, prefer a same-rank trump when forced,
// and dump aggressively once the deck is empty.
namespace durak {

namespace {

CardMask unknown_pool(const MemoryView& mv) {
    const CardMask known = mv.known_discarded | mv.known_in_own_hand | mv.known_on_table |
                           mv.known_in_opponent_hand;
    return ALL_CARDS & ~known;
}

// Cards in `pool` that could beat card `c`.
int beaters_in(Card c, CardMask pool, int trump) {
    int cnt = 0;
    const int s = suit_of(c), r = rank_of(c);
    for (int rr = r + 1; rr < NUM_RANKS; ++rr)
        if (pool & card_bit(make_card(rr, s))) ++cnt;
    if (s != trump) cnt += popcount(pool & SUIT_MASK[trump]);
    return cnt;
}

bool is_trump(Card c, int trump) { return suit_of(c) == trump; }

int min_non_trump_rank(CardMask hand, int trump) {
    const CardMask nt = hand & ~SUIT_MASK[trump];
    return nt ? rank_of(lowest(nt)) : NUM_RANKS;
}

double attack_value(Card c, const MemoryView& mv, CardMask pool) {
    double v = double(rank_of(c));
    if (is_trump(c, mv.trump_suit)) v += 100.0;
    v += 0.1 * double(beaters_in(c, pool, mv.trump_suit));  // prefer hard-to-beat dumps
    return v;
}

Move choose_attack(const Observation& o, const LegalMoves& legal, bool has_done) {
    const MemoryView& mv = *o.memory;
    const CardMask pool = unknown_pool(mv);

    int best = -1;
    double best_v = 1e18;
    for (int i = 0; i < legal.count; ++i) {
        if (legal.moves[i].type != MoveType::AttackPlay) continue;
        const double v = attack_value(legal.moves[i].card, mv, pool);
        if (v < best_v) {
            best_v = v;
            best = i;
        }
    }
    if (best < 0) return {MoveType::AttackDone, NO_CARD, 0};

    const int mnt = min_non_trump_rank(o.hand, mv.trump_suit);
    const bool endgame = (o.deck_count == 0);
    const int cap = mnt + (endgame ? 4 : 2);

    if (!has_done) {
        int group = -1;
        for (int r = 0; r < NUM_RANKS; ++r) {
            const int cnt = popcount(o.hand & RANK_MASK[r] & ~SUIT_MASK[mv.trump_suit]);
            if (cnt >= 2) {
                if (r <= cap) group = r;
                break;
            }
        }
        if (group >= 0) {
            for (int i = 0; i < legal.count; ++i) {
                const Move& m = legal.moves[i];
                if (m.type == MoveType::AttackPlay && rank_of(m.card) == group &&
                    !is_trump(m.card, mv.trump_suit))
                    return m;
            }
        }
        return legal.moves[best];
    }

    const Card c = legal.moves[best].card;
    if (!is_trump(c, mv.trump_suit) && rank_of(c) <= cap) return legal.moves[best];
    return {MoveType::AttackDone, NO_CARD, 0};
}

Move choose_defense(const Observation& o, const LegalMoves& legal) {
    const MemoryView& mv = *o.memory;
    const CardMask pool = unknown_pool(mv);

    bool coverable[6] = {false, false, false, false, false, false};
    bool any_defend = false;
    for (int i = 0; i < legal.count; ++i) {
        if (legal.moves[i].type == MoveType::DefendPlay) {
            coverable[legal.moves[i].target] = true;
            any_defend = true;
        }
    }
    for (int i = 0; i < o.n_table; ++i)
        if (o.def[i] == NO_CARD && !coverable[i]) return {MoveType::DefendTake, NO_CARD, 0};
    if (!any_defend) return {MoveType::DefendTake, NO_CARD, 0};

    int best = -1;
    double best_c = 1e18;
    bool best_is_trump = false;
    int best_trump_rank = 0;
    for (int i = 0; i < legal.count; ++i) {
        const Move& m = legal.moves[i];
        if (m.type != MoveType::DefendPlay) continue;
        const Card d = m.card;
        const Card a = o.atk[m.target];
        double cost = double(rank_of(d));
        const bool dt = is_trump(d, mv.trump_suit);
        if (dt) {
            cost += 50.0;
            if (rank_of(d) == rank_of(a)) cost -= 25.0;  // same-rank trump when forced
        }
        if (cost < best_c) {
            best_c = cost;
            best = i;
            best_is_trump = dt;
            best_trump_rank = rank_of(d);
        }
    }
    if (best < 0) return {MoveType::DefendTake, NO_CARD, 0};

    // Memory-informed voluntary take: don't burn a high trump early while many
    // trumps are still out there and only a single card is attacking.
    const int unknown_trumps = popcount(pool & SUIT_MASK[mv.trump_suit]);
    if (best_is_trump && best_trump_rank >= 7 && o.deck_count >= 6 && unknown_trumps >= 3 &&
        o.n_table == 1)
        return {MoveType::DefendTake, NO_CARD, 0};

    return legal.moves[best];
}

}  // namespace

Move b4_mem(const Observation& o, const LegalMoves& legal, Rng&) {
    bool is_defense = false;
    bool has_done = false;
    for (int i = 0; i < legal.count; ++i) {
        const MoveType t = legal.moves[i].type;
        if (t == MoveType::DefendPlay || t == MoveType::DefendTake) is_defense = true;
        if (t == MoveType::AttackDone) has_done = true;
    }
    if (is_defense) return choose_defense(o, legal);
    return choose_attack(o, legal, has_done);
}

}  // namespace durak
