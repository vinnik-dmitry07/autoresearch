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
//   H2  opp_void_suit_attack        -- prefer suits opponent trumped off-suit on this table
//   H3  opp_shown_suit_deprioritize -- avoid pile-on in suits opponent beat in-suit this table
//   H4  ev_hand_score               -- score hand strength (trumps, low cards, pairs, suits)
//   H5  ev_refill_compare           -- defense cost vs expected draw quality from deck
// Parameters: (none)
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

// Table-only clues about opponent non-trump suits (current battle, no discard memory).
struct OppSuitClues {
    bool has_non_trump[NUM_SUITS] = {false, false, false, false};
    bool likely_void[NUM_SUITS] = {false, false, false, false};
};

OppSuitClues read_opp_suit_clues(const LocalFeatures& L) {
    OppSuitClues c;
    if (!L.is_attacker) return c;
    for (int i = 0; i < L.n_table; ++i) {
        const Card a = L.atk[i];
        if (a == NO_CARD) continue;
        const Card d = L.def[i];
        if (d == NO_CARD) continue;
        const int as = suit_of(a);
        const int ds = suit_of(d);
        if (as != L.trump_suit && ds == L.trump_suit)
            c.likely_void[as] = true;
        else if (as == ds && as != L.trump_suit)
            c.has_non_trump[as] = true;
    }
    return c;
}

// H2/H3: nudge attack scoring from opponent suit clues visible on the table.
double opp_suit_attack_adjust(Card c, int trump, const OppSuitClues& clues) {
    const int s = suit_of(c);
    if (s == trump) return 0.0;
    double adj = 0.0;
    if (clues.likely_void[s]) adj -= 5.0;
    if (clues.has_non_trump[s] && !clues.likely_void[s]) adj += 1.5;
    return adj;
}

// H4: strategic hand strength (higher = better). Memoryless, from hand + trump only.
double hand_value(CardMask hand, int trump) {
    if (!hand) return 0.0;
    double v = 0.0;
    const int tr = popcount(hand & SUIT_MASK[trump]);
    v += 4.5 * double(tr);
    int non_trump_suits = 0;
    for (int s = 0; s < NUM_SUITS; ++s) {
        if (s == trump) continue;
        const CardMask sm = hand & SUIT_MASK[s];
        const int n = popcount(sm);
        if (n == 0) continue;
        ++non_trump_suits;
        for (CardMask m = sm; m; m &= m - 1)
            v += 0.45 * double(NUM_RANKS - rank_of(lowest(m)));
    }
    v += 1.5 * double(non_trump_suits);
    for (int r = 0; r < NUM_RANKS; ++r) {
        const int cnt = popcount(hand & RANK_MASK[r] & ~SUIT_MASK[trump]);
        if (cnt >= 2) v += 1.0 + 0.35 * double(cnt - 2);
    }
    return v;
}

CardMask visible_cards(const LocalFeatures& L) {
    return L.hand | L.table_attack | L.table_defense;
}

// H4: per-card hand quality (higher = structurally stronger hand).
double hand_quality(CardMask hand, int trump) {
    if (!hand) return 0.0;
    return hand_value(hand, trump) / double(popcount(hand));
}

// Expected quality of one random draw from the deck (memoryless split over unknown cards).
double expected_draw_quality(const LocalFeatures& L) {
    const int pool = L.deck_count + L.opponent_hand_count;
    if (L.deck_count <= 0 || pool <= 0) return hand_quality(L.hand, L.trump_suit);

    const CardMask unknown = ALL_CARDS & ~visible_cards(L);
    double sum = 0.0;
    int n = 0;
    for (int ci = 0; ci < NUM_CARDS; ++ci) {
        const Card c = Card(ci);
        if (!(unknown & card_bit(c))) continue;
        ++n;
        sum += hand_quality(L.hand | card_bit(c), L.trump_suit);
    }
    if (n == 0) return hand_quality(L.hand, L.trump_suit);
    return sum / double(pool);
}

// H5 defense: penalize beaters that drop per-card quality below expected draw benchmark.
double defense_ev_adjust(Card d, int trump, CardMask hand, double draw_q_benchmark) {
    const double after = hand_quality(hand & ~card_bit(d), trump);
    const double gap = draw_q_benchmark - after;
    if (gap <= 0.0) return 0.0;
    return 0.12 * gap;
}

// Lower is better. Trumps are heavily penalized so non-trump dumps win; the
// memory term is a small prior favoring ranks that are still mostly unseen.
double attack_value(Card c, int trump, const MemoryFeatures* mem, const OppSuitClues& clues) {
    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    v += opp_suit_attack_adjust(c, trump, clues);
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);
    return v;
}

int pick_attack_card(const LocalFeatures& L, const LegalMoves& legal, const MemoryFeatures* mem,
                     int rank_filter, bool rank_only_non_trump) {
    const OppSuitClues clues = read_opp_suit_clues(L);
    int best = -1;
    double best_v = 1e18;
    for (int i = 0; i < legal.count; ++i) {
        if (legal.moves[i].type != MoveType::AttackPlay) continue;
        const Card c = legal.moves[i].card;
        if (rank_only_non_trump && is_trump(c, L.trump_suit)) continue;
        if (rank_filter >= 0 && rank_of(c) != rank_filter) continue;
        const double v = attack_value(c, L.trump_suit, mem, clues);
        if (v < best_v) {
            best_v = v;
            best = i;
        }
    }
    return best;
}

Move choose_attack(const LocalFeatures& L, const MemoryFeatures* mem, const LegalMoves& legal,
                   bool has_done) {
    const int best = pick_attack_card(L, legal, mem, -1, false);
    if (best < 0) return {MoveType::AttackDone, NO_CARD, 0};

    // H1: initial attack — lowest non-trump; midgame prefer low pair within cap; endgame
    // skip lone singleton if a low pair exists; else trump-strip when trump-rich.
    if (!has_done) {
        const CardMask nt = L.hand & ~SUIT_MASK[L.trump_suit];
        const int mnt = nt ? rank_of(lowest(nt)) : NUM_RANKS;
        int open_rank = mnt;
        if (L.deck_count > 0) {
            for (int r = mnt; r <= mnt + 2 && r < NUM_RANKS; ++r) {
                if (popcount(L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit]) >= 2) {
                    open_rank = r;
                    break;
                }
            }
        } else if (mnt < NUM_RANKS &&
                   popcount(L.hand & RANK_MASK[mnt] & ~SUIT_MASK[L.trump_suit]) == 1) {
            for (int r = mnt + 1; r < NUM_RANKS; ++r) {
                if (popcount(L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit]) >= 2) {
                    open_rank = r;
                    break;
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
        const int open = pick_attack_card(L, legal, mem, open_rank, true);
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

    const double draw_q = expected_draw_quality(L);
    int best = -1;
    double best_c = 1e18;
    for (int i = 0; i < legal.count; ++i) {
        const Move& m = legal.moves[i];
        if (m.type != MoveType::DefendPlay) continue;
        const Card d = m.card;
        double cost = double(rank_of(d));
        if (is_trump(d, L.trump_suit)) cost += 50.0;  // prefer non-trump (rational base)
        cost += defense_ev_adjust(d, L.trump_suit, L.hand, draw_q);
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
