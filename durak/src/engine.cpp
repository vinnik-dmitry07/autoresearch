#include "engine.hpp"

#include <algorithm>

namespace durak {

namespace {

constexpr int MAX_BATTLES = 4000;  // safety against pathological non-termination

int deck_phase(int deck_count) {
    if (deck_count >= 5) return 0;
    if (deck_count > 0) return 1;
    return 2;
}

void play_attack_card(GameState& st, int attacker, Card c) {
    const int defender = 1 - attacker;
    st.hands[attacker] &= ~card_bit(c);
    st.atk[st.n_table] = c;
    st.def[st.n_table] = NO_CARD;
    st.n_table += 1;
    st.known_opp[defender] &= ~card_bit(c);  // defender's belief: card left attacker's hand
}

void play_defense_card(GameState& st, int defender, Card c, int target) {
    const int attacker = 1 - defender;
    st.hands[defender] &= ~card_bit(c);
    st.def[target] = c;
    st.known_opp[attacker] &= ~card_bit(c);
}

int min_rank_or_none(CardMask cards) {
    return cards ? rank_of(lowest(cards)) : -1;
}

int max_rank_or_none(CardMask cards) {
    int max_rank = -1;
    for (CardMask t = cards; t; t &= t - 1) {
        max_rank = std::max(max_rank, rank_of(lowest(t)));
    }
    return max_rank;
}

int pair_rank_count(CardMask hand) {
    int pairs = 0;
    for (int r = 0; r < NUM_RANKS; ++r)
        if (popcount(hand & RANK_MASK[r]) >= 2) ++pairs;
    return pairs;
}

int high_trump_count(CardMask hand, int trump) {
    int count = 0;
    for (CardMask t = hand & SUIT_MASK[trump]; t; t &= t - 1) {
        if (rank_of(lowest(t)) >= 2) ++count;
    }
    return count;
}

void capture_initial_trace(const GameState& st, GameTrace& trace) {
    trace = GameTrace{};
    trace.initial_attacker = st.attacker;
    trace.trump_rank = rank_of(st.trump_card);
    trace.trump_suit = st.trump_suit;
    for (int p = 0; p < 2; ++p) {
        const CardMask trumps = st.hands[p] & SUIT_MASK[st.trump_suit];
        const CardMask non_trumps = st.hands[p] & ~SUIT_MASK[st.trump_suit];
        trace.initial_trumps[p] = popcount(trumps);
        trace.initial_high_trumps[p] = high_trump_count(st.hands[p], st.trump_suit);
        trace.initial_non_trumps[p] = popcount(non_trumps);
        trace.initial_pairs[p] = pair_rank_count(st.hands[p]);
        trace.initial_min_non_trump_rank[p] = min_rank_or_none(non_trumps);
        trace.initial_min_trump_rank[p] = min_rank_or_none(trumps);
    }
}

void finish_trace(const GameState& st, GameTrace* trace) {
    if (!trace) return;
    trace->final_deck_count = st.deck_count;
    trace->final_hand_count[0] = popcount(st.hands[0]);
    trace->final_hand_count[1] = popcount(st.hands[1]);
    for (int p = 0; p < 2; ++p) {
        const CardMask trumps = st.hands[p] & SUIT_MASK[st.trump_suit];
        const CardMask non_trumps = st.hands[p] & ~SUIT_MASK[st.trump_suit];
        trace->final_hand_mask[p] = st.hands[p];
        trace->final_trumps[p] = popcount(trumps);
        trace->final_high_trumps[p] = high_trump_count(st.hands[p], st.trump_suit);
        trace->final_non_trumps[p] = popcount(non_trumps);
        trace->final_min_trump_rank[p] = min_rank_or_none(trumps);
        trace->final_min_non_trump_rank[p] = min_rank_or_none(non_trumps);
        trace->final_max_trump_rank[p] = max_rank_or_none(trumps);
        trace->final_max_non_trump_rank[p] = max_rank_or_none(non_trumps);
    }
    trace->final_attacker = st.attacker;
}

bool all_uncovered_cards_coverable(const GameState& st, const LegalMoves& lm) {
    bool coverable[6] = {false, false, false, false, false, false};
    for (int i = 0; i < lm.count; ++i) {
        if (lm.moves[i].type == MoveType::DefendPlay) coverable[lm.moves[i].target] = true;
    }
    for (int i = 0; i < st.n_table; ++i) {
        if (st.def[i] == NO_CARD && !coverable[i]) return false;
    }
    return true;
}

Card cheapest_cover_card(const GameState& st, const LegalMoves& lm) {
    Card best = NO_CARD;
    double best_cost = 1e18;
    for (int i = 0; i < lm.count; ++i) {
        const Move& m = lm.moves[i];
        if (m.type != MoveType::DefendPlay) continue;
        const Card c = m.card;
        double cost = double(rank_of(c));
        if (suit_of(c) == st.trump_suit) cost += 50.0;
        if (cost < best_cost) {
            best_cost = cost;
            best = c;
        }
    }
    return best;
}

Card cheapest_cover_for_attack(CardMask defender_hand, Card attack, int trump_suit) {
    Card best = NO_CARD;
    double best_cost = 1e18;
    for (CardMask t = defender_hand; t; t &= t - 1) {
        const Card c = lowest(t);
        if (!beats(c, attack, trump_suit)) continue;
        double cost = double(rank_of(c));
        if (suit_of(c) == trump_suit) cost += 50.0;
        if (cost < best_cost) {
            best_cost = cost;
            best = c;
        }
    }
    return best;
}

void recompute_last_two_attack_counts(GameTrace& trace, int player) {
    trace.deck0_last_two_passes_with_trump[player] = 0;
    trace.deck0_last_two_nontrump_with_trump[player] = 0;
    trace.deck0_last_two_trump_with_trump[player] = 0;
    for (int i = 0; i < trace.deck0_last_two_attack_count[player]; ++i) {
        const int code = trace.deck0_last_two_attack_codes[player][i];
        if (code == 1)
            trace.deck0_last_two_passes_with_trump[player] += 1;
        else if (code == 2)
            trace.deck0_last_two_nontrump_with_trump[player] += 1;
        else if (code == 3)
            trace.deck0_last_two_trump_with_trump[player] += 1;
    }
}

void record_deck0_attack_decision(const GameState& st, int attacker, const LegalMoves& legal,
                                  const Move& chosen, GameTrace& trace) {
    int legal_trumps = 0;
    int legal_high_trumps = 0;
    int legal_attacks = 0;
    int legal_attack_done = 0;
    CardMask legal_attack_mask = 0;
    CardMask legal_trump_attack_mask = 0;
    CardMask legal_high_trump_attack_mask = 0;
    CardMask legal_nontrump_attack_mask = 0;
    for (int i = 0; i < legal.count; ++i) {
        const Move& m = legal.moves[i];
        if (m.type == MoveType::AttackDone) {
            legal_attack_done = 1;
            continue;
        }
        if (m.type != MoveType::AttackPlay) continue;
        ++legal_attacks;
        const CardMask bit = card_bit(m.card);
        legal_attack_mask |= bit;
        if (suit_of(m.card) == st.trump_suit) {
            ++legal_trumps;
            legal_trump_attack_mask |= bit;
            if (rank_of(m.card) >= 2) {
                ++legal_high_trumps;
                legal_high_trump_attack_mask |= bit;
            }
        } else {
            legal_nontrump_attack_mask |= bit;
        }
    }
    if (legal_attacks == 0 && chosen.type != MoveType::AttackDone) return;

    const bool holds_trump = (st.hands[attacker] & SUIT_MASK[st.trump_suit]) != 0;
    int code = 0;
    if (chosen.type == MoveType::AttackDone && holds_trump) {
        code = 1;
    } else if (chosen.type == MoveType::AttackPlay && holds_trump) {
        if (suit_of(chosen.card) == st.trump_suit)
            code = 3;
        else
            code = 2;
    }

    trace.deck0_last_decision_seen[attacker] = 1;
    trace.deck0_last_decision_battle[attacker] = trace.battles;
    trace.deck0_last_decision_code[attacker] = code;
    trace.deck0_last_decision_attack_done_available[attacker] = legal_attack_done;
    trace.deck0_last_decision_opponent_hand_count[attacker] =
        popcount(st.hands[1 - attacker]);
    trace.deck0_last_decision_chosen_rank[attacker] =
        chosen.type == MoveType::AttackPlay ? rank_of(chosen.card) : -1;
    trace.deck0_last_decision_chosen_suit[attacker] =
        chosen.type == MoveType::AttackPlay ? suit_of(chosen.card) : -1;
    trace.deck0_last_decision_chosen_is_trump[attacker] =
        chosen.type == MoveType::AttackPlay && suit_of(chosen.card) == st.trump_suit ? 1 : 0;
    trace.deck0_last_decision_hand_mask[attacker] = st.hands[attacker];
    trace.deck0_last_decision_legal_attack_mask[attacker] = legal_attack_mask;
    trace.deck0_last_decision_legal_trump_attack_mask[attacker] = legal_trump_attack_mask;
    trace.deck0_last_decision_legal_high_trump_attack_mask[attacker] =
        legal_high_trump_attack_mask;
    trace.deck0_last_decision_legal_nontrump_attack_mask[attacker] =
        legal_nontrump_attack_mask;

    const int attacker_hand_count = popcount(st.hands[attacker]);
    const int opponent_hand_count = popcount(st.hands[1 - attacker]);
    const bool tiny_high_trump_opportunity =
        legal_attack_done != 0 && attacker_hand_count <= 3 && opponent_hand_count <= 2 &&
        legal_high_trump_attack_mask != 0;
    if (tiny_high_trump_opportunity) {
        trace.deck0_tiny_high_trump_opportunities[attacker] += 1;
        trace.deck0_tiny_high_trump_legal_nontrump_options[attacker] +=
            popcount(legal_nontrump_attack_mask);
        const bool chose_high_trump =
            chosen.type == MoveType::AttackPlay && suit_of(chosen.card) == st.trump_suit &&
            rank_of(chosen.card) >= 2;
        if (chose_high_trump)
            trace.deck0_tiny_high_trump_chosen_high[attacker] += 1;
        else
            trace.deck0_tiny_high_trump_chosen_other[attacker] += 1;
        trace.deck0_tiny_high_trump_last_seen[attacker] = 1;
        trace.deck0_tiny_high_trump_last_hand_count[attacker] = attacker_hand_count;
        trace.deck0_tiny_high_trump_last_opponent_hand_count[attacker] = opponent_hand_count;
        trace.deck0_tiny_high_trump_last_chosen_rank[attacker] =
            chosen.type == MoveType::AttackPlay ? rank_of(chosen.card) : -1;
        trace.deck0_tiny_high_trump_last_chosen_suit[attacker] =
            chosen.type == MoveType::AttackPlay ? suit_of(chosen.card) : -1;
        trace.deck0_tiny_high_trump_last_chosen_is_trump[attacker] =
            chosen.type == MoveType::AttackPlay && suit_of(chosen.card) == st.trump_suit ? 1 : 0;
        trace.deck0_tiny_high_trump_last_hand_mask[attacker] = st.hands[attacker];
        trace.deck0_tiny_high_trump_last_legal_attack_mask[attacker] = legal_attack_mask;
        trace.deck0_tiny_high_trump_last_legal_high_trump_attack_mask[attacker] =
            legal_high_trump_attack_mask;
        trace.deck0_tiny_high_trump_last_legal_nontrump_attack_mask[attacker] =
            legal_nontrump_attack_mask;
    }

    if (chosen.type == MoveType::AttackPlay) {
        const int rank = rank_of(chosen.card);
        const int suit = suit_of(chosen.card);
        const int defender = 1 - attacker;
        trace.deck0_attack_play_count[attacker] += 1;
        trace.deck0_self_played_rank_mask[attacker] |= (1 << rank);
        trace.deck0_opp_played_rank_mask[defender] |= (1 << rank);

        int& play_count = trace.deck0_last_two_play_count[attacker];
        int slot = play_count;
        if (play_count < 2) {
            ++play_count;
        } else {
            trace.deck0_last_two_play_rank[attacker][0] =
                trace.deck0_last_two_play_rank[attacker][1];
            trace.deck0_last_two_play_suit[attacker][0] =
                trace.deck0_last_two_play_suit[attacker][1];
            trace.deck0_last_two_play_is_trump[attacker][0] =
                trace.deck0_last_two_play_is_trump[attacker][1];
            trace.deck0_last_two_play_opponent_hand_count[attacker][0] =
                trace.deck0_last_two_play_opponent_hand_count[attacker][1];
            trace.deck0_last_two_play_attack_done_available[attacker][0] =
                trace.deck0_last_two_play_attack_done_available[attacker][1];
            trace.deck0_last_two_play_hand_mask[attacker][0] =
                trace.deck0_last_two_play_hand_mask[attacker][1];
            trace.deck0_last_two_play_legal_attack_mask[attacker][0] =
                trace.deck0_last_two_play_legal_attack_mask[attacker][1];
            trace.deck0_last_two_play_legal_trump_attack_mask[attacker][0] =
                trace.deck0_last_two_play_legal_trump_attack_mask[attacker][1];
            trace.deck0_last_two_play_legal_high_trump_attack_mask[attacker][0] =
                trace.deck0_last_two_play_legal_high_trump_attack_mask[attacker][1];
            trace.deck0_last_two_play_legal_nontrump_attack_mask[attacker][0] =
                trace.deck0_last_two_play_legal_nontrump_attack_mask[attacker][1];
            slot = 1;
        }
        trace.deck0_last_two_play_rank[attacker][slot] = rank;
        trace.deck0_last_two_play_suit[attacker][slot] = suit;
        trace.deck0_last_two_play_is_trump[attacker][slot] =
            suit == st.trump_suit ? 1 : 0;
        trace.deck0_last_two_play_opponent_hand_count[attacker][slot] =
            opponent_hand_count;
        trace.deck0_last_two_play_attack_done_available[attacker][slot] =
            legal_attack_done;
        trace.deck0_last_two_play_hand_mask[attacker][slot] = st.hands[attacker];
        trace.deck0_last_two_play_legal_attack_mask[attacker][slot] = legal_attack_mask;
        trace.deck0_last_two_play_legal_trump_attack_mask[attacker][slot] =
            legal_trump_attack_mask;
        trace.deck0_last_two_play_legal_high_trump_attack_mask[attacker][slot] =
            legal_high_trump_attack_mask;
        trace.deck0_last_two_play_legal_nontrump_attack_mask[attacker][slot] =
            legal_nontrump_attack_mask;
    }

    trace.deck0_attack_decisions[attacker] += 1;
    trace.deck0_legal_trump_attack_options[attacker] += legal_trumps;
    trace.deck0_legal_high_trump_attack_options[attacker] += legal_high_trumps;
    if (code == 1)
        trace.deck0_attack_passes_with_trump[attacker] += 1;
    else if (code == 2)
        trace.deck0_attack_nontrump_with_trump[attacker] += 1;
    else if (code == 3)
        trace.deck0_attack_trump_with_trump[attacker] += 1;

    if (chosen.type == MoveType::AttackPlay &&
        suit_of(chosen.card) == st.trump_suit && rank_of(chosen.card) >= 2) {
        trace.deck0_high_trump_attacks[attacker] += 1;
    }

    int& count = trace.deck0_last_two_attack_count[attacker];
    if (count < 2) {
        trace.deck0_last_two_attack_codes[attacker][count] = code;
        ++count;
    } else {
        trace.deck0_last_two_attack_codes[attacker][0] =
            trace.deck0_last_two_attack_codes[attacker][1];
        trace.deck0_last_two_attack_codes[attacker][1] = code;
    }
    recompute_last_two_attack_counts(trace, attacker);
}

void note_later_deck0_trump_attack(GameTrace& trace, int attacker) {
    for (int p = 0; p < 2; ++p) {
        if (trace.first_deck0_forced_take_battle[p] < 0) continue;
        if (attacker == p)
            trace.first_deck0_forced_take_self_later_trump_attack[p] = 1;
        else
            trace.first_deck0_forced_take_opp_later_trump_attack[p] = 1;
    }
}

void record_last_deck0_attack(const GameState& st, int attacker, const LegalMoves& legal,
                              const Move& chosen, GameTrace& trace) {
    if (chosen.type != MoveType::AttackPlay) return;

    int legal_nontrumps = 0;
    int legal_trumps = 0;
    CardMask legal_attack_mask = 0;
    CardMask legal_trump_attack_mask = 0;
    CardMask legal_nontrump_attack_mask = 0;
    CardMask force_take_attack_mask = 0;
    CardMask force_high_trump_cover_attack_mask = 0;
    int chosen_forces_take = 0;
    int chosen_forces_high_trump_cover = 0;
    const int defender = 1 - attacker;
    for (int i = 0; i < legal.count; ++i) {
        const Move& m = legal.moves[i];
        if (m.type != MoveType::AttackPlay) continue;
        const CardMask bit = card_bit(m.card);
        legal_attack_mask |= bit;
        if (suit_of(m.card) == st.trump_suit) {
            ++legal_trumps;
            legal_trump_attack_mask |= bit;
        } else {
            ++legal_nontrumps;
            legal_nontrump_attack_mask |= bit;
        }

        const Card cover = cheapest_cover_for_attack(st.hands[defender], m.card, st.trump_suit);
        const bool force_take = cover == NO_CARD;
        const bool force_high_trump =
            cover != NO_CARD && suit_of(cover) == st.trump_suit && rank_of(cover) >= 2;
        if (force_take) force_take_attack_mask |= bit;
        if (force_high_trump) force_high_trump_cover_attack_mask |= bit;
        if (m.card == chosen.card) {
            chosen_forces_take = force_take ? 1 : 0;
            chosen_forces_high_trump_cover = force_high_trump ? 1 : 0;
        }
    }

    trace.last_deck0_attack_seen[attacker] = 1;
    trace.last_deck0_attack_battle[attacker] = trace.battles;
    trace.last_deck0_attack_slot[attacker] = st.n_table;
    trace.last_deck0_attack_chosen_is_trump[attacker] =
        suit_of(chosen.card) == st.trump_suit ? 1 : 0;
    trace.last_deck0_attack_chosen_rank[attacker] = rank_of(chosen.card);
    trace.last_deck0_attack_chosen_suit[attacker] = suit_of(chosen.card);
    trace.last_deck0_attack_legal_nontrumps[attacker] = legal_nontrumps;
    trace.last_deck0_attack_legal_trumps[attacker] = legal_trumps;
    trace.last_deck0_attack_legal_attack_mask[attacker] = legal_attack_mask;
    trace.last_deck0_attack_legal_trump_attack_mask[attacker] = legal_trump_attack_mask;
    trace.last_deck0_attack_legal_nontrump_attack_mask[attacker] = legal_nontrump_attack_mask;
    trace.last_deck0_attack_legal_force_take_attack_mask[attacker] = force_take_attack_mask;
    trace.last_deck0_attack_legal_force_high_trump_cover_attack_mask[attacker] =
        force_high_trump_cover_attack_mask;
    trace.last_deck0_attack_chosen_forces_take[attacker] = chosen_forces_take;
    trace.last_deck0_attack_chosen_forces_high_trump_cover[attacker] =
        chosen_forces_high_trump_cover;
    trace.last_deck0_attack_attacker_hand_count[attacker] = popcount(st.hands[attacker]);
    trace.last_deck0_attack_defender_hand_count[attacker] = popcount(st.hands[defender]);
    trace.last_deck0_attack_attacker_trumps[attacker] =
        popcount(st.hands[attacker] & SUIT_MASK[st.trump_suit]);
    trace.last_deck0_attack_defender_trumps[attacker] =
        popcount(st.hands[defender] & SUIT_MASK[st.trump_suit]);
    trace.last_deck0_attack_defender_high_trumps[attacker] =
        high_trump_count(st.hands[defender], st.trump_suit);
    trace.last_deck0_attack_covered[attacker] = 0;
    trace.last_deck0_attack_cover_is_trump[attacker] = 0;
    trace.last_deck0_attack_cover_same_rank[attacker] = 0;
    trace.last_deck0_attack_cover_rank[attacker] = -1;
    trace.last_deck0_attack_defender_trumps_after_cover[attacker] =
        trace.last_deck0_attack_defender_trumps[attacker];
    trace.last_deck0_attack_defender_high_trumps_after_cover[attacker] =
        trace.last_deck0_attack_defender_high_trumps[attacker];
    trace.last_deck0_attack_tracking_after_cover[attacker] = 0;
    trace.last_deck0_attack_self_attack_cards_after_cover[attacker] = 0;
    trace.last_deck0_attack_self_legal_trump_options_after_cover[attacker] = 0;
    trace.last_deck0_attack_self_trump_attacks_after_cover[attacker] = 0;
    trace.last_deck0_attack_opp_attack_cards_after_cover[attacker] = 0;
    trace.last_deck0_attack_opp_trump_attacks_after_cover[attacker] = 0;
    trace.last_deck0_attack_opp_high_trump_attacks_after_cover[attacker] = 0;
}

void record_last_deck0_attack_cover(const GameState& st, int attacker, int defender, const Move& cover,
                                    GameTrace& trace) {
    if (trace.last_deck0_attack_seen[attacker] == 0) return;
    if (trace.last_deck0_attack_slot[attacker] != int(cover.target)) return;

    const Card c = cover.card;
    trace.last_deck0_attack_covered[attacker] = 1;
    trace.last_deck0_attack_cover_is_trump[attacker] =
        suit_of(c) == st.trump_suit ? 1 : 0;
    trace.last_deck0_attack_cover_same_rank[attacker] =
        rank_of(c) == trace.last_deck0_attack_chosen_rank[attacker] ? 1 : 0;
    trace.last_deck0_attack_cover_rank[attacker] = rank_of(c);
    const CardMask after = st.hands[defender] & ~card_bit(c);
    trace.last_deck0_attack_defender_trumps_after_cover[attacker] =
        popcount(after & SUIT_MASK[st.trump_suit]);
    trace.last_deck0_attack_defender_high_trumps_after_cover[attacker] =
        high_trump_count(after, st.trump_suit);
    trace.last_deck0_attack_tracking_after_cover[attacker] = 1;
}

void record_post_prior_cover_attack(const GameState& st, int attacker, const LegalMoves& legal,
                                    const Move& chosen, GameTrace& trace) {
    if (chosen.type != MoveType::AttackPlay) return;

    int legal_trumps = 0;
    for (int i = 0; i < legal.count; ++i) {
        const Move& m = legal.moves[i];
        if (m.type == MoveType::AttackPlay && suit_of(m.card) == st.trump_suit)
            ++legal_trumps;
    }

    for (int p = 0; p < 2; ++p) {
        if (trace.first_deck0_forced_take_battle[p] >= 0) continue;
        if (trace.last_deck0_attack_tracking_after_cover[p] == 0) continue;

        const bool self = attacker == p;
        if (self) {
            trace.last_deck0_attack_self_attack_cards_after_cover[p] += 1;
            trace.last_deck0_attack_self_legal_trump_options_after_cover[p] += legal_trumps;
            if (suit_of(chosen.card) == st.trump_suit)
                trace.last_deck0_attack_self_trump_attacks_after_cover[p] += 1;
        } else {
            trace.last_deck0_attack_opp_attack_cards_after_cover[p] += 1;
            if (suit_of(chosen.card) == st.trump_suit) {
                trace.last_deck0_attack_opp_trump_attacks_after_cover[p] += 1;
                if (rank_of(chosen.card) >= 2)
                    trace.last_deck0_attack_opp_high_trump_attacks_after_cover[p] += 1;
            }
        }
    }
}

void record_first_deck0_forced_take(const GameState& st, int attacker, int defender, int limit,
                                    const LegalMoves& defense_legal, GameTrace& trace) {
    if (trace.first_deck0_forced_take_battle[defender] >= 0) return;

    int table_cards = 0;
    int uncovered = 0;
    int attack_cards = 0;
    int defense_cards = 0;
    int trump_attacks = 0;
    int trump_defenses = 0;
    int min_attack_rank = NUM_RANKS;
    int max_attack_rank = -1;
    CardMask attack_mask = 0;
    CardMask defense_mask = 0;
    for (int i = 0; i < st.n_table; ++i) {
        const Card a = st.atk[i];
        if (a != NO_CARD) {
            ++table_cards;
            ++attack_cards;
            attack_mask |= card_bit(a);
            if (suit_of(a) == st.trump_suit) ++trump_attacks;
            min_attack_rank = std::min(min_attack_rank, rank_of(a));
            max_attack_rank = std::max(max_attack_rank, rank_of(a));
        }
        const Card d = st.def[i];
        if (d == NO_CARD) {
            ++uncovered;
        } else {
            ++table_cards;
            ++defense_cards;
            defense_mask |= card_bit(d);
            if (suit_of(d) == st.trump_suit) ++trump_defenses;
        }
    }

    bool coverable[6] = {false, false, false, false, false, false};
    CardMask legal_defense_mask = 0;
    int legal_defense_cards = 0;
    int legal_trump_defenses = 0;
    int legal_nontrump_defenses = 0;
    for (int i = 0; i < defense_legal.count; ++i) {
        const Move& m = defense_legal.moves[i];
        if (m.type != MoveType::DefendPlay) continue;
        coverable[m.target] = true;
        legal_defense_mask |= card_bit(m.card);
        ++legal_defense_cards;
        if (suit_of(m.card) == st.trump_suit)
            ++legal_trump_defenses;
        else
            ++legal_nontrump_defenses;
    }

    int coverable_uncovered = 0;
    int uncoverable_uncovered = 0;
    for (int i = 0; i < st.n_table; ++i) {
        if (st.def[i] != NO_CARD) continue;
        if (coverable[i])
            ++coverable_uncovered;
        else
            ++uncoverable_uncovered;
    }

    int nontrump_throwins = 0;
    int trump_throwins = 0;
    const LegalMoves pile = gen_attack_moves(st, attacker, limit);
    for (int i = 0; i < pile.count; ++i) {
        const Move& m = pile.moves[i];
        if (m.type != MoveType::AttackPlay) continue;
        if (suit_of(m.card) == st.trump_suit)
            ++trump_throwins;
        else
            ++nontrump_throwins;
    }

    trace.first_deck0_forced_take_battle[defender] = trace.battles;
    trace.first_deck0_forced_take_attacker[defender] = attacker;
    trace.first_deck0_forced_take_table_cards[defender] = table_cards;
    trace.first_deck0_forced_take_uncovered[defender] = uncovered;
    trace.first_deck0_forced_take_attack_cards[defender] = attack_cards;
    trace.first_deck0_forced_take_defense_cards[defender] = defense_cards;
    trace.first_deck0_forced_take_trump_attacks[defender] = trump_attacks;
    trace.first_deck0_forced_take_trump_defenses[defender] = trump_defenses;
    trace.first_deck0_forced_take_min_attack_rank[defender] =
        (min_attack_rank == NUM_RANKS) ? -1 : min_attack_rank;
    trace.first_deck0_forced_take_max_attack_rank[defender] = max_attack_rank;
    trace.first_deck0_forced_take_defender_hand_count[defender] = popcount(st.hands[defender]);
    trace.first_deck0_forced_take_attacker_hand_count[defender] = popcount(st.hands[attacker]);
    trace.first_deck0_forced_take_defender_trumps[defender] =
        popcount(st.hands[defender] & SUIT_MASK[st.trump_suit]);
    trace.first_deck0_forced_take_attacker_trumps[defender] =
        popcount(st.hands[attacker] & SUIT_MASK[st.trump_suit]);
    trace.first_deck0_forced_take_defender_high_trumps[defender] =
        high_trump_count(st.hands[defender], st.trump_suit);
    trace.first_deck0_forced_take_attacker_high_trumps[defender] =
        high_trump_count(st.hands[attacker], st.trump_suit);
    trace.first_deck0_forced_take_attacker_nontrump_throwins[defender] = nontrump_throwins;
    trace.first_deck0_forced_take_attacker_trump_throwins[defender] = trump_throwins;
    trace.first_deck0_forced_take_attack_mask[defender] = attack_mask;
    trace.first_deck0_forced_take_defense_mask[defender] = defense_mask;
    trace.first_deck0_forced_take_defender_hand_mask[defender] = st.hands[defender];
    trace.first_deck0_forced_take_legal_defense_mask[defender] = legal_defense_mask;
    trace.first_deck0_forced_take_legal_defense_cards[defender] = legal_defense_cards;
    trace.first_deck0_forced_take_legal_trump_defenses[defender] = legal_trump_defenses;
    trace.first_deck0_forced_take_legal_nontrump_defenses[defender] = legal_nontrump_defenses;
    trace.first_deck0_forced_take_coverable_uncovered[defender] = coverable_uncovered;
    trace.first_deck0_forced_take_uncoverable_uncovered[defender] = uncoverable_uncovered;
    const Card cheapest = cheapest_cover_card(st, defense_legal);
    trace.first_deck0_forced_take_cheapest_cover_rank[defender] =
        cheapest == NO_CARD ? -1 : rank_of(cheapest);
    trace.first_deck0_forced_take_cheapest_cover_is_trump[defender] =
        cheapest != NO_CARD && suit_of(cheapest) == st.trump_suit ? 1 : 0;

    trace.first_deck0_forced_take_prior_attack_seen[defender] =
        trace.last_deck0_attack_seen[defender];
    trace.first_deck0_forced_take_prior_attack_battle[defender] =
        trace.last_deck0_attack_battle[defender];
    trace.first_deck0_forced_take_prior_attack_chosen_is_trump[defender] =
        trace.last_deck0_attack_chosen_is_trump[defender];
    trace.first_deck0_forced_take_prior_attack_chosen_rank[defender] =
        trace.last_deck0_attack_chosen_rank[defender];
    trace.first_deck0_forced_take_prior_attack_chosen_suit[defender] =
        trace.last_deck0_attack_chosen_suit[defender];
    trace.first_deck0_forced_take_prior_attack_legal_nontrumps[defender] =
        trace.last_deck0_attack_legal_nontrumps[defender];
    trace.first_deck0_forced_take_prior_attack_legal_trumps[defender] =
        trace.last_deck0_attack_legal_trumps[defender];
    trace.first_deck0_forced_take_prior_attack_legal_attack_mask[defender] =
        trace.last_deck0_attack_legal_attack_mask[defender];
    trace.first_deck0_forced_take_prior_attack_legal_trump_attack_mask[defender] =
        trace.last_deck0_attack_legal_trump_attack_mask[defender];
    trace.first_deck0_forced_take_prior_attack_legal_nontrump_attack_mask[defender] =
        trace.last_deck0_attack_legal_nontrump_attack_mask[defender];
    trace.first_deck0_forced_take_prior_attack_legal_force_take_attack_mask[defender] =
        trace.last_deck0_attack_legal_force_take_attack_mask[defender];
    trace.first_deck0_forced_take_prior_attack_legal_force_high_trump_cover_attack_mask[defender] =
        trace.last_deck0_attack_legal_force_high_trump_cover_attack_mask[defender];
    trace.first_deck0_forced_take_prior_attack_chosen_forces_take[defender] =
        trace.last_deck0_attack_chosen_forces_take[defender];
    trace.first_deck0_forced_take_prior_attack_chosen_forces_high_trump_cover[defender] =
        trace.last_deck0_attack_chosen_forces_high_trump_cover[defender];
    trace.first_deck0_forced_take_prior_attack_attacker_hand_count[defender] =
        trace.last_deck0_attack_attacker_hand_count[defender];
    trace.first_deck0_forced_take_prior_attack_defender_hand_count[defender] =
        trace.last_deck0_attack_defender_hand_count[defender];
    trace.first_deck0_forced_take_prior_attack_attacker_trumps[defender] =
        trace.last_deck0_attack_attacker_trumps[defender];
    trace.first_deck0_forced_take_prior_attack_defender_trumps[defender] =
        trace.last_deck0_attack_defender_trumps[defender];
    trace.first_deck0_forced_take_prior_attack_defender_high_trumps[defender] =
        trace.last_deck0_attack_defender_high_trumps[defender];
    trace.first_deck0_forced_take_prior_attack_covered[defender] =
        trace.last_deck0_attack_covered[defender];
    trace.first_deck0_forced_take_prior_attack_cover_is_trump[defender] =
        trace.last_deck0_attack_cover_is_trump[defender];
    trace.first_deck0_forced_take_prior_attack_cover_same_rank[defender] =
        trace.last_deck0_attack_cover_same_rank[defender];
    trace.first_deck0_forced_take_prior_attack_cover_rank[defender] =
        trace.last_deck0_attack_cover_rank[defender];
    trace.first_deck0_forced_take_prior_attack_defender_trumps_after_cover[defender] =
        trace.last_deck0_attack_defender_trumps_after_cover[defender];
    trace.first_deck0_forced_take_prior_attack_defender_high_trumps_after_cover[defender] =
        trace.last_deck0_attack_defender_high_trumps_after_cover[defender];
    trace.first_deck0_forced_take_prior_attack_battles_until_forced_take[defender] =
        trace.last_deck0_attack_battle[defender] >= 0
            ? trace.battles - trace.last_deck0_attack_battle[defender]
            : -1;
    trace.first_deck0_forced_take_prior_attack_self_attack_cards_after_cover[defender] =
        trace.last_deck0_attack_self_attack_cards_after_cover[defender];
    trace.first_deck0_forced_take_prior_attack_self_legal_trump_options_after_cover[defender] =
        trace.last_deck0_attack_self_legal_trump_options_after_cover[defender];
    trace.first_deck0_forced_take_prior_attack_self_trump_attacks_after_cover[defender] =
        trace.last_deck0_attack_self_trump_attacks_after_cover[defender];
    trace.first_deck0_forced_take_prior_attack_opp_attack_cards_after_cover[defender] =
        trace.last_deck0_attack_opp_attack_cards_after_cover[defender];
    trace.first_deck0_forced_take_prior_attack_opp_trump_attacks_after_cover[defender] =
        trace.last_deck0_attack_opp_trump_attacks_after_cover[defender];
    trace.first_deck0_forced_take_prior_attack_opp_high_trump_attacks_after_cover[defender] =
        trace.last_deck0_attack_opp_high_trump_attacks_after_cover[defender];
}

Move ask(GameState& st, int p, const LegalMoves& lm, StrategyFn seat0, StrategyFn seat1, Rng& rng) {
    CardMask ta = 0, td = 0;
    for (int i = 0; i < st.n_table; ++i) {
        ta |= card_bit(st.atk[i]);
        if (st.def[i] != NO_CARD) td |= card_bit(st.def[i]);
    }
    const int opp_count = popcount(st.hands[1 - p]);

    MemoryView mv;
    mv.known_discarded = st.discarded;
    mv.known_in_own_hand = st.hands[p];
    mv.known_on_table = ta | td;
    mv.known_in_opponent_hand = st.known_opp[p];
    mv.seen_ever = mv.known_discarded | mv.known_on_table | mv.known_in_own_hand |
                   mv.known_in_opponent_hand;
    mv.deck_count = st.deck_count;
    mv.opponent_hand_count = opp_count;
    mv.trump_suit = st.trump_suit;
    mv.trump_card = st.trump_card;

    Observation o;
    o.hand = st.hands[p];
    o.table_attack = ta;
    o.table_defense = td;
    o.atk = st.atk;
    o.def = st.def;
    o.n_table = st.n_table;
    o.trump_suit = st.trump_suit;
    o.trump_card = st.trump_card;
    o.deck_count = st.deck_count;
    o.opponent_hand_count = opp_count;
    o.is_attacker = (p == st.attacker);
    o.memory = &mv;

    StrategyFn fn = (p == 0) ? seat0 : seat1;
    return fn(o, lm, rng);
}

bool move_in(const LegalMoves& lm, const Move& m) {
    for (int i = 0; i < lm.count; ++i) {
        const Move& l = lm.moves[i];
        if (l.type == m.type && l.card == m.card && l.target == m.target) return true;
    }
    return false;
}

// Attacker adds cards until it declares done (or can no longer act).
// Returns whether at least one card was added.
bool attack_phase(GameState& st, int A, int limit, StrategyFn s0, StrategyFn s1, Rng& rng,
                  GameTrace* trace, int phase) {
    bool added = false;
    while (true) {
        LegalMoves lm = gen_attack_moves(st, A, limit);
        if (lm.count == 0) break;
        Move m = ask(st, A, lm, s0, s1, rng);
        if (!move_in(lm, m)) {
            // Defensive fallback: pick the first legal move.
            m = lm.moves[0];
        }
        if (m.type == MoveType::AttackDone) {
            if (st.n_table == 0) {  // an empty attack is illegal; force a play
                m = lm.moves[0];
            } else {
                if (trace && phase == 2) record_deck0_attack_decision(st, A, lm, m, *trace);
                break;
            }
        }
        if (trace) {
            if (phase == 2) record_deck0_attack_decision(st, A, lm, m, *trace);
            if (phase == 2) record_post_prior_cover_attack(st, A, lm, m, *trace);
            if (phase == 2) record_last_deck0_attack(st, A, lm, m, *trace);
        }
        play_attack_card(st, A, m.card);
        if (trace) {
            trace->attack_cards[A] += 1;
            if (suit_of(m.card) == st.trump_suit) {
                trace->trump_attack_cards[A] += 1;
                trace->trump_attack_cards_by_phase[A][phase] += 1;
                if (phase == 2) note_later_deck0_trump_attack(*trace, A);
            }
        }
        added = true;
    }
    return added;
}

// Defender beats every uncovered card or takes. Returns whether it took.
bool defense_phase(GameState& st, int A, int D, int limit, StrategyFn s0, StrategyFn s1,
                   Rng& rng, GameTrace* trace, int phase) {
    (void)A;
    while (true) {
        bool uncovered = false;
        for (int i = 0; i < st.n_table; ++i)
            if (st.def[i] == NO_CARD) { uncovered = true; break; }
        if (!uncovered) return false;

        LegalMoves lm = gen_defense_moves(st, D);
        Move m = ask(st, D, lm, s0, s1, rng);
        if (!move_in(lm, m)) m = lm.moves[lm.count - 1];  // last legal is always DefendTake
        if (m.type == MoveType::DefendTake) {
            if (trace) {
                trace->takes[D] += 1;
                const bool voluntary = all_uncovered_cards_coverable(st, lm);
                if (voluntary) {
                    trace->voluntary_takes[D] += 1;
                    trace->voluntary_takes_by_phase[D][phase] += 1;
                    const Card c = cheapest_cover_card(st, lm);
                    if (c != NO_CARD && suit_of(c) == st.trump_suit) {
                        trace->voluntary_take_min_cover_trump[D] += 1;
                        if (rank_of(c) >= 2 && st.deck_count >= 5)
                            trace->voluntary_take_high_trump_deck_ge5[D] += 1;
                    }
                } else {
                    trace->forced_takes[D] += 1;
                    trace->forced_takes_by_phase[D][phase] += 1;
                    if (phase == 2) record_first_deck0_forced_take(st, A, D, limit, lm, *trace);
                }
            }
            return true;
        }
        if (trace) {
            if (phase == 2) record_last_deck0_attack_cover(st, A, D, m, *trace);
        }
        play_defense_card(st, D, m.card, m.target);
        if (trace) {
            trace->defense_cards[D] += 1;
            if (suit_of(m.card) == st.trump_suit) trace->trump_defense_cards[D] += 1;
        }
    }
}

bool run_battle_impl(GameState& st, StrategyFn s0, StrategyFn s1, Rng& rng, GameTrace* trace) {
    const int A = st.attacker;
    const int D = 1 - A;
    const int phase = deck_phase(st.deck_count);
    reset_table(st);

    const int def_start = popcount(st.hands[D]);
    const int limit = std::min(6, def_start);
    if (limit <= 0 || st.hands[A] == 0) return false;

    if (trace) {
        trace->battles += 1;
        trace->attacks_started[A] += 1;
    }
    attack_phase(st, A, limit, s0, s1, rng, trace, phase);

    bool took = false;
    while (true) {
        const bool take = defense_phase(st, A, D, limit, s0, s1, rng, trace, phase);
        if (take) {
            took = true;
            attack_phase(st, A, limit, s0, s1, rng, trace, phase);  // pile-on while defender takes
            break;
        }
        const bool added = attack_phase(st, A, limit, s0, s1, rng, trace, phase);
        if (!added) break;  // all beaten, nothing more thrown in -> bito
    }

    CardMask table = 0;
    for (int i = 0; i < st.n_table; ++i) {
        table |= card_bit(st.atk[i]);
        if (st.def[i] != NO_CARD) table |= card_bit(st.def[i]);
    }
    const int table_cards = popcount(table);
    if (trace) {
        trace->max_table_cards = std::max(trace->max_table_cards, table_cards);
        trace->table_cards_total += table_cards;
    }
    if (took) {
        st.hands[D] |= table;
        st.known_opp[A] |= table;
        st.known_opp[D] &= ~table;
        if (trace) {
            trace->cards_taken[D] += table_cards;
            trace->cards_taken_by_phase[D][phase] += table_cards;
            trace->max_cards_taken = std::max(trace->max_cards_taken, table_cards);
        }
    } else {
        st.discarded |= table;
        st.known_opp[0] &= ~table;
        st.known_opp[1] &= ~table;
        if (trace) {
            trace->successful_defenses[D] += 1;
            trace->successful_defenses_by_phase[D][phase] += 1;
            trace->discarded_cards += table_cards;
        }
    }
    reset_table(st);
    return took;
}

GameResult play_from_state_impl(GameState st, StrategyFn seat0, StrategyFn seat1, Rng& rng,
                                GameTrace* trace) {
    for (int battle = 0; battle < MAX_BATTLES; ++battle) {
        if (st.deck_count == 0) {
            const bool e0 = (st.hands[0] == 0);
            const bool e1 = (st.hands[1] == 0);
            if (e0 && e1) {
                finish_trace(st, trace);
                return GameResult::Draw;
            }
            if (e0) {
                finish_trace(st, trace);
                return GameResult::Player0Win;
            }
            if (e1) {
                finish_trace(st, trace);
                return GameResult::Player1Win;
            }
        }
        const bool took = run_battle_impl(st, seat0, seat1, rng, trace);
        const int first_draw = st.attacker;
        const int second_draw = 1 - st.attacker;
        const int first_before = popcount(st.hands[first_draw]);
        draw_to_six(st, first_draw);
        const int second_before = popcount(st.hands[second_draw]);
        draw_to_six(st, second_draw);
        if (trace) {
            trace->draws[first_draw] += popcount(st.hands[first_draw]) - first_before;
            trace->draws[second_draw] += popcount(st.hands[second_draw]) - second_before;
            if (st.deck_count == 0 && trace->deck_empty_after_battle < 0)
                trace->deck_empty_after_battle = trace->battles;
        }
        if (!took) st.attacker = 1 - st.attacker;
    }
    finish_trace(st, trace);
    return GameResult::Draw;
}

}  // namespace

void reset_table(GameState& st) {
    st.n_table = 0;
    st.atk.fill(NO_CARD);
    st.def.fill(NO_CARD);
}

LegalMoves gen_attack_moves(const GameState& st, int attacker, int limit) {
    LegalMoves lm;
    const CardMask hand = st.hands[attacker];
    if (st.n_table < limit) {
        if (st.n_table == 0) {
            for (CardMask t = hand; t; t &= t - 1) lm.add({MoveType::AttackPlay, lowest(t), 0});
        } else {
            bool rank_present[NUM_RANKS] = {false};
            for (int i = 0; i < st.n_table; ++i) {
                rank_present[rank_of(st.atk[i])] = true;
                if (st.def[i] != NO_CARD) rank_present[rank_of(st.def[i])] = true;
            }
            for (CardMask t = hand; t; t &= t - 1) {
                const Card c = lowest(t);
                if (rank_present[rank_of(c)]) lm.add({MoveType::AttackPlay, c, 0});
            }
        }
    }
    if (st.n_table > 0) lm.add({MoveType::AttackDone, NO_CARD, 0});
    return lm;
}

LegalMoves gen_defense_moves(const GameState& st, int defender) {
    LegalMoves lm;
    const CardMask hand = st.hands[defender];
    for (int i = 0; i < st.n_table; ++i) {
        if (st.def[i] != NO_CARD) continue;
        const Card a = st.atk[i];
        for (CardMask t = hand; t; t &= t - 1) {
            const Card d = lowest(t);
            if (beats(d, a, st.trump_suit))
                lm.add({MoveType::DefendPlay, d, std::uint8_t(i)});
        }
    }
    lm.add({MoveType::DefendTake, NO_CARD, 0});
    return lm;
}

int first_attacker(const GameState& st) {
    const CardMask trumps = (st.hands[0] | st.hands[1]) & SUIT_MASK[st.trump_suit];
    if (trumps) {
        const Card low = lowest(trumps);
        return (st.hands[0] & card_bit(low)) ? 0 : 1;
    }
    return 0;
}

void draw_to_six(GameState& st, int player) {
    while (popcount(st.hands[player]) < 6 && st.deck_count > 0) {
        const Card c = st.deck[st.deck_count - 1];
        st.deck_count -= 1;
        st.hands[player] |= card_bit(c);
    }
}

GameState new_game(std::uint64_t deck_seed) {
    GameState st;
    for (int i = 0; i < NUM_CARDS; ++i) st.deck[i] = Card(i);

    Rng rng(deck_seed ? deck_seed : 1);
    for (int i = NUM_CARDS - 1; i > 0; --i) {
        const int j = int(rng.bounded(std::uint32_t(i + 1)));
        std::swap(st.deck[i], st.deck[j]);
    }

    st.trump_card = st.deck[0];
    st.trump_suit = suit_of(st.trump_card);
    st.deck_count = NUM_CARDS;
    reset_table(st);

    // Deal 6 + 6 from the top of the deck.
    for (int k = 0; k < 6; ++k) {
        st.hands[0] |= card_bit(st.deck[st.deck_count - 1]);
        st.deck_count -= 1;
    }
    for (int k = 0; k < 6; ++k) {
        st.hands[1] |= card_bit(st.deck[st.deck_count - 1]);
        st.deck_count -= 1;
    }
    return st;
}

bool run_battle(GameState& st, StrategyFn s0, StrategyFn s1, Rng& rng) {
    return run_battle_impl(st, s0, s1, rng, nullptr);
}

GameResult play_from_state(GameState st, StrategyFn seat0, StrategyFn seat1, Rng& rng) {
    return play_from_state_impl(st, seat0, seat1, rng, nullptr);
}

GameResult play_game(std::uint64_t deck_seed, StrategyFn seat0, StrategyFn seat1,
                     std::uint64_t rng_seed) {
    GameState st = new_game(deck_seed);
    st.attacker = first_attacker(st);
    Rng rng(rng_seed);
    return play_from_state(st, seat0, seat1, rng);
}

GameResult play_game_traced(std::uint64_t deck_seed, StrategyFn seat0, StrategyFn seat1,
                            std::uint64_t rng_seed, GameTrace& trace) {
    GameState st = new_game(deck_seed);
    st.attacker = first_attacker(st);
    capture_initial_trace(st, trace);
    Rng rng(rng_seed);
    return play_from_state_impl(st, seat0, seat1, rng, &trace);
}

}  // namespace durak
