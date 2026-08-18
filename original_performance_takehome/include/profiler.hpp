#pragma once

#include "machine.hpp"

#include <cstdint>
#include <string>

namespace vliw {

struct ProfileExtra {
    const std::uint32_t* scratch_addr = nullptr;
    const std::uint16_t* scratch_len = nullptr;
    const char* const* scratch_names = nullptr;
    int n_scratch = 0;
    const std::uint8_t* phase = nullptr;
    int n_phase = 0;
    const std::uint8_t* depth = nullptr;
    int n_depth = 0;
    int forest_height = 0;
    int rounds = 0;
    int batch_size = 0;
};

// Scheduler-aware static profile. Writes are deferred one cycle.
std::string profile_json(const Program& program, const char* prev_json = nullptr,
                         const ProfileExtra* extra = nullptr);

}  // namespace vliw
