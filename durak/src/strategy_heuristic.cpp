#include "policy_core.hpp"
#include "strategies.hpp"

// ============================================================================
// B2 -- no-memory heuristic policy core. THIS IS THE ONLY FILE THE AGENT EDITS.
//
// The core consumes LocalFeatures (always) and optional MemoryFeatures. When
// `memory == nullptr` it is the no-memory policy (B2). When `memory != nullptr`
// the SAME logic runs with memory available, used ONLY for tie-breaks / priors
// (B3 ablation). Do not add new heuristic classes that fire only in the memory
// branch, and do not add persistent/global state, I/O, clocks, or randomness.
//
// MANIFEST (keep in sync with the constants below):
//   H1  min_non_trump_play          -- lowest non-trump attack/throw-in/defend; midgame open
//                                       low pair within min+2; endgame pair-open + trump-strip
//   H2  suit_balance_attack         -- opening rank + pile-on ties: minimize suit spread
//   H3  suit_balance_defense        -- among tied minimal beaters, minimize post-play spread
// Parameters: (none)
// ============================================================================
namespace durak {

constexpr int kHeuristicCount = 3;
constexpr int kParameterCount = 0;
constexpr int kComplexity = 100 * kHeuristicCount + 10 * kParameterCount;

const char* strategy_name() { return "B2_heuristic_nomem"; }
int heuristic_count() { return kHeuristicCount; }
int parameter_count() { return kParameterCount; }
int complexity_score() { return kComplexity; }

namespace {

bool is_trump(Card c, int trump) { return suit_of(c) == trump; }

int suit_len(CardMask hand, int suit) { return popcount(hand & SUIT_MASK[suit]); }

// Non-trump suit spread: 0 = perfectly even, higher = more lopsided hand.
int suit_imbalance(CardMask hand, int trump) {
    int lo = 99, hi = 0;
    for (int s = 0; s < NUM_SUITS; ++s) {
        if (s == trump) continue;
        const int n = suit_len(hand, s);
        if (n < lo) lo = n;
        if (n > hi) hi = n;
    }
    return (lo == 99) ? 0 : hi - lo;
}

int imbalance_after(CardMask hand, Card c, int trump) {
    return suit_imbalance(hand & ~card_bit(c), trump);
}

// Lower is better. Trumps are heavily penalized so non-trump dumps win; the
// memory term is a small prior favoring ranks that are still mostly unseen.
double attack_value(Card c, int trump, const MemoryFeatures* mem) {
    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);
    return v;
}

// H2: prefer attacks that leave a more even non-trump suit distribution.
int pick_attack_index(const LocalFeatures& L, const LegalMoves& legal, const MemoryFeatures* mem,
                      int rank_filter, bool rank_only_non_trump) {
    int best = -1;
    double best_v = 1e18;
    int best_imb = 999;
    int best_suit_len = -1;
    for (int i = 0; i < legal.count; ++i) {
        if (legal.moves[i].type != MoveType::AttackPlay) continue;
        const Card c = legal.moves[i].card;
        if (rank_only_non_trump && is_trump(c, L.trump_suit)) continue;
        if (rank_filter >= 0 && rank_of(c) != rank_filter) continue;
        const double v = attack_value(c, L.trump_suit, mem);
        const int imb = imbalance_after(L.hand, c, L.trump_suit);
        const int sl = suit_len(L.hand, suit_of(c));
        if (v < best_v - 1e-9) {
            best_v = v;
            best_imb = imb;
            best_suit_len = sl;
            best = i;
        } else if (v <= best_v + 1e-9) {
            if (imb < best_imb || (imb == best_imb && sl > best_suit_len)) {
                best_imb = imb;
                best_suit_len = sl;
                best = i;
            }
        }
    }
    return best;
}

// H3: spend beaters from suits that keep the hand balanced afterward.
int pick_defense_index(const LocalFeatures& L, const LegalMoves& legal,
                       const MemoryFeatures* mem) {
    int best = -1;
    double best_c = 1e18;
    int best_imb = 999;
    int best_suit_len = -1;
    for (int i = 0; i < legal.count; ++i) {
        const Move& m = legal.moves[i];
        if (m.type != MoveType::DefendPlay) continue;
        const Card d = m.card;
        double cost = double(rank_of(d));
        if (is_trump(d, L.trump_suit)) cost += 50.0;
        if (mem) cost -= 0.001 * double(mem->unknown_rank_count[rank_of(d)]);
        const int imb = imbalance_after(L.hand, d, L.trump_suit);
        const int sl = suit_len(L.hand, suit_of(d));
        if (cost < best_c - 1e-9) {
            best_c = cost;
            best_imb = imb;
            best_suit_len = sl;
            best = i;
        } else if (cost <= best_c + 1e-9) {
            if (imb < best_imb || (imb == best_imb && sl > best_suit_len)) {
                best_imb = imb;
                best_suit_len = sl;
                best = i;
            }
        }
    }
    return best;
}

Move choose_attack(const LocalFeatures& L, const MemoryFeatures* mem, const LegalMoves& legal,
                   bool has_done) {
    const int best = pick_attack_index(L, legal, mem, -1, false);
    if (best < 0) return {MoveType::AttackDone, NO_CARD, 0};

    // H1: initial attack — lowest non-trump; midgame prefer low pair within cap; endgame
    // skip lone singleton if a low pair exists; else trump-strip when trump-rich.
    if (!has_done) {
        const CardMask nt = L.hand & ~SUIT_MASK[L.trump_suit];
        const int mnt = nt ? rank_of(lowest(nt)) : NUM_RANKS;
        int open_rank = mnt;
        if (L.deck_count > 0) {
            int best_imb = 999;
            for (int r = mnt; r <= mnt + 2 && r < NUM_RANKS; ++r) {
                const CardMask rank_cards = L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit];
                if (popcount(rank_cards) < 2) continue;
                const Card sample = lowest(rank_cards);
                const int imb = imbalance_after(L.hand, sample, L.trump_suit);
                if (imb < best_imb) {
                    best_imb = imb;
                    open_rank = r;
                }
            }
        } else if (mnt < NUM_RANKS &&
                   popcount(L.hand & RANK_MASK[mnt] & ~SUIT_MASK[L.trump_suit]) == 1) {
            int best_imb = 999;
            for (int r = mnt + 1; r < NUM_RANKS; ++r) {
                const CardMask rank_cards = L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit];
                if (popcount(rank_cards) < 2) continue;
                const Card sample = lowest(rank_cards);
                const int imb = imbalance_after(L.hand, sample, L.trump_suit);
                if (imb < best_imb) {
                    best_imb = imb;
                    open_rank = r;
                }
            }
            if (open_rank == mnt && L.opponent_hand_count <= 3 &&
                popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 3) {
                Move low_trump{MoveType::AttackDone, NO_CARD, 0};
                for (int i = 0; i < legal.count; ++i) {
                    const Move& m = legal.moves[i];
                    if (m.type != MoveType::AttackPlay || !is_trump(m.card, L.trump_suit)) continue;
                    if (low_trump.type != MoveType::AttackPlay ||
                        rank_of(m.card) < rank_of(low_trump.card))
                        low_trump = m;
                }
                if (low_trump.type == MoveType::AttackPlay) return low_trump;
            }
        }
        const int open = pick_attack_index(L, legal, mem, open_rank, true);
        if (open >= 0) return legal.moves[open];
        return legal.moves[best];
    }

    // Optional throw-in / pile-on: keep dumping the lowest non-trump card, never a trump.
    if (!is_trump(legal.moves[best].card, L.trump_suit)) return legal.moves[best];
    return {MoveType::AttackDone, NO_CARD, 0};
}

