#include "policy_core.hpp"
#include "strategies.hpp"

// ============================================================================
// B2 -- no-memory heuristic policy core. THIS IS THE ONLY FILE THE AGENT EDITS.
//
// FROM-SCRATCH SEED. This is the minimal heuristic that clears the locked
// "B2 beats B1" sanity gate and nothing more; the search starts here. It is the
// basic baseline (lowest card, take only when forced, no pile-on) plus a single
// idea: spend non-trumps before trumps. Everything else is open for the agent.
//
// The core consumes LocalFeatures (always) and optional MemoryFeatures. When
// `memory == nullptr` it is the no-memory policy (B2). When `memory != nullptr`
// the SAME logic runs (B3 ablation); this seed ignores memory entirely, so B3
// plays identically to B2 until the agent wires a real tie-break prior. Keep it a
// pure function of the features: no persistent or global mutable state, no I/O, no
// clocks, no concurrency, no randomness (see the forbidden-symbol check).
//
// MANIFEST (keep in sync with the constants below):
//   H1  trump_avoidance -- attack and defend with the lowest NON-trump card
//                          first; fall back to the lowest trump only when no
//                          non-trump option exists. Open only (no pile-on);
//                          take only when an uncovered card cannot be beaten.
//   H2  conservation_take -- while deck>=5, voluntarily take rather than burn
//                          a high trump (rank 8+) on defense.
//   H3  deck_empty_pileon -- when deck==0, keep rank-matched throw-ins going
//                          (cheapest non-trump) instead of passing at once.
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

// Lower is better. Rank orders the choice; the +100 trump penalty (H1) makes
// every non-trump strictly cheaper than every trump, so trumps are spent last.
double card_cost(Card c, int trump) {
    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    return v;
}

int pick_cheapest(const LegalMoves& legal, MoveType type, int trump) {
    int best = -1;
    double best_v = 1e18;
    for (int i = 0; i < legal.count; ++i) {
        if (legal.moves[i].type != type) continue;
        const double v = card_cost(legal.moves[i].card, trump);
        if (v < best_v) {
            best_v = v;
            best = i;
        }
    }
    return best;
}

// H3: pile phase only dumps non-trumps; trumps stay for direct attacks.
int pick_cheapest_nontrump(const LegalMoves& legal, MoveType type, int trump) {
    int best = -1;
    double best_v = 1e18;
    for (int i = 0; i < legal.count; ++i) {
        if (legal.moves[i].type != type) continue;
        const Card c = legal.moves[i].card;
        if (is_trump(c, trump)) continue;
        const double v = double(rank_of(c));
        if (v < best_v) {
            best_v = v;
            best = i;
        }
    }
    return best;
}

Move choose_attack(const LocalFeatures& L, const LegalMoves& legal, bool has_done) {
    if (has_done) {
        if (L.deck_count == 0) {
            const int best = pick_cheapest_nontrump(legal, MoveType::AttackPlay, L.trump_suit);
            if (best >= 0) return legal.moves[best];
        }
        return {MoveType::AttackDone, NO_CARD, 0};
    }
    const int best = pick_cheapest(legal, MoveType::AttackPlay, L.trump_suit);
    if (best < 0) return {MoveType::AttackDone, NO_CARD, 0};
    return legal.moves[best];
}

Move choose_defense(const LocalFeatures& L, const LegalMoves& legal) {
    bool coverable[6] = {false, false, false, false, false, false};
    bool any_defend = false;
    for (int i = 0; i < legal.count; ++i) {
        if (legal.moves[i].type == MoveType::DefendPlay) {
            coverable[legal.moves[i].target] = true;
            any_defend = true;
        }
    }
    // Rational base (shared with B1): if any uncovered card cannot be beaten, take.
    for (int i = 0; i < L.n_table; ++i)
        if (L.def[i] == NO_CARD && !coverable[i]) return {MoveType::DefendTake, NO_CARD, 0};
    if (!any_defend) return {MoveType::DefendTake, NO_CARD, 0};

    const int best = pick_cheapest(legal, MoveType::DefendPlay, L.trump_suit);
    if (best < 0) return {MoveType::DefendTake, NO_CARD, 0};
    const Card c = legal.moves[best].card;
    // H2: keep high trumps while the deck is still deep.
    if (L.deck_count >= 5 && is_trump(c, L.trump_suit) && rank_of(c) >= 2)
        return {MoveType::DefendTake, NO_CARD, 0};
    return legal.moves[best];
}

}  // namespace

Move choose_move_core(const LocalFeatures& local, const MemoryFeatures* /*memory*/,
                      const LegalMoves& legal) {
    bool is_defense = false;
    bool has_done = false;
    for (int i = 0; i < legal.count; ++i) {
        const MoveType t = legal.moves[i].type;
        if (t == MoveType::DefendPlay || t == MoveType::DefendTake) is_defense = true;
        if (t == MoveType::AttackDone) has_done = true;
    }
    if (is_defense) return choose_defense(local, legal);
    return choose_attack(local, legal, has_done);
}

// No-memory wrapper (B2): never passes memory features to the core.
Move b2_heuristic(const Observation& o, const LegalMoves& legal, Rng&) {
    const LocalFeatures L = make_local_features(o);
    return choose_move_core(L, nullptr, legal);
}

}  // namespace durak
