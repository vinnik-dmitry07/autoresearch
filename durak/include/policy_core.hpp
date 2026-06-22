#pragma once

#include "cards.hpp"
#include "engine.hpp"
#include "move.hpp"

// Fixed interface shared by the no-memory heuristic (B2) and its memory ablation
// (B3). The agent edits only the body of choose_move_core and the manifest in
// strategy_heuristic.cpp; this header (the signature) must not change.
namespace durak {

struct LocalFeatures {
    CardMask hand = 0;
    CardMask table_attack = 0;
    CardMask table_defense = 0;
    std::array<Card, 6> atk{};
    std::array<Card, 6> def{};
    int n_table = 0;
    int trump_suit = 0;
    Card trump_card = NO_CARD;
    int deck_count = 0;
    int opponent_hand_count = 0;
    bool is_attacker = false;
};

struct MemoryFeatures {
    CardMask unknown_cards = 0;
    int unknown_trump_count = 0;
    int unknown_rank_count[NUM_RANKS] = {0};
    int known_opponent_rank_count[NUM_RANKS] = {0};
};

// nullptr memory => no-memory mode (B2). Non-null => memory ablation (B3).
Move choose_move_core(const LocalFeatures& local, const MemoryFeatures* memory, const LegalMoves& legal);

// Manifest, reported by the harness for the Occam criterion.
const char* strategy_name();
int heuristic_count();
int parameter_count();
int complexity_score();

inline LocalFeatures make_local_features(const Observation& o) {
    LocalFeatures lf;
    lf.hand = o.hand;
    lf.table_attack = o.table_attack;
    lf.table_defense = o.table_defense;
    lf.atk = o.atk;
    lf.def = o.def;
    lf.n_table = o.n_table;
    lf.trump_suit = o.trump_suit;
    lf.trump_card = o.trump_card;
    lf.deck_count = o.deck_count;
    lf.opponent_hand_count = o.opponent_hand_count;
    lf.is_attacker = o.is_attacker;
    return lf;
}

inline MemoryFeatures make_memory_features(const MemoryView& mv) {
    MemoryFeatures mf;
    const CardMask known = mv.known_discarded | mv.known_in_own_hand | mv.known_on_table |
                           mv.known_in_opponent_hand;
    const CardMask unknown = ALL_CARDS & ~known;
    mf.unknown_cards = unknown;
    mf.unknown_trump_count = popcount(unknown & SUIT_MASK[mv.trump_suit]);
    for (int r = 0; r < NUM_RANKS; ++r) {
        mf.unknown_rank_count[r] = popcount(unknown & RANK_MASK[r]);
        mf.known_opponent_rank_count[r] = popcount(mv.known_in_opponent_hand & RANK_MASK[r]);
    }
    return mf;
}

}  // namespace durak
