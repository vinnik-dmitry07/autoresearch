#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "cards.hpp"
#include "engine.hpp"
#include "move.hpp"

namespace durak {

struct CardView {
    Card id = NO_CARD;
    std::string rank;
    std::string suit;
    std::string suit_sym;
    bool red = false;
    bool trump = false;
};

struct MoveView {
    int index = 0;
    std::string type;
    std::string label;
    Card card = NO_CARD;
    int target = -1;
};

CardView card_view(Card c, int trump_suit);
std::vector<CardView> hand_views(CardMask m, int trump_suit);
std::string move_label(const Move& m, const Observation& o);
std::string json_escape(const std::string& s);
std::string card_json(const CardView& c);
std::string cards_json(const std::vector<CardView>& cards);

}  // namespace durak
