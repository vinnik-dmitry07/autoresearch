#include "play_ui.hpp"

#include <sstream>

namespace durak {

namespace {

static const char* RANKS = "6789TJQKA";
static const char* SUIT_SYM[] = {"\xe2\x99\xa3", "\xe2\x99\xa6", "\xe2\x99\xa5", "\xe2\x99\xa0"};
static const char* SUIT_NAMES[] = {"clubs", "diamonds", "hearts", "spades"};

}  // namespace

CardView card_view(Card c, int trump_suit) {
    CardView v;
    if (c == NO_CARD) {
        v.rank = "-";
        v.suit = "none";
        v.suit_sym = "-";
        return v;
    }
    v.id = c;
    const int r = rank_of(c);
    v.rank = (r == 4) ? "10" : std::string(1, RANKS[r]);
    const int s = suit_of(c);
    v.suit = SUIT_NAMES[s];
    v.suit_sym = SUIT_SYM[s];
    v.red = (s == 1 || s == 2);
    v.trump = (s == trump_suit);
    return v;
}

std::vector<CardView> hand_views(CardMask m, int trump_suit) {
    std::vector<CardView> out;
    for (int s = 0; s < NUM_SUITS; ++s) {
        for (int r = 0; r < NUM_RANKS; ++r) {
            const Card c = make_card(r, s);
            if (m & card_bit(c)) out.push_back(card_view(c, trump_suit));
        }
    }
    return out;
}

std::string move_label(const Move& m, const Observation& o) {
    switch (m.type) {
        case MoveType::AttackDone:
            return "Done attacking";
        case MoveType::AttackPlay:
            return "Play " + card_view(m.card, o.trump_suit).rank + card_view(m.card, o.trump_suit).suit_sym;
        case MoveType::DefendPlay:
            return "Beat with " + card_view(m.card, o.trump_suit).rank +
                   card_view(m.card, o.trump_suit).suit_sym;
        case MoveType::DefendTake:
            return "Take cards";
    }
    return "?";
}

std::string json_escape(const std::string& s) {
    std::string out;
    out.reserve(s.size() + 8);
    for (unsigned char c : s) {
        if (c == '"') out += "\\\"";
        else if (c == '\\') out += "\\\\";
        else if (c == '\n') out += "\\n";
        else if (c >= 0x20) out += char(c);
    }
    return out;
}

std::string card_json(const CardView& c) {
    std::ostringstream os;
    os << "{\"id\":" << int(c.id) << ",\"rank\":\"" << json_escape(c.rank) << "\",\"suit\":\""
       << json_escape(c.suit) << "\",\"sym\":\"" << json_escape(c.suit_sym) << "\",\"red\":"
       << (c.red ? "true" : "false") << ",\"trump\":" << (c.trump ? "true" : "false") << '}';
    return os.str();
}

std::string cards_json(const std::vector<CardView>& cards) {
    std::string out = "[";
    for (std::size_t i = 0; i < cards.size(); ++i) {
        if (i) out += ',';
        out += card_json(cards[i]);
    }
    out += ']';
    return out;
}

}  // namespace durak
