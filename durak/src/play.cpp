#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <string>

#ifdef _WIN32
#include <windows.h>
#endif

#include "engine.hpp"
#include "strategies.hpp"

using namespace durak;

namespace {

int g_human_seat = 0;
GameState g_state{};

// UTF-8: ♣ ♦ ♥ ♠
static const char* SUIT_SYM[] = {"\xe2\x99\xa3", "\xe2\x99\xa6", "\xe2\x99\xa5", "\xe2\x99\xa0"};
static const char* SUIT_NAMES[] = {"clubs \xe2\x99\xa3", "diamonds \xe2\x99\xa6", "hearts \xe2\x99\xa5",
                                   "spades \xe2\x99\xa0"};

std::string card_display(Card c) {
    static const char* ranks = "6789TJQKA";
    if (c == NO_CARD) return "--";
    std::string s;
    s += ranks[rank_of(c)];
    s += SUIT_SYM[suit_of(c)];
    return s;
}

std::string hand_str(CardMask m) {
    std::string out;
    for (int s = 0; s < NUM_SUITS; ++s) {
        for (int r = 0; r < NUM_RANKS; ++r) {
            const Card c = make_card(r, s);
            if (m & card_bit(c)) {
                if (!out.empty()) out += ' ';
                out += card_display(c);
            }
        }
    }
    return out.empty() ? "(empty)" : out;
}

void print_table(const GameState& st) {
    if (st.n_table == 0) {
        std::printf("  table: (empty)\n");
        return;
    }
    std::printf("  table:\n");
    for (int i = 0; i < st.n_table; ++i) {
        std::printf("    %d) %s", i + 1, card_display(st.atk[i]).c_str());
        if (st.def[i] != NO_CARD) std::printf(" <- %s", card_display(st.def[i]).c_str());
        else std::printf(" <- ?");
        std::printf("\n");
    }
}

void print_status(const GameState& st) {
    const int ai = 1 - g_human_seat;
    std::printf("\n--- trump %s (%s) | deck %d ---\n", card_display(st.trump_card).c_str(),
                SUIT_NAMES[st.trump_suit], st.deck_count);
    std::printf("  you (%s): %s\n", st.attacker == g_human_seat ? "attack" : "defend",
                hand_str(st.hands[g_human_seat]).c_str());
    std::printf("  AI: %d cards\n", popcount(st.hands[ai]));
    print_table(st);
}

std::string move_label(const Move& m, const Observation& o) {
    switch (m.type) {
        case MoveType::AttackDone:
            return "pass (done attacking)";
        case MoveType::AttackPlay:
            return "attack " + card_display(m.card);
        case MoveType::DefendPlay:
            return "defend " + card_display(m.card) + " vs " + card_display(o.atk[m.target]);
        case MoveType::DefendTake:
            return "take cards";
    }
    return "?";
}

int suit_from_char(char sc) {
    sc = char(std::tolower(unsigned char(sc)));
    if (sc == 'c') return 0;
    if (sc == 'd') return 1;
    if (sc == 'h') return 2;
    if (sc == 's') return 3;
    return -1;
}

int suit_from_utf8(const std::string& tok, std::size_t pos) {
    if (pos + 2 >= tok.size()) return -1;
    const unsigned char b0 = unsigned char(tok[pos]);
    const unsigned char b1 = unsigned char(tok[pos + 1]);
    const unsigned char b2 = unsigned char(tok[pos + 2]);
    if (b0 == 0xE2 && b1 == 0x99) {
        if (b2 == 0xA3) return 0;  // ♣
        if (b2 == 0xA6) return 1;  // ♦
        if (b2 == 0xA5) return 2;  // ♥
        if (b2 == 0xA0) return 3;  // ♠
    }
    return -1;
}

bool parse_card_token(const std::string& tok, Card& out) {
    if (tok.size() < 2) return false;
    static const char* ranks = "6789TJQKA";
    const char rc = char(std::toupper(unsigned char(tok[0])));
    const char* rp = std::strchr(ranks, rc);
    if (!rp) return false;
    const int rank = int(rp - ranks);
    int suit = suit_from_char(tok[1]);
    if (suit < 0) suit = suit_from_utf8(tok, 1);
    if (suit < 0) return false;
    out = make_card(rank, suit);
    return true;
}

int find_move(const LegalMoves& lm, const std::string& tok) {
    std::string t = tok;
    for (char& c : t) c = char(std::tolower(unsigned char(c)));
    if (t == "d" || t == "done" || t == "pass") {
        for (int i = 0; i < lm.count; ++i)
            if (lm.moves[i].type == MoveType::AttackDone) return i;
        return -1;
    }
    if (t == "take" || t == "t") {
        for (int i = 0; i < lm.count; ++i)
            if (lm.moves[i].type == MoveType::DefendTake) return i;
        return -1;
    }
    Card c = NO_CARD;
    if (parse_card_token(t, c)) {
        for (int i = 0; i < lm.count; ++i)
            if (lm.moves[i].card == c) return i;
    }
    char* end = nullptr;
    const long n = std::strtol(t.c_str(), &end, 10);
    if (end && *end == '\0' && n >= 1 && n <= lm.count) return int(n - 1);
    return -1;
}

Move human_player(const Observation& o, const LegalMoves& lm, Rng&) {
    print_status(g_state);
    std::printf("\nYour turn (%s). Legal moves:\n", o.is_attacker ? "attack" : "defend");
    for (int i = 0; i < lm.count; ++i)
        std::printf("  %2d) %s\n", i + 1, move_label(lm.moves[i], o).c_str());
    std::printf("Pick number or card (e.g. 7%s or 7c). Attack: 'done'. Defend: 'take'.\n> ",
                SUIT_SYM[0]);
    std::fflush(stdout);

    std::string line;
    while (true) {
        if (!std::getline(std::cin, line)) return lm.moves[0];
        const int idx = find_move(lm, line);
        if (idx >= 0) return lm.moves[idx];
        std::printf("Invalid move. Try again> ");
        std::fflush(stdout);
    }
}

Move ai_player(const Observation& o, const LegalMoves& lm, Rng& rng) {
    const Move m = b2_heuristic(o, lm, rng);
    std::printf("  AI: %s\n", move_label(m, o).c_str());
    return m;
}

StrategyFn seat_fn(int seat) { return seat == g_human_seat ? &human_player : &ai_player; }

const char* result_text(GameResult r) {
    if (r == GameResult::Draw) return "Draw.";
    if (r == GameResult::Player0Win)
        return g_human_seat == 0 ? "You win!" : "AI wins (you are durak).";
    return g_human_seat == 1 ? "You win!" : "AI wins (you are durak).";
}

}  // namespace

