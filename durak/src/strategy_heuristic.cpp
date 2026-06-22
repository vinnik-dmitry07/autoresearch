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
//   H1  min_non_trump_attack        -- attack/throw-in with the lowest non-trump card
//   H2  near_rank_group_attack       -- start a low pair/triple when its rank <= min_nt + kDelta
// Parameters: kDelta
// ============================================================================
namespace durak {

constexpr int kDelta = 2;
constexpr int kHeuristicCount = 2;
constexpr int kParameterCount = 1;
constexpr int kComplexity = 100 * kHeuristicCount + 10 * kParameterCount;

const char* strategy_name() { return "B2_heuristic_nomem"; }
int heuristic_count() { return kHeuristicCount; }
int parameter_count() { return kParameterCount; }
int complexity_score() { return kComplexity; }

namespace {

bool is_trump(Card c, int trump) { return suit_of(c) == trump; }

int min_non_trump_rank(CardMask hand, int trump) {
    const CardMask nt = hand & ~SUIT_MASK[trump];
    return nt ? rank_of(lowest(nt)) : NUM_RANKS;
}

// Lower is better. Trumps are heavily penalized so non-trump dumps win; the
// memory term is a small prior favoring ranks that are still mostly unseen.
double attack_value(Card c, int trump, const MemoryFeatures* mem) {
    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);
    return v;
}

Move choose_attack(const LocalFeatures& L, const MemoryFeatures* mem, const LegalMoves& legal,
                   bool has_done) {
    int best = -1;
    double best_v = 1e18;
    for (int i = 0; i < legal.count; ++i) {
        if (legal.moves[i].type != MoveType::AttackPlay) continue;
        const double v = attack_value(legal.moves[i].card, L.trump_suit, mem);
        if (v < best_v) {
            best_v = v;
            best = i;
        }
    }
    if (best < 0) return {MoveType::AttackDone, NO_CARD, 0};

    const int mnt = min_non_trump_rank(L.hand, L.trump_suit);

    if (!has_done) {
        // Initial attack (mandatory). H2: prefer to open a low non-trump group.
        int group = -1;
        for (int r = 0; r < NUM_RANKS; ++r) {
            const int cnt = popcount(L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit]);
            if (cnt >= 2) {
                if (r <= mnt + kDelta) group = r;
                break;  // lowest non-trump pair found
            }
        }
        if (group >= 0) {
            for (int i = 0; i < legal.count; ++i) {
                const Move& m = legal.moves[i];
                if (m.type == MoveType::AttackPlay && rank_of(m.card) == group &&
                    !is_trump(m.card, L.trump_suit))
                    return m;
            }
        }
        return legal.moves[best];  // H1: lowest non-trump (trump only if no choice)
    }

    // Optional throw-in / pile-on: keep dumping low non-trump cards (continues a
    // started group), but never throw trumps and never go above min_nt + kDelta.
    const Card c = legal.moves[best].card;
    if (!is_trump(c, L.trump_suit) && rank_of(c) <= mnt + kDelta) return legal.moves[best];
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

    int best = -1;
    double best_c = 1e18;
    for (int i = 0; i < legal.count; ++i) {
        const Move& m = legal.moves[i];
        if (m.type != MoveType::DefendPlay) continue;
        const Card d = m.card;
        double cost = double(rank_of(d));
        if (is_trump(d, L.trump_suit)) cost += 50.0;  // prefer non-trump (rational base)
        if (mem) cost -= 0.001 * double(mem->unknown_rank_count[rank_of(d)]);
        if (cost < best_c) {
            best_c = cost;
            best = i;
        }
    }
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
