#include "engine.hpp"
#include "strategies.hpp"
#include "test_util.hpp"

using namespace durak;

namespace {

// Test helper: always take on defense; minimal single attack otherwise.
Move always_take(const Observation&, const LegalMoves& legal, Rng&) {
    for (int i = 0; i < legal.count; ++i)
        if (legal.moves[i].type == MoveType::DefendTake) return legal.moves[i];
    // attack: lowest card, then done
    int best = -1;
    Card bc = NO_CARD;
    for (int i = 0; i < legal.count; ++i) {
        if (legal.moves[i].type != MoveType::AttackPlay) continue;
        if (best < 0 || legal.moves[i].card < bc) { best = i; bc = legal.moves[i].card; }
    }
    if (best >= 0) return legal.moves[best];
    return {MoveType::AttackDone, NO_CARD, 0};
}

GameState empty_state(int trump_suit) {
    GameState st;
    st.trump_card = make_card(0, trump_suit);
    st.trump_suit = trump_suit;
    st.deck_count = 0;
    reset_table(st);
    return st;
}

void test_beats() {
    const int trump = 0;  // suit 0 is trump
    CHECK(beats(make_card(2, 1), make_card(1, 1), trump));    // same suit higher beats
    CHECK(!beats(make_card(1, 1), make_card(2, 1), trump));   // same suit lower fails
    CHECK(beats(make_card(0, 0), make_card(8, 1), trump));    // trump beats high non-trump
    CHECK(!beats(make_card(8, 1), make_card(0, 0), trump));   // non-trump cannot beat trump
    CHECK(beats(make_card(5, 0), make_card(3, 0), trump));    // trump vs lower trump
    CHECK(!beats(make_card(3, 2), make_card(3, 1), trump));   // different non-trump suits: no
}

void test_throw_in_ranks() {
    // Table: 7c attacked, beaten by 9c. Ranks present: 7 (rank1) and 9 (rank3).
    GameState st = empty_state(3);  // trump = spades, so clubs are non-trump
    st.atk[0] = make_card(1, 0);  // 7c
    st.def[0] = make_card(3, 0);  // 9c
    st.n_table = 1;
    st.hands[0] = card_bit(make_card(3, 1)) | card_bit(make_card(1, 2)) | card_bit(make_card(0, 1));
    LegalMoves lm = gen_attack_moves(st, 0, 6);
    bool has_9 = false, has_7 = false, has_6 = false, has_done = false;
    for (int i = 0; i < lm.count; ++i) {
        const Move& m = lm.moves[i];
        if (m.type == MoveType::AttackDone) has_done = true;
        if (m.type == MoveType::AttackPlay) {
            if (rank_of(m.card) == 3) has_9 = true;  // matches defense card rank
            if (rank_of(m.card) == 1) has_7 = true;  // matches attack card rank
            if (rank_of(m.card) == 0) has_6 = true;  // rank not on table
        }
    }
    CHECK(has_7);
    CHECK(has_9);
    CHECK(!has_6);
    CHECK(has_done);
}

void test_attack_limit() {
    GameState st = empty_state(3);
    st.atk[0] = make_card(1, 0);
    st.atk[1] = make_card(1, 1);
    st.n_table = 2;
    st.hands[0] = card_bit(make_card(1, 2));  // another 7, rank present
    LegalMoves lm = gen_attack_moves(st, 0, 2);  // limit reached
    CHECK(lm.count == 1);
    CHECK(lm.moves[0].type == MoveType::AttackDone);
}

void test_first_attacker_youngest_trump() {
    GameState st = empty_state(0);  // trump suit 0
    st.hands[0] = card_bit(make_card(5, 1));            // no trump
    st.hands[1] = card_bit(make_card(0, 0));            // 6 of trump (lowest trump)
    CHECK(first_attacker(st) == 1);

    st.hands[0] = card_bit(make_card(2, 0));            // 8 of trump
    st.hands[1] = card_bit(make_card(1, 0));            // 7 of trump (lower)
    CHECK(first_attacker(st) == 1);
}

void test_take_keeps_attacker_and_moves_cards() {
    GameState st = empty_state(3);  // spades trump
    st.attacker = 0;
    st.hands[0] = card_bit(make_card(0, 0)) | card_bit(make_card(0, 1));  // 6c, 6d
    st.hands[1] = card_bit(make_card(0, 2));  // 6h: cannot beat 6c/6d (different non-trump suits)
    Rng rng(1);
    const bool took = run_battle(st, &always_take, &always_take, rng);
    CHECK(took);
    // defender (1) picked up the attack card; limit was 1 so exactly one 6 moved.
    CHECK(popcount(st.hands[1]) == 2);
    CHECK(st.n_table == 0);
}

void test_bito_moves_to_discard() {
    GameState st = empty_state(3);  // spades trump
    st.attacker = 0;
    st.hands[0] = card_bit(make_card(0, 0));  // 6c
    st.hands[1] = card_bit(make_card(1, 0));  // 7c beats 6c
    Rng rng(1);
    const bool took = run_battle(st, &b1_basic, &b1_basic, rng);
    CHECK(!took);
    CHECK(st.discarded == (card_bit(make_card(0, 0)) | card_bit(make_card(1, 0))));
    CHECK(st.hands[0] == 0 && st.hands[1] == 0);
}

void test_terminal_conditions() {
    Rng rng(1);
    {
        GameState st = empty_state(0);
        st.deck_count = 0;
        st.hands[0] = 0;
        st.hands[1] = 0;
        CHECK(play_from_state(st, &b1_basic, &b1_basic, rng) == GameResult::Draw);
    }
    {
        GameState st = empty_state(0);
        st.deck_count = 0;
        st.hands[0] = 0;
        st.hands[1] = card_bit(make_card(5, 1));
        CHECK(play_from_state(st, &b1_basic, &b1_basic, rng) == GameResult::Player0Win);
    }
    {
        GameState st = empty_state(0);
        st.deck_count = 0;
        st.hands[0] = card_bit(make_card(5, 1));
        st.hands[1] = 0;
        CHECK(play_from_state(st, &b1_basic, &b1_basic, rng) == GameResult::Player1Win);
    }
}

void test_new_game_deal() {
    GameState st = new_game(12345);
    CHECK(popcount(st.hands[0]) == 6);
    CHECK(popcount(st.hands[1]) == 6);
    CHECK(st.deck_count == 24);
    CHECK(st.trump_card == st.deck[0]);
    // No card appears twice across hands.
    CHECK((st.hands[0] & st.hands[1]) == 0);
}

void test_deterministic_replay() {
    const GameResult a = play_game(99, &b1_basic, &b4_mem, 99);
    const GameResult b = play_game(99, &b1_basic, &b4_mem, 99);
    CHECK(a == b);
}

}  // namespace

int main() {
    test_beats();
    test_throw_in_ranks();
    test_attack_limit();
    test_first_attacker_youngest_trump();
    test_take_keeps_attacker_and_moves_cards();
    test_bito_moves_to_discard();
    test_terminal_conditions();
    test_new_game_deal();
    test_deterministic_replay();
    return durak_test::report("engine_tests");
}
