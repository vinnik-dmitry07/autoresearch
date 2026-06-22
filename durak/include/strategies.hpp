#pragma once

#include "engine.hpp"

namespace durak {

Move b0_random(const Observation&, const LegalMoves&, Rng&);          // random legal
Move b1_basic(const Observation&, const LegalMoves&, Rng&);           // basic no-memory
Move b2_heuristic(const Observation&, const LegalMoves&, Rng&);       // heuristic no-memory (agent)
Move b3_heuristic_mem(const Observation&, const LegalMoves&, Rng&);   // same core + memory (ablation)
Move b4_mem(const Observation&, const LegalMoves&, Rng&);             // independent memory baseline

StrategyFn strategy_by_name(const char* name);
const char* strategy_label(StrategyFn fn);

}  // namespace durak