Move choose_defense(const LocalFeatures& L, const MemoryFeatures* mem, const LegalMoves& legal) {
    bool coverable[6] = {false, false, false, false, false, false};
    bool any_defend = false;
    for (int i = 0; i < legal.count; ++i) {
        if (legal.moves[i].type == MoveType::DefendPlay) {
            coverable[legal.moves[i].target] = true;
            any_defend = true;
        }
    }
    // Rational base (shared with B1): if any uncovered card cannot be beaten, take now.
    for (int i = 0; i < L.n_table; ++i)
        if (L.def[i] == NO_CARD && !coverable[i]) return {MoveType::DefendTake, NO_CARD, 0};
    if (!any_defend) return {MoveType::DefendTake, NO_CARD, 0};

    const int best = pick_defense_index(L, legal, mem);
    return best >= 0 ? legal.moves[best] : Move{MoveType::DefendTake, NO_CARD, 0};
}

}  // namespace

Move choose_move_core(const LocalFeatures& local, const MemoryFeatures* memory,
                      const LegalMoves& legal) {
    bool is_defense = false;
    bool has_done = false;
    for (int i = 0; i < legal.count; ++i) {
        const MoveType t = legal.moves[i].type;
        if (t == MoveType::DefendPlay || t == MoveType::DefendTake) is_defense = true;
        if (t == MoveType::AttackDone) has_done = true;
    }
    if (is_defense) return choose_defense(local, memory, legal);
    return choose_attack(local, memory, legal, has_done);
}

// No-memory wrapper (B2): never passes memory features to the core.
Move b2_heuristic(const Observation& o, const LegalMoves& legal, Rng&) {
    const LocalFeatures L = make_local_features(o);
    return choose_move_core(L, nullptr, legal);
}

}  // namespace durak
