#include "profiler.hpp"
#include "test_util.hpp"

#include <cstdint>
#include <cstdlib>
#include <string>

using vliw::Engine;
using vliw::ProfileExtra;
using vliw::Program;
using vliw::profile_json;

namespace {

constexpr std::uint8_t kAdd = 0;
constexpr std::uint8_t kConst = 3;
constexpr std::uint8_t kLoad = 0;
constexpr std::uint8_t kVLoad = 2;
constexpr std::uint8_t kStore = 0;
constexpr std::uint8_t kSelect = 0;
constexpr std::uint8_t kVSelect = 2;
constexpr std::uint8_t kPause = 4;
constexpr std::uint8_t kValuAdd = 0;
constexpr std::uint8_t kValuMadd = 14;

std::int64_t jget(const std::string& json, const char* key) {
    const std::string pat = std::string("\"") + key + "\":";
    const auto pos = json.find(pat);
    if (pos == std::string::npos) return -999999;
    const char* p = json.c_str() + pos + pat.size();
    while (*p == ' ') ++p;
    return std::strtoll(p, nullptr, 10);
}

bool jstr(const std::string& json, const char* key, const char* val) {
    const std::string a = std::string("\"") + key + "\": \"" + val + "\"";
    const std::string b = std::string("\"") + key + "\":\"" + val + "\"";
    return json.find(a) != std::string::npos || json.find(b) != std::string::npos;
}

void one(Program& p, Engine e, std::uint8_t op, std::uint32_t dest = 0, std::uint32_t a = 0,
         std::uint32_t b = 0, std::uint32_t c = 0) {
    p.begin_bundle();
    p.add(e, op, dest, a, b, c);
    p.end_bundle();
}

bool has(const std::string& json, const char* needle) {
    return json.find(needle) != std::string::npos;
}

void test_dep_chain() {
    Program p;
    one(p, Engine::Load, kConst, 0, 1);
    one(p, Engine::Load, kConst, 1, 2);
    one(p, Engine::Alu, kAdd, 2, 0, 1);
    one(p, Engine::Load, kConst, 3, 0);
    one(p, Engine::Store, kStore, 3, 2);
    p.finalize();
    const std::string j = profile_json(p);
    CHECK(has(j, "\"cycles_est\": 5"));
    CHECK(has(j, "\"critical_path\": 3"));
    CHECK(has(j, "\"idle_cause\": \"deps\""));
    CHECK(has(j, "\"assumes_linear\": true"));
    CHECK(has(j, "alu.+"));
    CHECK(has(j, "\"floor\": 2"));
    CHECK(has(j, "\"floor_engine\": \"load\""));
    CHECK(has(j, "\"overhead\": 3"));
    CHECK(has(j, "\"hypotheses\""));
    CHECK(has(j, "\"select_vs_gather\""));
}

void test_packed_bundle() {
    Program p;
    p.begin_bundle();
    p.add(Engine::Load, kConst, 0, 1);
    p.add(Engine::Load, kConst, 1, 2);
    p.end_bundle();
    p.begin_bundle();
    p.add(Engine::Alu, kAdd, 2, 0, 1);
    p.end_bundle();
    p.finalize();
    const std::string j = profile_json(p);
    CHECK(has(j, "\"cycles_est\": 2"));
    CHECK(has(j, "\"slots\": 3"));
    CHECK(has(j, "\"critical_path\": 2"));
}

void test_debug_skips_cycle() {
    Program p;
    one(p, Engine::Load, kConst, 0, 1);
    one(p, Engine::Debug, 2);
    one(p, Engine::Load, kConst, 1, 2);
    p.finalize();
    const std::string j = profile_json(p);
    CHECK(has(j, "\"cycles_est\": 2"));
    CHECK(has(j, "\"debug_bundles\": 1"));
}

void test_diff_and_fingerprint() {
    Program p;
    one(p, Engine::Load, kConst, 0, 7);
    p.finalize();
    const std::string a = profile_json(p);
    const std::string b = profile_json(p, a.c_str());
    CHECK(has(b, "\"same_program\": true"));
    CHECK(has(b, "\"cycles_est\": 0"));
    Program q;
    one(q, Engine::Load, kConst, 0, 7);
    one(q, Engine::Load, kConst, 1, 8);
    q.finalize();
    const std::string c = profile_json(q, a.c_str());
    CHECK(has(c, "\"same_program\": false"));
    CHECK(has(c, "\"cycles_est\": 1"));
}

void test_independent_consts_are_schedule() {
    Program p;
    for (int i = 0; i < 32; ++i) one(p, Engine::Load, kConst, static_cast<std::uint32_t>(i), 1);
    p.finalize();
    const std::string j = profile_json(p);
    CHECK(has(j, "\"idle_cause\": \"schedule\""));
    CHECK(has(j, "\"cycles_est\": 32"));
}

void test_cp_split_waw_and_mem() {
    Program waw;
    one(waw, Engine::Load, kConst, 0, 1);
    one(waw, Engine::Load, kConst, 0, 2);
    waw.finalize();
    const std::string jw = profile_json(waw);
    CHECK(has(jw, "\"cp_raw\": 1"));
    CHECK(has(jw, "\"cp_waw\": 2"));

    Program mem;
    one(mem, Engine::Load, kConst, 0, 1);
    one(mem, Engine::Load, kConst, 1, 2);
    one(mem, Engine::Store, kStore, 0, 1);
    one(mem, Engine::Load, kConst, 2, 3);
    one(mem, Engine::Load, 0, 3, 2);
    mem.finalize();
    const std::string jm = profile_json(mem);
    CHECK(has(jm, "\"cp_raw\": 2"));
    CHECK(has(jm, "\"cp_mem\": 3"));
    CHECK(has(jm, "\"ready_not_issued\""));
    CHECK(has(jm, "\"top_slack\""));
}

void test_phase_and_named() {
    Program p;
    one(p, Engine::Load, kConst, 0, 1);
    one(p, Engine::Load, kConst, 1, 2);
    one(p, Engine::Alu, kAdd, 2, 0, 1);
    p.finalize();
    const std::uint8_t ph[] = {1, 2, 3};
    const std::uint32_t addr[] = {0, 1, 2};
    const std::uint16_t len[] = {1, 1, 1};
    const char* names[] = {"tmp_a", "tmp_b", "tmp_c"};
    ProfileExtra extra;
    extra.phase = ph;
    extra.n_phase = 3;
    extra.scratch_addr = addr;
    extra.scratch_len = len;
    extra.scratch_names = names;
    extra.n_scratch = 3;
    const std::string j = profile_json(p, nullptr, &extra);
    CHECK(has(j, "\"phase_init\": 1"));
    CHECK(has(j, "\"phase_ldst\": 1"));
    CHECK(has(j, "\"phase_hash\": 1"));
    CHECK(has(j, "tmp_a"));
    CHECK(has(j, "\"writes\": 1"));
}

void test_floor_prefers_valu_on_tie() {
    Program p;
    for (int i = 0; i < 6; ++i) {
        one(p, Engine::Valu, kValuAdd, static_cast<std::uint32_t>(i * 8), 0, 0);
    }
    one(p, Engine::Load, kConst, 0, 1);
    one(p, Engine::Load, kConst, 1, 2);
    p.finalize();
    const std::string j = profile_json(p);
    CHECK_EQ(jget(j, "cycles_est"), 8);
    CHECK_EQ(jget(j, "floor"), 1);
    CHECK(jstr(j, "floor_engine", "valu"));
    CHECK_EQ(jget(j, "overhead"), 7);
    CHECK_EQ(jget(j, "valu_ops"), 6);
    CHECK_EQ(jget(j, "load_ops"), 2);
}

void test_floor_load_heavy_consts() {
    Program p;
    for (int i = 0; i < 32; ++i) one(p, Engine::Load, kConst, static_cast<std::uint32_t>(i), 1);
    p.finalize();
    const std::string j = profile_json(p);
    CHECK_EQ(jget(j, "cycles_est"), 32);
    CHECK_EQ(jget(j, "floor"), 16);
    CHECK(jstr(j, "floor_engine", "load"));
    CHECK_EQ(jget(j, "overhead"), 16);
    CHECK(jstr(j, "mix_imbalance", "load_heavy"));
    CHECK_EQ(jget(j, "valu_hungry"), 32);
    CHECK_EQ(jget(j, "empty"), 0);
    CHECK(has(j, "\"tag\": \"pipeline\""));
    CHECK(has(j, "\"tag\": \"oneslot\""));
}

void test_flow_heavy_floor() {
    Program p;
    for (int i = 0; i < 12; ++i) one(p, Engine::Flow, kSelect, 0, 0, 0, 0);
    p.finalize();
    const std::string j = profile_json(p);
    CHECK_EQ(jget(j, "cycles_est"), 12);
    CHECK_EQ(jget(j, "floor"), 12);
    CHECK(jstr(j, "floor_engine", "flow"));
    CHECK_EQ(jget(j, "overhead"), 0);
    CHECK(jstr(j, "mix_imbalance", "flow_heavy"));
    CHECK_EQ(jget(j, "select_ops"), 12);
    CHECK(has(j, "\"tag\": \"control_bounds\""));
}

void test_packed_load_full_and_sat() {
    Program p;
    p.begin_bundle();
    p.add(Engine::Load, kConst, 0, 1);
    p.add(Engine::Load, kConst, 1, 2);
    p.end_bundle();
    p.finalize();
    const std::string j = profile_json(p);
    CHECK_EQ(jget(j, "cycles_est"), 1);
    CHECK_EQ(jget(j, "slots"), 2);
    CHECK_EQ(jget(j, "floor"), 1);
    CHECK(jstr(j, "floor_engine", "load"));
    CHECK_EQ(jget(j, "overhead"), 0);
    CHECK_EQ(jget(j, "saturation_cycles"), 1);
    CHECK(has(j, "\"port_full\""));
}

void test_valu_bundle_saturates() {
    Program p;
    p.begin_bundle();
    for (int i = 0; i < 6; ++i) {
        p.add(Engine::Valu, kValuAdd, static_cast<std::uint32_t>(i * 8), 0, 0);
    }
    p.end_bundle();
    p.finalize();
    const std::string j = profile_json(p);
    CHECK_EQ(jget(j, "cycles_est"), 1);
    CHECK_EQ(jget(j, "valu_ops"), 6);
    CHECK_EQ(jget(j, "floor"), 1);
    CHECK(jstr(j, "floor_engine", "valu"));
    CHECK_EQ(jget(j, "saturation_cycles"), 1);
    CHECK_EQ(jget(j, "overhead"), 0);
    CHECK(jstr(j, "floor_engine", "valu"));
}

void test_valu_heavy_mix() {
    Program p;
    for (int i = 0; i < 18; ++i) {
        one(p, Engine::Valu, kValuAdd, static_cast<std::uint32_t>(i * 8), 0, 0);
    }
    p.finalize();
    const std::string j = profile_json(p);
    CHECK_EQ(jget(j, "floor"), 3);
    CHECK(jstr(j, "floor_engine", "valu"));
    CHECK(jstr(j, "mix_imbalance", "valu_heavy"));
}

void test_gather_select_and_madd_counts() {
    Program p;
    one(p, Engine::Load, kConst, 0, 10);
    one(p, Engine::Load, kLoad, 1, 0);
    one(p, Engine::Load, kLoad, 2, 0);
    one(p, Engine::Load, kVLoad, 8, 0);
    one(p, Engine::Flow, kVSelect, 16, 1, 8, 8);
    one(p, Engine::Flow, kSelect, 3, 1, 2, 1);
    one(p, Engine::Valu, kValuMadd, 24, 8, 8, 8);
    p.finalize();
    const std::string j = profile_json(p);
    CHECK_EQ(jget(j, "gather_scalar"), 2);
    CHECK_EQ(jget(j, "vload_ops"), 1);
    CHECK_EQ(jget(j, "vselect_ops"), 1);
    CHECK_EQ(jget(j, "select_ops"), 1);
    CHECK_EQ(jget(j, "madd_ops"), 1);
    CHECK_EQ(jget(j, "const_ops"), 1);
    CHECK(has(j, "\"prefer\": \"select\""));
    CHECK(has(j, "\"prefer\": \"gather\""));
    CHECK(has(j, "\"level\": 0"));
    CHECK(has(j, "\"level\": 5"));
}

void test_gather_hypothesis_needs_many_loads() {
    Program p;
    one(p, Engine::Load, kConst, 0, 1);
    for (int i = 0; i < 10; ++i) one(p, Engine::Load, kLoad, static_cast<std::uint32_t>(i + 1), 0);
    p.finalize();
    const std::string j = profile_json(p);
    CHECK_EQ(jget(j, "gather_scalar"), 10);
    CHECK_EQ(jget(j, "vselect_ops"), 0);
    CHECK(has(j, "\"tag\": \"gather\""));
    CHECK(has(j, "\"tag\": \"memory_layout\""));
    CHECK(has(j, "\"tag\": \"valu_unused\""));
}

void test_top_slack_skips_pause() {
    Program p;
    one(p, Engine::Flow, kPause);
    one(p, Engine::Load, kConst, 0, 1);
    one(p, Engine::Load, kConst, 1, 2);
    one(p, Engine::Alu, kAdd, 2, 0, 1);
    p.finalize();
    const std::string j = profile_json(p);
    const auto slack_at = j.find("\"top_slack\"");
    const auto named_at = j.find("\"named_live\"");
    CHECK(slack_at != std::string::npos);
    CHECK(named_at != std::string::npos && named_at > slack_at);
    const std::string slack = j.substr(slack_at, named_at - slack_at);
    CHECK(slack.find("flow.pause") == std::string::npos);
}

void test_diff_floor_and_gather() {
    Program loads;
    for (int i = 0; i < 8; ++i) one(loads, Engine::Load, kLoad, static_cast<std::uint32_t>(i), 0);
    loads.finalize();
    const std::string a = profile_json(loads);
    CHECK(jstr(a, "floor_engine", "load"));

    Program valu;
    for (int i = 0; i < 12; ++i) {
        one(valu, Engine::Valu, kValuAdd, static_cast<std::uint32_t>(i * 8), 0, 0);
    }
    valu.finalize();
    const std::string b = profile_json(valu, a.c_str());
    CHECK(jstr(b, "floor_engine", "valu"));
    CHECK(has(b, "\"floor_engine_changed\": true"));
    CHECK(has(b, "\"same_program\": false"));
    CHECK(has(b, "\"gather_scalar\": -8"));
}

void test_waw_hypothesis() {
    Program p;
    for (int i = 0; i < 20; ++i) one(p, Engine::Load, kConst, 0, static_cast<std::uint32_t>(i + 1));
    p.finalize();
    const std::string j = profile_json(p);
    CHECK_EQ(jget(j, "cp_raw"), 1);
    CHECK_EQ(jget(j, "cp_waw"), 20);
    CHECK(has(j, "\"tag\": \"store_lifetime\""));
}

void test_scratch_peak() {
    Program p;
    one(p, Engine::Load, kConst, 0, 1);
    one(p, Engine::Load, kConst, 1, 2);
    one(p, Engine::Alu, kAdd, 2, 0, 1);
    p.finalize();
    const std::string j = profile_json(p);
    CHECK(has(j, "\"peak_live\": 3"));
    CHECK(has(j, "\"cells_touched\": 3"));
}

void test_gather_depth_and_bounds() {
    Program p;
    for (int i = 0; i < 4; ++i) one(p, Engine::Load, kLoad, static_cast<std::uint32_t>(i), 0);
    p.finalize();
    const std::uint8_t ph[] = {6, 6, 6, 6};
    const std::uint8_t dep[] = {0, 0, 1, 2};
    ProfileExtra extra;
    extra.phase = ph;
    extra.n_phase = 4;
    extra.depth = dep;
    extra.n_depth = 4;
    extra.forest_height = 10;
    extra.rounds = 16;
    extra.batch_size = 256;
    const std::string j = profile_json(p, nullptr, &extra);
    CHECK_EQ(jget(j, "phase_gather"), 4);
    CHECK_EQ(jget(j, "gather_floor_all_scalar"), 2048);
    CHECK_EQ(jget(j, "useful_op_floor"), 1093);
    CHECK_EQ(jget(j, "fused_hash_floor"), 1024);
    CHECK(has(j, "\"gathers_by_depth\""));
    CHECK(has(j, "\"0\": {\"gathers\": 2"));
    CHECK(has(j, "\"alu_class\""));
    CHECK(has(j, "\"scratch_vectors\""));
    CHECK(has(j, "\"capacity_vecs\": 192"));
    CHECK(has(j, "\"integrity\""));
    CHECK(has(j, "\"hash_ops_present\": false"));
    CHECK(has(j, "\"suspect_cheat\": true"));
    CHECK(has(j, "\"rle\""));
    CHECK(has(j, "\"gather\": 4"));
    CHECK(has(j, "\"regions\""));
    CHECK(has(j, "\"occupancy_hist\""));
    CHECK(has(j, "\"ii_est\""));
    CHECK(has(j, "\"wavefront\""));
}

void test_schedule_metrics() {
    Program chain;
    one(chain, Engine::Load, kConst, 0, 1);
    one(chain, Engine::Load, kConst, 1, 2);
    one(chain, Engine::Alu, kAdd, 2, 0, 1);
    one(chain, Engine::Load, kConst, 3, 0);
    one(chain, Engine::Store, kStore, 3, 2);
    chain.finalize();
    const std::string jc = profile_json(chain);
    CHECK_EQ(jget(jc, "cycles_est"), 5);
    CHECK_EQ(jget(jc, "zero_load_cycles"), 2);
    CHECK_EQ(jget(jc, "load0_valu_lt6"), 2);
    CHECK_EQ(jget(jc, "startup_end"), 0);
    CHECK_EQ(jget(jc, "drain_start"), 5);
    CHECK(has(jc, "\"load\": {\"limit\": 2, \"mean_used\":"));
    CHECK(has(jc, "\"hist\": [2, 3, 0]"));
    CHECK(has(jc, "\"hist\": [4, 1, 0"));
    CHECK(has(jc, "\"occupancy_series\": {\"n\": 0"));
    CHECK(has(jc, "\"pressure\""));
    CHECK(has(jc, "\"load_to_use_hist\""));
    CHECK(has(jc, "\"wavefront\""));
    CHECK(has(jc, "\"live_overlaps\""));

    Program packed;
    packed.begin_bundle();
    packed.add(Engine::Load, kConst, 0, 1);
    packed.add(Engine::Load, kConst, 1, 2);
    packed.end_bundle();
    packed.finalize();
    const std::string jp = profile_json(packed);
    CHECK_EQ(jget(jp, "zero_load_cycles"), 0);
    CHECK_EQ(jget(jp, "load0_valu_lt6"), 0);
    CHECK(has(jp, "\"hist\": [0, 0, 1]"));
    CHECK(has(jp, "\"limit\": 2"));

    Program valu;
    valu.begin_bundle();
    for (int i = 0; i < 6; ++i) {
        valu.add(Engine::Valu, kValuAdd, static_cast<std::uint32_t>(i * 8), 0, 0);
    }
    valu.end_bundle();
    valu.finalize();
    const std::string jv = profile_json(valu);
    CHECK_EQ(jget(jv, "zero_load_cycles"), 1);
    CHECK_EQ(jget(jv, "load0_valu_lt6"), 0);
    CHECK(has(jv, "\"hist\": [0, 0, 0, 0, 0, 0, 1]"));
    CHECK(has(jv, "\"limit\": 6"));
    CHECK(has(jv, "\"occupancy_series\": {\"n\": 1"));

    Program war;
    war.begin_bundle();
    war.add(Engine::Alu, kAdd, 2, 0, 1);
    war.add(Engine::Load, kConst, 0, 9);
    war.end_bundle();
    war.finalize();
    CHECK_EQ(jget(profile_json(war), "war_same_cycle"), 1);

    Program lu;
    one(lu, Engine::Load, kConst, 0, 10);
    one(lu, Engine::Load, kLoad, 1, 0);
    one(lu, Engine::Alu, kAdd, 2, 1, 1);
    lu.finalize();
    const std::string jl = profile_json(lu);
    CHECK_EQ(jget(jl, "load_to_use_n"), 1);
    CHECK_EQ(jget(jl, "load_to_use_p50"), 1);
    CHECK_EQ(jget(jl, "load_to_use_p95"), 1);
    CHECK(has(jl, "\"1\": 1"));

    Program reg;
    for (int i = 0; i < 6; ++i) one(reg, Engine::Load, kConst, static_cast<std::uint32_t>(i), 1);
    reg.finalize();
    const std::uint8_t ph[] = {1, 1, 3, 3, 3, 1};
    ProfileExtra extra;
    extra.phase = ph;
    extra.n_phase = 6;
    extra.rounds = 3;
    extra.batch_size = 2;
    const std::string jr = profile_json(reg, nullptr, &extra);
    CHECK_EQ(jget(jr, "startup_end"), 2);
    CHECK_EQ(jget(jr, "drain_start"), 5);
    CHECK_EQ(jget(jr, "item_rounds"), 6);
    CHECK(has(jr, "\"ii_est\": 0.5000"));
    CHECK(has(jr, "\"steady_cycles\": 3"));
    CHECK(has(jr, "\"hash\": 3"));

    Program ov;
    one(ov, Engine::Load, kConst, 0, 1);
    one(ov, Engine::Load, kConst, 1, 2);
    one(ov, Engine::Alu, kAdd, 2, 0, 1);
    ov.finalize();
    const std::uint32_t addr[] = {0, 1, 2};
    const std::uint16_t len[] = {1, 1, 1};
    const char* names[] = {"tmp_a", "tmp_b", "tmp_c"};
    ProfileExtra named;
    named.scratch_addr = addr;
    named.scratch_len = len;
    named.scratch_names = names;
    named.n_scratch = 3;
    const std::string jo = profile_json(ov, nullptr, &named);
    CHECK_EQ(jget(jo, "war_named_overlaps"), 3);
    CHECK(has(jo, "\"live_overlaps\""));
    CHECK(has(jo, "tmp_a"));
    CHECK(has(jo, "tmp_b"));

    Program longp;
    for (int i = 0; i < 300; ++i) {
        one(longp, Engine::Load, kConst, static_cast<std::uint32_t>(i % 64), 1);
    }
    longp.finalize();
    const std::string jn = profile_json(longp);
    CHECK(has(jn, "\"occupancy_series\": {\"n\": 0"));
    CHECK(has(jn, "\"limit\": 2"));
}

void test_schema_keys() {
    Program p;
    one(p, Engine::Load, kConst, 0, 1);
    p.finalize();
    const std::string j = profile_json(p);
    const char* keys[] = {
        "fingerprint", "assumes_linear", "has_jumps", "cycles_est", "ipc",
        "floor", "floor_engine", "overhead", "overhead_frac", "cp_raw", "cp_waw",
        "cp_mem", "alu_ops", "valu_ops", "load_ops", "zero_load_cycles",
        "load0_valu_lt6", "war_same_cycle", "engines", "phases", "mix", "bounds",
        "alu_class", "scratch_vectors", "pipeline", "regions", "occupancy_hist",
        "occupancy_series", "pressure", "live_overlaps", "integrity",
        "select_vs_gather", "hypotheses", "top_ops", "top_slack", "named_live",
        "hints", "port_full", "limit_engine", "ready_not_issued",
    };
    for (const char* k : keys) CHECK(has(j, k));
}

void test_oneslot_identities() {
    Program p;
    for (int i = 0; i < 8; ++i) one(p, Engine::Load, kConst, static_cast<std::uint32_t>(i), 1);
    p.finalize();
    const std::string j = profile_json(p);
    CHECK_EQ(jget(j, "cycles_est"), 8);
    CHECK_EQ(jget(j, "load_ops"), 8);
    CHECK_EQ(jget(j, "zero_load_cycles"), 0);
    CHECK_EQ(jget(j, "load0_valu_lt6"), 0);
    CHECK(has(j, "\"hist\": [0, 8, 0]"));
    CHECK(has(j, "\"occupancy_series\": {\"n\": 0"));
}

void test_full_valu_no_load() {
    Program p;
    p.begin_bundle();
    for (int i = 0; i < 6; ++i) p.add(Engine::Valu, kValuAdd, static_cast<std::uint32_t>(i * 8), 0, 0);
    p.end_bundle();
    one(p, Engine::Load, kConst, 48, 1);
    p.begin_bundle();
    for (int i = 0; i < 6; ++i) {
        p.add(Engine::Valu, kValuAdd, static_cast<std::uint32_t>(64 + i * 8), 0, 0);
    }
    p.end_bundle();
    p.finalize();
    const std::string j = profile_json(p);
    CHECK_EQ(jget(j, "cycles_est"), 3);
    CHECK_EQ(jget(j, "zero_load_cycles"), 2);
    CHECK_EQ(jget(j, "load0_valu_lt6"), 0);
    CHECK(has(j, "\"hist\": [1, 0, 0, 0, 0, 0, 2]"));
}

void test_drain_trailing_idle() {
    Program p;
    one(p, Engine::Load, kConst, 0, 1);
    one(p, Engine::Alu, kAdd, 1, 0, 0);
    one(p, Engine::Flow, kPause);
    one(p, Engine::Flow, kPause);
    p.finalize();
    const std::string j = profile_json(p);
    CHECK_EQ(jget(j, "startup_end"), 0);
    CHECK_EQ(jget(j, "drain_start"), 2);
    CHECK_EQ(jget(j, "flow_ops"), 2);
}

void test_series_gate() {
    Program low;
    for (int b = 0; b < 10; ++b) {
        low.begin_bundle();
        for (int i = 0; i < 6; ++i) {
            low.add(Engine::Valu, kValuAdd, static_cast<std::uint32_t>(b * 48 + i * 8), 0, 0);
        }
        low.end_bundle();
    }
    one(low, Engine::Load, kConst, 800, 1);
    one(low, Engine::Load, kConst, 801, 2);
    low.finalize();
    const std::string jl = profile_json(low);
    CHECK(has(jl, "\"occupancy_series\": {\"n\": 12"));

    Program high;
    for (int i = 0; i < 18; ++i) {
        one(high, Engine::Valu, kValuAdd, static_cast<std::uint32_t>(i * 8), 0, 0);
    }
    high.finalize();
    CHECK(has(profile_json(high), "\"occupancy_series\": {\"n\": 0"));
}

void test_unused_and_pressure() {
    Program p;
    one(p, Engine::Load, kConst, 0, 1);
    one(p, Engine::Load, kConst, 1, 2);
    one(p, Engine::Alu, kAdd, 2, 0, 1);
    p.finalize();
    const std::string j = profile_json(p);
    CHECK_EQ(jget(j, "peak_live"), 3);
    CHECK(has(j, "\"peak\": 3"));
    CHECK(has(j, "\"valu_unused_slots\": 18"));
    CHECK(has(j, "\"load_unused_slots\": 4"));
}

void test_jump_and_integrity() {
    Program jmp;
    one(jmp, Engine::Load, kConst, 0, 1);
    one(jmp, Engine::Flow, 8, 0, 0);
    jmp.finalize();
    const std::string jj = profile_json(jmp);
    CHECK(has(jj, "\"has_jumps\": true"));
    CHECK(has(jj, "\"assumes_linear\": false"));

    Program cheat;
    for (int i = 0; i < 4; ++i) one(cheat, Engine::Load, kLoad, static_cast<std::uint32_t>(i), 0);
    cheat.finalize();
    ProfileExtra extra;
    extra.forest_height = 10;
    extra.rounds = 16;
    extra.batch_size = 8;
    const std::string jc = profile_json(cheat, nullptr, &extra);
    CHECK(has(jc, "\"suspect_skip_hash\": true"));
    CHECK(has(jc, "\"suspect_cheat\": true"));
    CHECK(has(jc, "\"hash_ops_present\": false"));
}

void test_empty_and_debug_only() {
    Program empty;
    empty.finalize();
    const std::string je = profile_json(empty);
    CHECK_EQ(jget(je, "cycles_est"), 0);
    CHECK_EQ(jget(je, "slots"), 0);

    Program dbg;
    one(dbg, Engine::Debug, 2);
    dbg.finalize();
    const std::string jd = profile_json(dbg);
    CHECK_EQ(jget(jd, "cycles_est"), 0);
    CHECK_EQ(jget(jd, "debug_bundles"), 1);
}

void test_fingerprint_stable() {
    Program a;
    one(a, Engine::Load, kConst, 0, 7);
    a.finalize();
    const std::string ja = profile_json(a);
    const std::string jb = profile_json(a);
    CHECK(has(jb, "\"fingerprint\""));
    const auto pa = ja.find("\"fingerprint\": \"");
    const auto pb = jb.find("\"fingerprint\": \"");
    CHECK(pa != std::string::npos && pb != std::string::npos);
    CHECK(ja.substr(pa, 32) == jb.substr(pb, 32));
}

}  // namespace

int main() {
    std::printf("profiler tests\n");
    test_dep_chain();
    test_packed_bundle();
    test_debug_skips_cycle();
    test_diff_and_fingerprint();
    test_independent_consts_are_schedule();
    test_scratch_peak();
    test_cp_split_waw_and_mem();
    test_phase_and_named();
    test_floor_prefers_valu_on_tie();
    test_floor_load_heavy_consts();
    test_flow_heavy_floor();
    test_packed_load_full_and_sat();
    test_valu_bundle_saturates();
    test_valu_heavy_mix();
    test_gather_select_and_madd_counts();
    test_gather_hypothesis_needs_many_loads();
    test_top_slack_skips_pause();
    test_diff_floor_and_gather();
    test_waw_hypothesis();
    test_gather_depth_and_bounds();
    test_schedule_metrics();
    test_schema_keys();
    test_oneslot_identities();
    test_full_valu_no_load();
    test_drain_trailing_idle();
    test_series_gate();
    test_unused_and_pressure();
    test_jump_and_integrity();
    test_empty_and_debug_only();
    test_fingerprint_stable();
    return vliw_test::report("profiler");
}
