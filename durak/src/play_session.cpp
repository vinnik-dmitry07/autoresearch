#include "play_session.hpp"

#include "play_ui.hpp"
#include "strategies.hpp"

#include <algorithm>
#include <sstream>

namespace durak {

namespace {

constexpr int MAX_BATTLES = 4000;

}  // namespace

void PlaySession::new_game(std::uint64_t seed, int human_seat) {
    human_ = human_seat & 1;
    st_ = durak::new_game(seed);
    st_.attacker = first_attacker(st_);
    rng_ = Rng(seed ? seed + 1 : 1);
    in_battle_ = false;
    battle_took_ = false;
    step_ = Step::BetweenBattles;
    waiting_human_ = false;
    result_.reset();
    log_.clear();
    log_.push_back("New game vs B2 heuristic agent.");
    pump();
}

Observation PlaySession::build_obs(int player) const {
    CardMask ta = 0, td = 0;
    for (int i = 0; i < st_.n_table; ++i) {
        ta |= card_bit(st_.atk[i]);
        if (st_.def[i] != NO_CARD) td |= card_bit(st_.def[i]);
    }
    const int opp_count = popcount(st_.hands[1 - player]);

    Observation o;
    o.hand = st_.hands[player];
    o.table_attack = ta;
    o.table_defense = td;
    o.atk = st_.atk;
    o.def = st_.def;
    o.n_table = st_.n_table;
    o.trump_suit = st_.trump_suit;
    o.trump_card = st_.trump_card;
    o.deck_count = st_.deck_count;
    o.opponent_hand_count = opp_count;
    o.is_attacker = (player == st_.attacker);
    o.memory = nullptr;
    return o;
}

bool PlaySession::move_in(const LegalMoves& lm, const Move& m) const {
    for (int i = 0; i < lm.count; ++i) {
        const Move& l = lm.moves[i];
        if (l.type == m.type && l.card == m.card && l.target == m.target) return true;
    }
    return false;
}

void PlaySession::play_attack_card(int attacker, Card c) {
    const int defender = 1 - attacker;
    st_.hands[attacker] &= ~card_bit(c);
    st_.atk[st_.n_table] = c;
    st_.def[st_.n_table] = NO_CARD;
    st_.n_table += 1;
    st_.known_opp[defender] &= ~card_bit(c);
}

void PlaySession::play_defense_card(int defender, Card c, int target) {
    const int attacker = 1 - defender;
    st_.hands[defender] &= ~card_bit(c);
    st_.def[target] = c;
    st_.known_opp[attacker] &= ~card_bit(c);
}

void PlaySession::start_battle() {
    reset_table(st_);
    const int D = 1 - st_.attacker;
    battle_limit_ = std::min(6, popcount(st_.hands[D]));
    battle_took_ = false;
    in_battle_ = true;
    step_ = Step::Attack;
    if (battle_limit_ <= 0 || st_.hands[st_.attacker] == 0) {
        in_battle_ = false;
        step_ = Step::BetweenBattles;
    }
}

void PlaySession::finish_battle(bool took) {
    CardMask table = 0;
    for (int i = 0; i < st_.n_table; ++i) {
        table |= card_bit(st_.atk[i]);
        if (st_.def[i] != NO_CARD) table |= card_bit(st_.def[i]);
    }
    const int D = 1 - st_.attacker;
    if (took) {
        st_.hands[D] |= table;
        st_.known_opp[st_.attacker] |= table;
        st_.known_opp[D] &= ~table;
        push_log("Defender took the table.");
    } else {
        st_.discarded |= table;
        st_.known_opp[0] &= ~table;
        st_.known_opp[1] &= ~table;
        push_log("Defense successful (bito).");
    }
    reset_table(st_);
    in_battle_ = false;
    step_ = Step::BetweenBattles;
    draw_to_six(st_, st_.attacker);
    draw_to_six(st_, 1 - st_.attacker);
    if (!took) st_.attacker = 1 - st_.attacker;
}

std::optional<GameResult> PlaySession::check_game_over() const {
    if (st_.deck_count > 0) return std::nullopt;
    const bool e0 = (st_.hands[0] == 0);
    const bool e1 = (st_.hands[1] == 0);
    if (e0 && e1) return GameResult::Draw;
    if (e0) return GameResult::Player0Win;
    if (e1) return GameResult::Player1Win;
    return std::nullopt;
}

Move PlaySession::ai_move(const Observation& o, const LegalMoves& lm) {
    const Move m = b2_heuristic(o, lm, rng_);
    push_log(std::string("AI: ") + move_label(m, o));
    return m;
}

void PlaySession::push_log(const std::string& line) { log_.push_back(line); }

bool PlaySession::step_once() {
    if (result_) return false;

    if (!in_battle_) {
        if (auto over = check_game_over()) {
            result_ = *over;
            if (*over == GameResult::Draw) push_log("Draw.");
            else if ((*over == GameResult::Player0Win) == (human_ == 0)) push_log("You win!");
            else push_log("AI wins — you are durak.");
            return false;
        }
        start_battle();
        if (!in_battle_) return true;
    }

    const int A = st_.attacker;
    const int D = 1 - A;

    if (step_ == Step::Attack) {
        LegalMoves lm = gen_attack_moves(st_, A, battle_limit_);
        if (lm.count == 0) {
            step_ = Step::Defend;
            return true;
        }
        const Observation o = build_obs(A);
        Move m{};
        if (A == human_) {
            human_legal_ = lm;
            human_obs_ = o;
            waiting_human_ = true;
            return false;
        }
        m = ai_move(o, lm);
        if (!move_in(lm, m)) m = lm.moves[0];
        if (m.type == MoveType::AttackDone) {
            if (st_.n_table == 0) m = lm.moves[0];
            else {
                step_ = Step::Defend;
                return true;
            }
        }
        play_attack_card(A, m.card);
        return true;
    }

    if (step_ == Step::Defend) {
        bool uncovered = false;
        for (int i = 0; i < st_.n_table; ++i)
            if (st_.def[i] == NO_CARD) { uncovered = true; break; }
        if (!uncovered) {
            finish_battle(false);
            return true;
        }

        LegalMoves lm = gen_defense_moves(st_, D);
        const Observation o = build_obs(D);
        Move m{};
        if (D == human_) {
            human_legal_ = lm;
            human_obs_ = o;
            waiting_human_ = true;
            return false;
        }
        m = ai_move(o, lm);
        if (!move_in(lm, m)) m = lm.moves[lm.count - 1];
        if (m.type == MoveType::DefendTake) {
            battle_took_ = true;
            LegalMoves alm = gen_attack_moves(st_, A, battle_limit_);
            while (alm.count > 0) {
                const Observation ao = build_obs(A);
                Move am{};
                if (A == human_) {
                    human_legal_ = alm;
                    human_obs_ = ao;
                    waiting_human_ = true;
                    step_ = Step::FinishBattle;
                    return false;
                }
                am = ai_move(ao, alm);
                if (!move_in(alm, am)) am = alm.moves[0];
                if (am.type == MoveType::AttackDone) {
                    if (st_.n_table == 0) am = alm.moves[0];
                    else break;
                }
                play_attack_card(A, am.card);
                alm = gen_attack_moves(st_, A, battle_limit_);
            }
            finish_battle(true);
            return true;
        }
        play_defense_card(D, m.card, m.target);
        step_ = Step::Attack;
        return true;
    }

    if (step_ == Step::FinishBattle) {
        LegalMoves lm = gen_attack_moves(st_, A, battle_limit_);
        if (lm.count == 0) {
            finish_battle(true);
            return true;
        }
        const Observation o = build_obs(A);
        Move m{};
        if (A == human_) {
            human_legal_ = lm;
            human_obs_ = o;
            waiting_human_ = true;
            return false;
        }
        m = ai_move(o, lm);
        if (!move_in(lm, m)) m = lm.moves[0];
        if (m.type == MoveType::AttackDone) {
            if (st_.n_table == 0) m = lm.moves[0];
            else {
                finish_battle(true);
                return true;
            }
        }
        play_attack_card(A, m.card);
        return true;
    }

    return false;
}

void PlaySession::pump() {
    waiting_human_ = false;
    int guard = 0;
    while (!waiting_human_ && !result_ && guard++ < 10000) {
        if (!step_once()) break;
    }
}

bool PlaySession::apply_human_move(int index) {
    if (!waiting_human_ || result_) return false;
    if (index < 0 || index >= human_legal_.count) return false;
    const Move m = human_legal_.moves[index];
    const int A = st_.attacker;
    const int D = 1 - A;

    push_log(std::string("You: ") + move_label(m, human_obs_));
    waiting_human_ = false;

    if (step_ == Step::Attack || step_ == Step::FinishBattle) {
        Move chosen = m;
        if (!move_in(human_legal_, chosen)) return false;
        if (chosen.type == MoveType::AttackDone) {
            if (st_.n_table == 0) return false;
            if (step_ == Step::FinishBattle)
                finish_battle(true);
            else
                step_ = Step::Defend;
        } else {
            play_attack_card(A, chosen.card);
        }
    } else if (step_ == Step::Defend) {
        if (m.type == MoveType::DefendTake) {
            battle_took_ = true;
            step_ = Step::FinishBattle;
            pump();
            return true;
        }
        play_defense_card(D, m.card, m.target);
        step_ = Step::Attack;
    }

    pump();
    return true;
}

std::string PlaySession::to_json() const {
    const int ai = 1 - human_;
    const CardView trump = card_view(st_.trump_card, st_.trump_suit);
    const auto hand = hand_views(st_.hands[human_], st_.trump_suit);

    std::ostringstream os;
    os << '{';
    os << "\"trump\":" << card_json(trump) << ',';
    os << "\"deck\":" << st_.deck_count << ',';
    os << "\"youAttack\":" << (st_.attacker == human_ ? "true" : "false") << ',';
    os << "\"opponentCards\":" << popcount(st_.hands[ai]) << ',';
    os << "\"hand\":" << cards_json(hand) << ',';
    os << "\"table\":[";
    for (int i = 0; i < st_.n_table; ++i) {
        if (i) os << ',';
        os << '{';
        os << "\"attack\":" << card_json(card_view(st_.atk[i], st_.trump_suit));
        if (st_.def[i] != NO_CARD)
            os << ",\"defense\":" << card_json(card_view(st_.def[i], st_.trump_suit));
        else
            os << ",\"defense\":null";
        os << '}';
    }
    os << "],\"waitingHuman\":" << (waiting_human_ ? "true" : "false") << ',';
    os << "\"yourTurn\":" << (waiting_human_ ? "true" : "false") << ',';
    os << "\"role\":\""
       << json_escape(waiting_human_ ? (human_obs_.is_attacker ? "attack" : "defend") : "")
       << "\",";
    os << "\"legalMoves\":[";
    if (waiting_human_) {
        for (int i = 0; i < human_legal_.count; ++i) {
            if (i) os << ',';
            const Move& m = human_legal_.moves[i];
            os << '{';
            os << "\"index\":" << i << ',';
            os << "\"type\":\"";
            switch (m.type) {
                case MoveType::AttackPlay: os << "attack"; break;
                case MoveType::AttackDone: os << "done"; break;
                case MoveType::DefendPlay: os << "defend"; break;
                case MoveType::DefendTake: os << "take"; break;
            }
            os << "\",\"label\":\"" << json_escape(move_label(m, human_obs_)) << "\"";
            if (m.card != NO_CARD) os << ",\"card\":" << card_json(card_view(m.card, st_.trump_suit));
            if (m.type == MoveType::DefendPlay) os << ",\"target\":" << int(m.target);
            os << '}';
        }
    }
    os << "],\"log\":[";
    for (std::size_t i = 0; i < log_.size(); ++i) {
        if (i) os << ',';
        os << '"' << json_escape(log_[i]) << '"';
    }
    os << "],\"gameOver\":" << (result_.has_value() ? "true" : "false");
    if (result_) {
        os << ",\"result\":\"";
        if (*result_ == GameResult::Draw) os << "draw";
        else if ((*result_ == GameResult::Player0Win) == (human_ == 0)) os << "win";
        else os << "loss";
        os << '"';
    }
    os << '}';
    return os.str();
}

}  // namespace durak
