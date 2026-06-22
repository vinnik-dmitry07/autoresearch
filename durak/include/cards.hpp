#pragma once

#include <array>
#include <bit>
#include <cstdint>
#include <string>

namespace durak {

using Card = std::uint8_t;
using CardMask = std::uint64_t;

constexpr int NUM_RANKS = 9;  // 6 7 8 9 10 J Q K A  ->  index 0..8
constexpr int NUM_SUITS = 4;
constexpr int NUM_CARDS = 36;
constexpr Card NO_CARD = 255;
constexpr CardMask ALL_CARDS = (CardMask{1} << NUM_CARDS) - 1;

// Card encoding: card = rank * 4 + suit.
// Lower card index == lower rank, so a plain bit scan yields the lowest rank.
constexpr Card make_card(int rank, int suit) { return Card(rank * NUM_SUITS + suit); }
constexpr int rank_of(Card c) { return c >> 2; }
constexpr int suit_of(Card c) { return c & 3; }
constexpr CardMask card_bit(Card c) { return CardMask{1} << c; }

constexpr std::array<CardMask, NUM_RANKS> make_rank_masks() {
    std::array<CardMask, NUM_RANKS> m{};
    for (int r = 0; r < NUM_RANKS; ++r) m[r] = CardMask{0xF} << (r * NUM_SUITS);
    return m;
}
constexpr std::array<CardMask, NUM_SUITS> make_suit_masks() {
    std::array<CardMask, NUM_SUITS> m{};
    for (int s = 0; s < NUM_SUITS; ++s) {
        CardMask x = 0;
        for (int r = 0; r < NUM_RANKS; ++r) x |= card_bit(make_card(r, s));
        m[s] = x;
    }
    return m;
}

inline constexpr std::array<CardMask, NUM_RANKS> RANK_MASK = make_rank_masks();
inline constexpr std::array<CardMask, NUM_SUITS> SUIT_MASK = make_suit_masks();

inline int popcount(CardMask m) { return std::popcount(m); }
inline Card lowest(CardMask m) { return Card(std::countr_zero(m)); }  // precondition: m != 0

// Does defender card 'd' beat attacker card 'a' given the trump suit?
inline bool beats(Card d, Card a, int trump_suit) {
    const int ds = suit_of(d), as = suit_of(a);
    if (ds == as) return d > a;        // same suit (also covers trump vs trump)
    return ds == trump_suit;           // a trump beats any off-suit card
}

inline std::string card_name(Card c) {
    static const char* ranks = "6789TJQKA";
    static const char* suits = "cdhs";
    if (c == NO_CARD) return "--";
    std::string s;
    s += ranks[rank_of(c)];
    s += suits[suit_of(c)];
    return s;
}

}  // namespace durak