int main(int argc, char** argv) {
#ifdef _WIN32
    SetConsoleOutputCP(65001);
    SetConsoleCP(65001);
#endif
    std::uint64_t seed = 0;
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--seed") == 0 && i + 1 < argc)
            seed = std::strtoull(argv[++i], nullptr, 10);
        else if (std::strcmp(argv[i], "--seat") == 0 && i + 1 < argc)
            g_human_seat = std::atoi(argv[++i]) & 1;
        else if (std::strcmp(argv[i], "--help") == 0 || std::strcmp(argv[i], "-h") == 0) {
            std::printf("play vs B2 heuristic agent\n\n");
            std::printf("usage: play [--seed N] [--seat 0|1]\n");
            std::printf("  --seat 0  you are player 0 (default)\n");
            std::printf("  --seat 1  you are player 1\n");
            return 0;
        }
    }

    g_state = new_game(seed);
    g_state.attacker = first_attacker(g_state);
    Rng rng(seed ? seed + 1 : 1);

    std::printf("Durak vs B2 (heuristic agent). You are player %d.\n", g_human_seat);
    std::printf("Cards: rank + suit (7%s, 7c). Trump: %s\n\n", SUIT_SYM[0],
                SUIT_NAMES[g_state.trump_suit]);

    StrategyFn s0 = seat_fn(0);
    StrategyFn s1 = seat_fn(1);

    constexpr int MAX_BATTLES = 4000;
    for (int battle = 0; battle < MAX_BATTLES; ++battle) {
        if (g_state.deck_count == 0) {
            const bool e0 = (g_state.hands[0] == 0);
            const bool e1 = (g_state.hands[1] == 0);
            if (e0 && e1) {
                std::printf("\n=== %s ===\n", result_text(GameResult::Draw));
                return 0;
            }
            if (e0) {
                std::printf("\n=== %s ===\n", result_text(GameResult::Player0Win));
                return 0;
            }
            if (e1) {
                std::printf("\n=== %s ===\n", result_text(GameResult::Player1Win));
                return 0;
            }
        }
        const bool took = run_battle(g_state, s0, s1, rng);
        std::printf("  >> %s\n", took ? "defender took the table" : "defense successful (bito)");
        draw_to_six(g_state, g_state.attacker);
        draw_to_six(g_state, 1 - g_state.attacker);
        if (!took) g_state.attacker = 1 - g_state.attacker;
    }
    std::printf("\n=== Draw (battle limit) ===\n");
    return 0;
}
