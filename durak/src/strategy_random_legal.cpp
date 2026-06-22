#include "strategies.hpp"

// B0: uniform random over the legal moves. Sanity opponent and ladder floor.
namespace durak {

Move b0_random(const Observation&, const LegalMoves& legal, Rng& rng) {
    const int i = int(rng.bounded(std::uint32_t(legal.count)));
    return legal.moves[i];
}

}  // namespace durak
