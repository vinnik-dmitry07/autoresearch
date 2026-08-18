#include "machine.hpp"
#include "profiler.hpp"
#include "test_util.hpp"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

using vliw::Engine;
using vliw::Machine;
using vliw::ProfileExtra;
using vliw::Program;
using vliw::State;
using vliw::profile_json;

namespace {

constexpr std::uint8_t kAdd = 0;
constexpr std::uint8_t kXor = 5;
constexpr std::uint8_t kShl = 8;
constexpr std::uint8_t kShr = 9;
constexpr std::uint8_t kMod = 10;
constexpr std::uint8_t kLt = 11;
constexpr std::uint8_t kEqOp = 12;
constexpr std::uint8_t kLoad = 0;
constexpr std::uint8_t kConst = 3;
constexpr std::uint8_t kStore = 0;
constexpr std::uint8_t kSelect = 0;
constexpr std::uint8_t kHalt = 3;
constexpr std::uint8_t kPause = 4;

void one(Program& p, Engine e, std::uint8_t op, std::uint32_t dest = 0, std::uint32_t a = 0,
         std::uint32_t b = 0, std::uint32_t c = 0) {
    p.begin_bundle();
    p.add(e, op, dest, a, b, c);
    p.end_bundle();
}

std::uint32_t ref_alu(std::uint8_t kind, std::uint32_t a1, std::uint32_t a2) {
    switch (kind) {
        case kAdd:
            return a1 + a2;
        case kXor:
            return a1 ^ a2;
        case kShl:
            return a2 >= 32 ? 0u : (a1 << a2);
        case kShr:
            return a2 >= 32 ? 0u : (a1 >> a2);
        default:
            return 0;
    }
}

std::uint32_t myhash(std::uint32_t a) {
    const std::uint8_t op1[] = {kAdd, kXor, kAdd, kAdd, kAdd, kXor};
    const std::uint32_t v1[] = {0x7ED55D16u, 0xC761C23Cu, 0x165667B1u, 0xD3A2646Cu, 0xFD7046C5u,
                                0xB55A4F09u};
    const std::uint8_t op2[] = {kAdd, kXor, kAdd, kXor, kAdd, kXor};
    const std::uint8_t op3[] = {kShl, kShr, kShl, kShl, kShl, kShr};
    const std::uint32_t v3[] = {12, 19, 5, 9, 3, 16};
    for (int i = 0; i < 6; ++i) {
        a = ref_alu(op2[i], ref_alu(op1[i], a, v1[i]), ref_alu(op3[i], a, v3[i]));
    }
    return a;
}

void emit_hash(Program& p, std::uint32_t val, std::uint32_t tmp1, std::uint32_t tmp2) {
    const std::uint8_t op1[] = {kAdd, kXor, kAdd, kAdd, kAdd, kXor};
    const std::uint32_t v1[] = {0x7ED55D16u, 0xC761C23Cu, 0x165667B1u, 0xD3A2646Cu, 0xFD7046C5u,
                                0xB55A4F09u};
    const std::uint8_t op2[] = {kAdd, kXor, kAdd, kXor, kAdd, kXor};
    const std::uint8_t op3[] = {kShl, kShr, kShl, kShl, kShl, kShr};
    const std::uint32_t v3[] = {12, 19, 5, 9, 3, 16};
    for (int i = 0; i < 6; ++i) {
        const std::uint32_t c1 = 200 + static_cast<std::uint32_t>(i) * 2;
        const std::uint32_t c3 = 201 + static_cast<std::uint32_t>(i) * 2;
        one(p, Engine::Load, kConst, c1, v1[i]);
        one(p, Engine::Load, kConst, c3, v3[i]);
        one(p, Engine::Alu, op1[i], tmp1, val, c1);
        one(p, Engine::Alu, op3[i], tmp2, val, c3);
        one(p, Engine::Alu, op2[i], val, tmp1, tmp2);
    }
}

// Flat image + unrolled 1-item / 1-round kernel, same layout as build_mem_image.
Program make_mini_kernel() {
    Program p;
    const std::uint32_t tmp1 = 0;
    const std::uint32_t tmp2 = 1;
    const std::uint32_t tmp3 = 2;
    const std::uint32_t forest_p = 3;
    const std::uint32_t idx_p = 4;
    const std::uint32_t val_p = 5;
    const std::uint32_t n_nodes = 6;
    const std::uint32_t tmp_idx = 7;
    const std::uint32_t tmp_val = 8;
    const std::uint32_t tmp_node = 9;
    const std::uint32_t tmp_addr = 10;
    const std::uint32_t zero_c = 11;
    const std::uint32_t one_c = 12;
    const std::uint32_t two_c = 13;

    one(p, Engine::Load, kConst, tmp1, 4);
    one(p, Engine::Load, kLoad, forest_p, tmp1);
    one(p, Engine::Load, kConst, tmp1, 5);
    one(p, Engine::Load, kLoad, idx_p, tmp1);
    one(p, Engine::Load, kConst, tmp1, 6);
    one(p, Engine::Load, kLoad, val_p, tmp1);
    one(p, Engine::Load, kConst, tmp1, 1);
    one(p, Engine::Load, kLoad, n_nodes, tmp1);
    one(p, Engine::Load, kConst, zero_c, 0);
    one(p, Engine::Load, kConst, one_c, 1);
    one(p, Engine::Load, kConst, two_c, 2);
    one(p, Engine::Flow, kPause);

    one(p, Engine::Alu, kAdd, tmp_addr, idx_p, zero_c);
    one(p, Engine::Load, kLoad, tmp_idx, tmp_addr);
    one(p, Engine::Alu, kAdd, tmp_addr, val_p, zero_c);
    one(p, Engine::Load, kLoad, tmp_val, tmp_addr);
    one(p, Engine::Alu, kAdd, tmp_addr, forest_p, tmp_idx);
    one(p, Engine::Load, kLoad, tmp_node, tmp_addr);
    one(p, Engine::Alu, kXor, tmp_val, tmp_val, tmp_node);
    emit_hash(p, tmp_val, tmp1, tmp2);
    one(p, Engine::Alu, kMod, tmp1, tmp_val, two_c);
    one(p, Engine::Alu, kEqOp, tmp1, tmp1, zero_c);
    one(p, Engine::Flow, kSelect, tmp3, tmp1, one_c, two_c);
    one(p, Engine::Alu, 2, tmp_idx, tmp_idx, two_c);  // *
    one(p, Engine::Alu, kAdd, tmp_idx, tmp_idx, tmp3);
    one(p, Engine::Alu, kLt, tmp1, tmp_idx, n_nodes);
    one(p, Engine::Flow, kSelect, tmp_idx, tmp1, tmp_idx, zero_c);
    one(p, Engine::Alu, kAdd, tmp_addr, idx_p, zero_c);
    one(p, Engine::Store, kStore, tmp_addr, tmp_idx);
    one(p, Engine::Alu, kAdd, tmp_addr, val_p, zero_c);
    one(p, Engine::Store, kStore, tmp_addr, tmp_val);
    one(p, Engine::Flow, kPause);
    one(p, Engine::Flow, kHalt);
    return p;
}

std::vector<std::uint32_t> make_mem(std::uint32_t value, std::uint32_t node0) {
    // header 8 + 3 forest + 1 idx + 1 val
    std::vector<std::uint32_t> mem(16, 0);
    mem[0] = 1;
    mem[1] = 3;
    mem[2] = 1;
    mem[3] = 1;
    mem[4] = 8;
    mem[5] = 11;
    mem[6] = 12;
    mem[8] = node0;
    mem[9] = 0;
    mem[10] = 0;
    mem[11] = 0;
    mem[12] = value;
    return mem;
}

void expect_step(std::uint32_t value, std::uint32_t node0, std::uint32_t& out_val,
                 std::uint32_t& out_idx) {
    out_val = myhash(value ^ node0);
    std::uint32_t idx = 0;
    idx = 2 * idx + (out_val % 2 == 0 ? 1u : 2u);
    if (idx >= 3) idx = 0;
    out_idx = idx;
}

std::int64_t jget(const std::string& json, const char* key) {
    const std::string pat = std::string("\"") + key + "\":";
    const auto pos = json.find(pat);
    if (pos == std::string::npos) return -999999;
    const char* p = json.c_str() + pos + pat.size();
    while (*p == ' ') ++p;
    return std::strtoll(p, nullptr, 10);
}

bool jhas(const std::string& json, const char* needle) {
    return json.find(needle) != std::string::npos;
}

void test_mini_kernel_three_paths() {
    std::printf("[1/6] mini kernel checked / fast / linear\n");
    const std::uint32_t value = 0x12345678u;
    const std::uint32_t node0 = 0x11111111u;
    std::uint32_t want_val = 0;
    std::uint32_t want_idx = 0;
    expect_step(value, node0, want_val, want_idx);

    auto mem = make_mem(value, node0);
    Program prog = make_mini_kernel();

    Machine checked(mem, prog);
    checked.run();
    CHECK_EQ(checked.mem()[12], value);
    checked.run();
    CHECK_EQ(checked.mem()[12], want_val);
    CHECK_EQ(checked.mem()[11], want_idx);
    checked.set_enable_pause(false);
    checked.run();

    Machine fast(mem, prog);
    fast.set_enable_debug(false);
    fast.set_enable_pause(false);
    fast.run();
    CHECK_EQ(fast.mem()[12], want_val);
    CHECK_EQ(fast.mem()[11], want_idx);
    CHECK_EQ(fast.cycle(), checked.cycle());

    Machine linear(mem, prog);
    linear.set_enable_debug(false);
    linear.set_enable_pause(false);
    linear.run();
    CHECK_EQ(linear.mem()[12], want_val);
    CHECK_EQ(linear.mem()[11], want_idx);
    CHECK_EQ(linear.cycle(), checked.cycle());
    CHECK(linear.cores()[0].state == State::Stopped);
}

void test_load_oneslot_pipeline() {
    std::printf("[2/6] load_oneslot → Machine → run\n");
    struct Desc {
        std::uint8_t engine;
        std::uint8_t op;
        std::uint8_t pad[2];
        std::uint32_t dest;
        std::uint32_t a;
        std::uint32_t b;
        std::uint32_t c;
    };
    const Desc raw[] = {
        {2, kConst, {}, 0, 9, 0, 0},
        {2, kConst, {}, 1, 6, 0, 0},
        {0, 2, {}, 2, 0, 1, 0},  // mul
        {2, kConst, {}, 3, 0, 0, 0},
        {3, kStore, {}, 3, 2, 0, 0},
        {4, kHalt, {}, 0, 0, 0, 0},
    };
    Program p;
    p.load_oneslot(raw, 6);
    CHECK(p.linear_ok);
    const std::uint32_t mem0[] = {0, 0, 0, 0, 0, 0, 0, 0};
    Machine m(mem0, p);
    m.set_enable_pause(false);
    m.set_enable_debug(false);
    m.run();
    CHECK_EQ(m.mem()[0], 54);
    CHECK_EQ(m.cycle(), 6);
    CHECK_EQ(jget(profile_json(p), "cycles_est"), m.cycle());
}

void test_pause_then_linear_disabled_body() {
    std::printf("[3/6] pause/resume then disable pause for tail\n");
    const std::uint32_t value = 7;
    const std::uint32_t node0 = 3;
    std::uint32_t want_val = 0;
    std::uint32_t want_idx = 0;
    expect_step(value, node0, want_val, want_idx);
    auto mem = make_mem(value, node0);
    Program prog = make_mini_kernel();
    Machine m(mem, prog);
    m.run();
    CHECK(m.cores()[0].state == State::Paused);
    CHECK_EQ(m.mem()[12], value);
    m.set_enable_pause(false);
    m.set_enable_debug(false);
    m.run();
    CHECK_EQ(m.mem()[12], want_val);
    CHECK_EQ(m.mem()[11], want_idx);
}

void test_profile_matches_disabled_run() {
    std::printf("[4/6] profile cycles_est == Machine.run (pause off)\n");
    Program prog = make_mini_kernel();
    prog.finalize();
    const std::string json = profile_json(prog);
    auto mem = make_mem(0x12345678u, 0x11111111u);
    Machine m(mem, prog);
    m.set_enable_pause(false);
    m.set_enable_debug(false);
    m.run();
    CHECK_EQ(jget(json, "cycles_est"), m.cycle());
    CHECK(jget(json, "slots") > 0);
    CHECK(jget(json, "floor") > 0);
    CHECK(jget(json, "overhead") >= 0);
    CHECK(jhas(json, "\"hypotheses\""));
    CHECK(jhas(json, "\"select_vs_gather\""));
}

void test_profile_named_and_phases_on_mini_kernel() {
    std::printf("[5/6] profile extra names/phases on mini kernel\n");
    Program prog = make_mini_kernel();
    prog.finalize();
    const std::uint32_t addrs[] = {0, 1, 2, 7, 8, 9, 10};
    const std::uint16_t lens[] = {1, 1, 1, 1, 1, 1, 1};
    const char* names[] = {"tmp1", "tmp2", "tmp3", "tmp_idx", "tmp_val", "tmp_node", "tmp_addr"};
    const int n_billed = static_cast<int>(prog.bundles.size());
    std::vector<std::uint8_t> phases(static_cast<std::size_t>(n_billed), 1);
    for (int i = 12; i < n_billed && i < 20; ++i) phases[static_cast<std::size_t>(i)] = 2;
    for (int i = 20; i < n_billed && i < 50; ++i) phases[static_cast<std::size_t>(i)] = 3;
    for (int i = 50; i < n_billed && i < 58; ++i) phases[static_cast<std::size_t>(i)] = 4;
    for (int i = 58; i < n_billed; ++i) phases[static_cast<std::size_t>(i)] = 5;
    ProfileExtra extra;
    extra.scratch_addr = addrs;
    extra.scratch_len = lens;
    extra.scratch_names = names;
    extra.n_scratch = 7;
    extra.phase = phases.data();
    extra.n_phase = n_billed;
    const std::string json = profile_json(prog, nullptr, &extra);
    CHECK(jget(json, "phase_init") > 0);
    CHECK(jget(json, "phase_hash") > 0);
    CHECK_EQ(jget(json, "phase_init") + jget(json, "phase_ldst") + jget(json, "phase_hash") +
                 jget(json, "phase_walk") + jget(json, "phase_store") + jget(json, "phase_gather") +
                 jget(json, "phase_unknown"),
             jget(json, "cycles_est"));
    CHECK(jhas(json, "tmp_val"));
    CHECK(jhas(json, "named_live"));
}

void test_profile_all_metric_blocks() {
    std::printf("[7/7] all metric blocks on mini kernel\n");
    Program prog = make_mini_kernel();
    prog.finalize();
    const std::uint32_t addrs[] = {0, 1, 2, 7, 8, 9, 10};
    const std::uint16_t lens[] = {1, 1, 1, 1, 1, 1, 1};
    const char* names[] = {"tmp1", "tmp2", "tmp3", "tmp_idx", "tmp_val", "tmp_node", "tmp_addr"};
    const int n_billed = static_cast<int>(prog.bundles.size());
    std::vector<std::uint8_t> phases(static_cast<std::size_t>(n_billed), 3);
    for (int i = 0; i < n_billed && i < 8; ++i) phases[static_cast<std::size_t>(i)] = 1;
    if (n_billed > 0) phases[static_cast<std::size_t>(n_billed - 1)] = 1;
    ProfileExtra extra;
    extra.scratch_addr = addrs;
    extra.scratch_len = lens;
    extra.scratch_names = names;
    extra.n_scratch = 7;
    extra.phase = phases.data();
    extra.n_phase = n_billed;
    extra.forest_height = 3;
    extra.rounds = 2;
    extra.batch_size = 4;
    const std::string j = profile_json(prog, nullptr, &extra);
    CHECK(jhas(j, "\"regions\""));
    CHECK(jhas(j, "\"occupancy_hist\""));
    CHECK(jhas(j, "\"occupancy_series\""));
    CHECK(jhas(j, "\"pressure\""));
    CHECK(jhas(j, "\"live_overlaps\""));
    CHECK(jhas(j, "\"integrity\""));
    CHECK(jhas(j, "\"pipeline\""));
    CHECK(jhas(j, "\"bounds\""));
    CHECK(jhas(j, "\"alu_class\""));
    CHECK(jhas(j, "\"scratch_vectors\""));
    CHECK(jhas(j, "\"gathers_by_depth\""));
    CHECK(jhas(j, "\"select_vs_gather\""));
    CHECK(jhas(j, "\"zero_load_cycles\""));
    CHECK(jhas(j, "\"load0_valu_lt6\""));
    CHECK(jhas(j, "\"war_same_cycle\""));
    CHECK(jhas(j, "\"ii_est\""));
    CHECK(jhas(j, "\"wavefront\""));
    CHECK(jhas(j, "\"load_to_use_hist\""));
    CHECK(jhas(j, "\"limit\": 12"));
    CHECK(jhas(j, "\"limit\": 6"));
    CHECK(jhas(j, "\"limit\": 2"));
    CHECK(jhas(j, "tmp_val"));
    CHECK_EQ(jget(j, "item_rounds"), 8);
    CHECK_EQ(jget(j, "zero_load_cycles") + jget(j, "load_ops"), jget(j, "cycles_est"));
    CHECK_EQ(jget(j, "zero_load_cycles"), jget(j, "load0_valu_lt6"));
    CHECK(jhas(j, "\"occupancy_series\": {\"n\": 0"));
    CHECK(jget(j, "peak_live") > 0);
    CHECK(jget(j, "startup_end") >= 0);
    CHECK(jget(j, "drain_start") > 0);
}

void test_profile_same_program_diff_and_data_independent() {
    std::printf("[6/6] profile diff + data-independent\n");
    Program prog = make_mini_kernel();
    prog.finalize();
    const std::string a = profile_json(prog);
    const std::string b = profile_json(prog, a.c_str());
    CHECK(jhas(b, "\"same_program\": true"));
    CHECK_EQ(jget(b, "cycles_est"), jget(a, "cycles_est"));
    const auto dpos = b.find("\"diff\"");
    CHECK(dpos != std::string::npos);
    CHECK(b.find("\"cycles_est\": 0", dpos) != std::string::npos);
    CHECK_EQ(jget(a, "cycles_est"), jget(profile_json(prog), "cycles_est"));
}

}  // namespace

int main() {
    setvbuf(stdout, nullptr, _IONBF, 0);
    test_mini_kernel_three_paths();
    test_load_oneslot_pipeline();
    test_pause_then_linear_disabled_body();
    test_profile_matches_disabled_run();
    test_profile_named_and_phases_on_mini_kernel();
    test_profile_same_program_diff_and_data_independent();
    test_profile_all_metric_blocks();
    return vliw_test::report("engine_integration");
}
