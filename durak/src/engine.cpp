#include "engine.hpp"

#include <algorithm>

namespace durak {

namespace {

constexpr int MAX_BATTLES = 4000;  // safety against pathological non-termination

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
bool attack_phase(GameState& st, int A, int limit, StrategyFn s0, StrategyFn s1, Rng& rng) {
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
                break;
            }
        }
        play_attack_card(st, A, m.card);
        added = true;
    }
    return added;
}

// Defender beats every uncovered card or takes. Returns whether it took.
bool defense_phase(GameState& st, int A, int D, StrategyFn s0, StrategyFn s1, Rng& rng) {
    (void)A;
    while (true) {
        bool uncovered = false;
        for (int i = 0; i < st.n_table; ++i)
            if (st.def[i] == NO_CARD) { uncovered = true; break; }
        if (!uncovered) return false;

        LegalMoves lm = gen_defense_moves(st, D);
        Move m = ask(st, D, lm, s0, s1, rng);
        if (!move_in(lm, m)) m = lm.moves[lm.count - 1];  // last legal is always DefendTake
        if (m.type == MoveType::DefendTake) return true;
        play_defense_card(st, D, m.card, m.target);
    }
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
    const int A = st.attacker;
    const int D = 1 - A;
    reset_table(st);

    const int def_start = popcount(st.hands[D]);
    const int limit = std::min(6, def_start);
    if (limit <= 0 || st.hands[A] == 0) return false;

    attack_phase(st, A, limit, s0, s1, rng);

    bool took = false;
    while (true) {
        const bool take = defense_phase(st, A, D, s0, s1, rng);
        if (take) {
            took = true;
            attack_phase(st, A, limit, s0, s1, rng);  // pile-on while defender takes
            break;
        }
        const bool added = attack_phase(st, A, limit, s0, s1, rng);
        if (!added) break;  // all beaten, nothing more thrown in -> bito
    }

    CardMask table = 0;
    for (int i = 0; i < st.n_table; ++i) {
        table |= card_bit(st.atk[i]);
        if (st.def[i] != NO_CARD) table |= card_bit(st.def[i]);
    }
    if (took) {
        st.hands[D] |= table;
        st.known_opp[A] |= table;
        st.known_opp[D] &= ~table;
    } else {
        st.discarded |= table;
        st.known_opp[0] &= ~table;
        st.known_opp[1] &= ~table;
    }
    reset_table(st);
    return took;
}

GameResult play_from_state(GameState st, StrategyFn seat0, StrategyFn seat1, Rng& rng) {
    for (int battle = 0; battle < MAX_BATTLES; ++battle) {
        if (st.deck_count == 0) {
            const bool e0 = (st.hands[0] == 0);
            const bool e1 = (st.hands[1] == 0);
            if (e0 && e1) return GameResult::Draw;
            if (e0) return GameResult::Player0Win;
            if (e1) return GameResult::Player1Win;
        }
        const bool took = run_battle(st, seat0, seat1, rng);
        draw_to_six(st, st.attacker);
        draw_to_six(st, 1 - st.attacker);
        if (!took) st.attacker = 1 - st.attacker;
    }
    return GameResult::Draw;
}

GameResult play_game(std::uint64_t deck_seed, StrategyFn seat0, StrategyFn seat1,
                     std::uint64_t rng_seed) {
    GameState st = new_game(deck_seed);
    st.attacker = first_attacker(st);
    Rng rng(rng_seed);
    return play_from_state(st, seat0, seat1, rng);
}

}  // namespace durak
