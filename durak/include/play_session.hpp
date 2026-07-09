#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "engine.hpp"
#include "move.hpp"

namespace durak {

class PlaySession {
public:
    void new_game(std::uint64_t seed, int human_seat = 0);

    // Run AI moves until the human must act or the game ends.
    void pump();

    // Apply a human move by legal-move index, then pump AI again.
    bool apply_human_move(int index);

    std::string to_json() const;

    bool waiting_human() const { return waiting_human_; }
    bool game_over() const { return result_.has_value(); }

private:
    enum class Step { Attack, Defend, FinishBattle, BetweenBattles };

    Observation build_obs(int player) const;
    bool move_in(const LegalMoves& lm, const Move& m) const;
    void play_attack_card(int attacker, Card c);
    void play_defense_card(int defender, Card c, int target);
    void start_battle();
    void finish_battle(bool took);
    std::optional<GameResult> check_game_over() const;
    bool step_once();
    Move ai_move(const Observation& o, const LegalMoves& lm);
    void push_log(const std::string& line);

    GameState st_{};
    Rng rng_{1};
    int human_ = 0;
    int battle_limit_ = 0;
    bool in_battle_ = false;
    bool battle_took_ = false;
    Step step_ = Step::BetweenBattles;

    bool waiting_human_ = false;
    LegalMoves human_legal_{};
    Observation human_obs_{};
    std::optional<GameResult> result_{};
    std::vector<std::string> log_;
    std::uint64_t deck_seed_ = 0;
};

}  // namespace durak
