#include "policy_core.hpp"
#include "strategies.hpp"

// ============================================================================
// A3 SWEEP TEMPLATE -- five-heuristic family with tokenized thresholds for the
// LLM-free SweepEngine. NOT compiled directly; the harness substitutes
// __H2_DECK__ / __H2_RANK__ / __H4_OPP__ from sweep.axes and scores each variant
// through the locked precheck/keep gate. Center variant (5 / 2 / 2) is the sweep
// baseline sanity check.
//
// MANIFEST (keep in sync with the constants below):
//   H1  trump_avoidance -- attack and defend with the lowest NON-trump card first.
//   H2  conservation_take -- while deck>=__H2_DECK__, voluntarily take rather than
//                          burn a high trump (rank>=__H2_RANK__) on defense.
//   H3  midgame_pileon -- pile phase: extend with lowest non-trump whose rank is
//                          already on the table; else cheapest non-trump.
//   H4  endgame_trump_strip -- deck==0 and opponent<=__H4_OPP__ cards: open with the
//                          lowest trump to force tempo before they convert.
//   H5  shallow_pile_trump -- pile phase with deck<=3: dump lowest trump before
//                          passing when no non-trump throw-in exists, while not
//                          card-short vs the opponent.
// Parameters: (none -- swept thresholds are structural constants)
// ============================================================================
namespace durak {

constexpr int kHeuristicCount = 5;
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

// H3: extend pile with a table rank when possible; otherwise dump cheapest non-trump.
int pick_pile_throwin(const LocalFeatures& L, const LegalMoves& legal, int trump) {
    bool on_table[NUM_RANKS] = {};
    for (int i = 0; i < L.n_table; ++i) {
        if (L.atk[i] != NO_CARD) on_table[rank_of(L.atk[i])] = true;
        if (L.def[i] != NO_CARD) on_table[rank_of(L.def[i])] = true;
    }
    int best = -1;
    int best_rank = NUM_RANKS;
    for (int i = 0; i < legal.count; ++i) {
        if (legal.moves[i].type != MoveType::AttackPlay) continue;
        const Card c = legal.moves[i].card;
        if (is_trump(c, trump)) continue;
        const int r = rank_of(c);
        if (!on_table[r]) continue;
        if (r < best_rank) {
            best_rank = r;
            best = i;
        }
    }
    if (best >= 0) return best;

    best = -1;
    double best_v = 1e18;
    for (int i = 0; i < legal.count; ++i) {
        if (legal.moves[i].type != MoveType::AttackPlay) continue;
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

// H4: lowest trump open when endgame strip conditions hold.
int pick_lowest_trump(const LegalMoves& legal, MoveType type, int trump) {
    int best = -1;
    double best_v = 1e18;
    for (int i = 0; i < legal.count; ++i) {
        if (legal.moves[i].type != type) continue;
        const Card c = legal.moves[i].card;
        if (!is_trump(c, trump)) continue;
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
        const int best = pick_pile_throwin(L, legal, L.trump_suit);
        if (best >= 0) return legal.moves[best];
        // H5: shed trumps while shallow, but only when not card-short vs opponent.
        if (L.deck_count <= 3 && L.opponent_hand_count <= 5 &&
            popcount(L.hand) >= L.opponent_hand_count) {
            const int dump = pick_lowest_trump(legal, MoveType::AttackPlay, L.trump_suit);
            if (dump >= 0) return legal.moves[dump];
        }
        return {MoveType::AttackDone, NO_CARD, 0};
    }
    if (L.deck_count == 0 && L.opponent_hand_count <= __H4_OPP__ &&
        popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1) {
        const int strip = pick_lowest_trump(legal, MoveType::AttackPlay, L.trump_suit);
        if (strip >= 0) return legal.moves[strip];
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
    if (L.deck_count >= __H2_DECK__ && is_trump(c, L.trump_suit) && rank_of(c) >= __H2_RANK__)
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
