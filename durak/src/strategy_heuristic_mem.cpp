#include "policy_core.hpp"
#include "strategies.hpp"

// B3: memory ablation of B2. Fixed wrapper -- NOT edited by the agent. It calls
// the exact same choose_move_core as B2, but with MemoryFeatures enabled, so the
// only difference between B2 and B3 is whether the shared core can see memory.
namespace durak {

Move b3_heuristic_mem(const Observation& o, const LegalMoves& legal, Rng&) {
    const LocalFeatures L = make_local_features(o);
    const MemoryFeatures mf = make_memory_features(*o.memory);
    return choose_move_core(L, &mf, legal);
}

}  // namespace durak
