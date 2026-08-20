#include "machine.hpp"
#include "test_util.hpp"

#include <array>
#include <cstdint>
#include <cstdio>
#include <span>
#include <vector>

using vliw::Bundle;
using vliw::decode_op;
using vliw::Engine;
using vliw::kFlagNonDebug;
using vliw::kFlagSingle;
using vliw::kVlen;
using vliw::Machine;
using vliw::Op;
using vliw::Program;
using vliw::State;

namespace {

constexpr std::uint8_t kAdd = 0;
constexpr std::uint8_t kSub = 1;
constexpr std::uint8_t kMul = 2;
constexpr std::uint8_t kDiv = 3;
constexpr std::uint8_t kCdiv = 4;
constexpr std::uint8_t kXor = 5;
constexpr std::uint8_t kAnd = 6;
constexpr std::uint8_t kOr = 7;
constexpr std::uint8_t kShl = 8;
constexpr std::uint8_t kShr = 9;
constexpr std::uint8_t kMod = 10;
constexpr std::uint8_t kLt = 11;
constexpr std::uint8_t kEq = 12;
constexpr std::uint8_t kLoad = 0;
constexpr std::uint8_t kLoadOff = 1;
constexpr std::uint8_t kVLoad = 2;
constexpr std::uint8_t kConst = 3;
constexpr std::uint8_t kStore = 0;
constexpr std::uint8_t kVStore = 1;
constexpr std::uint8_t kSelect = 0;
constexpr std::uint8_t kAddImm = 1;
constexpr std::uint8_t kVSelect = 2;
constexpr std::uint8_t kHalt = 3;
constexpr std::uint8_t kPause = 4;
constexpr std::uint8_t kTrace = 5;
constexpr std::uint8_t kCJump = 6;
constexpr std::uint8_t kCJumpRel = 7;
constexpr std::uint8_t kJump = 8;
constexpr std::uint8_t kJumpInd = 9;
constexpr std::uint8_t kCoreId = 10;
constexpr std::uint8_t kBroadcast = 13;
constexpr std::uint8_t kMadd = 14;
constexpr std::uint8_t kDbgCmp = 0;
constexpr std::uint8_t kDbgVCmp = 1;
constexpr std::uint8_t kDbgNop = 2;

enum class Path : int { Checked = 0, Fast = 1, Linear = 2 };

void one(Program& p, Engine e, std::uint8_t op, std::uint32_t dest = 0, std::uint32_t a = 0,
         std::uint32_t b = 0, std::uint32_t c = 0) {
    p.begin_bundle();
    p.add(e, op, dest, a, b, c);
    p.end_bundle();
}

void apply_path(Machine& m, Path path) {
    if (path == Path::Fast) m.set_enable_debug(false);
    if (path == Path::Linear) {
        m.set_enable_debug(false);
        m.set_enable_pause(false);
    }
}

Machine run_prog(const Program& prog, std::span<const std::uint32_t> mem, Path path,
                 int n_cores = 1) {
    Machine m(mem, prog, n_cores);
    apply_path(m, path);
    m.run();
    return m;
}

template <typename Fn>
void each_path(Fn&& fn) {
    fn(Path::Checked);
    fn(Path::Fast);
    fn(Path::Linear);
}

std::uint32_t ref_alu(std::uint8_t kind, std::uint32_t a1, std::uint32_t a2) {
    switch (kind) {
        case kAdd:
            return a1 + a2;
        case kSub:
            return a1 - a2;
        case kMul:
            return a1 * a2;
        case kDiv:
            return a2 ? a1 / a2 : 0u;
        case kCdiv: {
            if (a2 == 0) return 0;
            const std::uint64_t num =
                static_cast<std::uint64_t>(a1) + static_cast<std::uint64_t>(a2) - 1;
            return static_cast<std::uint32_t>(num / a2);
        }
        case kXor:
            return a1 ^ a2;
        case kAnd:
            return a1 & a2;
        case kOr:
            return a1 | a2;
        case kShl:
            return a2 >= 32 ? 0u : (a1 << a2);
        case kShr:
            return a2 >= 32 ? 0u : (a1 >> a2);
        case kMod:
            return a2 ? a1 % a2 : 0u;
        case kLt:
            return a1 < a2 ? 1u : 0u;
        case kEq:
            return a1 == a2 ? 1u : 0u;
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
        const std::uint32_t t1 = ref_alu(op1[i], a, v1[i]);
        const std::uint32_t t2 = ref_alu(op3[i], a, v3[i]);
        a = ref_alu(op2[i], t1, t2);
    }
    return a;
}

// --- decode / program construction ---

void test_decode_op_tables() {
    CHECK(decode_op(Engine::Alu, kAdd) == Op::AluAdd);
    CHECK(decode_op(Engine::Alu, kEq) == Op::AluEq);
    CHECK(decode_op(Engine::Valu, kAdd) == Op::ValuAdd);
    CHECK(decode_op(Engine::Valu, kBroadcast) == Op::ValuBroadcast);
    CHECK(decode_op(Engine::Valu, kMadd) == Op::ValuMadd);
    CHECK(decode_op(Engine::Load, kLoad) == Op::Load);
    CHECK(decode_op(Engine::Load, kLoadOff) == Op::LoadOffset);
    CHECK(decode_op(Engine::Load, kVLoad) == Op::VLoad);
    CHECK(decode_op(Engine::Load, kConst) == Op::Const);
    CHECK(decode_op(Engine::Store, kStore) == Op::Store);
    CHECK(decode_op(Engine::Store, kVStore) == Op::VStore);
    CHECK(decode_op(Engine::Flow, kSelect) == Op::Select);
    CHECK(decode_op(Engine::Flow, kCoreId) == Op::CoreId);
    CHECK(decode_op(Engine::Debug, kDbgCmp) == Op::DebugCompare);
    CHECK(decode_op(Engine::Debug, kDbgVCmp) == Op::DebugVCompare);
    CHECK(decode_op(Engine::Debug, kDbgNop) == Op::Nop);
    Program p;
    CHECK_THROWS(p.add(Engine::Alu, 13));
    CHECK_THROWS(p.add(Engine::Valu, 15));
    CHECK_THROWS(p.add(Engine::Load, 4));
    CHECK_THROWS(p.add(Engine::Store, 2));
    CHECK_THROWS(p.add(Engine::Flow, 11));
}

void test_slot_limits() {
    CHECK_EQ(vliw::kMaxSlotsPerBundle, 12 + 6 + 2 + 2 + 1 + 64);
    CHECK_EQ(vliw::kMaxScratchWrites, 12 + kVlen * (6 + 2 + 1));
    CHECK_EQ(vliw::kMaxMemWrites, kVlen * 2);

    Program alu;
    alu.begin_bundle();
    for (int i = 0; i < 12; ++i) alu.add(Engine::Alu, kAdd, 0, 0, 0);
    CHECK_THROWS(alu.add(Engine::Alu, kAdd, 0, 0, 0));

    Program valu;
    valu.begin_bundle();
    for (int i = 0; i < 6; ++i) valu.add(Engine::Valu, kAdd, 0, 0, 0);
    CHECK_THROWS(valu.add(Engine::Valu, kAdd, 0, 0, 0));

    Program load;
    load.begin_bundle();
    load.add(Engine::Load, kConst, 0, 1);
    load.add(Engine::Load, kConst, 1, 2);
    CHECK_THROWS(load.add(Engine::Load, kConst, 2, 3));

    Program flow;
    flow.begin_bundle();
    flow.add(Engine::Flow, kHalt);
    CHECK_THROWS(flow.add(Engine::Flow, kHalt));
}

void test_load_oneslot_matches_add() {
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
        {2, kConst, {}, 0, 40, 0, 0},
        {2, kConst, {}, 1, 2, 0, 0},
        {0, kAdd, {}, 2, 0, 1, 0},
        {4, kHalt, {}, 0, 0, 0, 0},
    };
    Program loaded;
    loaded.load_oneslot(raw, 4);
    CHECK_EQ(loaded.bundles.size(), 4);
    CHECK(loaded.linear_ok);
    CHECK_EQ(loaded.linear.size(), 4);
    CHECK_EQ(loaded.debug_key_count, 0);

    Program added;
    one(added, Engine::Load, kConst, 0, 40);
    one(added, Engine::Load, kConst, 1, 2);
    one(added, Engine::Alu, kAdd, 2, 0, 1);
    one(added, Engine::Flow, kHalt);
    const std::uint32_t mem0[] = {0};
    each_path([&](Path path) {
        auto a = run_prog(added, mem0, path);
        auto b = run_prog(loaded, mem0, path);
        CHECK_EQ(a.cores()[0].scratch[2], 42);
        CHECK_EQ(b.cores()[0].scratch[2], 42);
        CHECK_EQ(a.cycle(), b.cycle());
    });
}

void test_linear_ok_flags() {
    Program ok;
    one(ok, Engine::Load, kConst, 0, 1);
    one(ok, Engine::Debug, kDbgNop);
    one(ok, Engine::Alu, kAdd, 0, 0, 0);
    CHECK(ok.linear_ok);
    CHECK_EQ(ok.linear.size(), 2);

    Program jump;
    one(jump, Engine::Load, kConst, 0, 1);
    one(jump, Engine::Flow, kJump, 0, 0);
    CHECK(!jump.linear_ok);
    CHECK_EQ(jump.linear.size(), 0);

    Program multi;
    one(multi, Engine::Load, kConst, 0, 1);
    multi.begin_bundle();
    multi.add(Engine::Alu, kAdd, 0, 0, 0);
    multi.add(Engine::Alu, kAdd, 1, 0, 0);
    multi.end_bundle();
    CHECK(!multi.linear_ok);
}

void test_debug_keys_assigned() {
    Program p;
    one(p, Engine::Debug, kDbgCmp, 3);
    one(p, Engine::Debug, kDbgVCmp, 8);
    CHECK_EQ(p.debug_key_count, 1 + kVlen);
    CHECK_EQ(p.bundles[0].one.a, 0);
    CHECK_EQ(p.bundles[1].one.a, 1);
}

void test_ctor_rejects_bad_args() {
    Program p;
    one(p, Engine::Flow, kHalt);
    const std::uint32_t mem0[] = {0};
    CHECK_THROWS(Machine(mem0, p, 0));
    CHECK_THROWS(Machine(mem0, p, 1, 0));
    CHECK_THROWS(Machine(mem0, p, 1, 2000));
}

void test_empty_program_and_short_mem() {
    Program p;
    Machine m(std::span<const std::uint32_t>{}, p);
    CHECK(m.mem().size() >= 8);
    m.run();
    CHECK_EQ(m.cycle(), 0);
    CHECK(m.cores()[0].state == State::Stopped);
}

// --- ALU ---

void test_alu_table() {
    struct Case {
        std::uint8_t op;
        std::uint32_t a;
        std::uint32_t b;
    };
    const Case cases[] = {
        {kAdd, 40, 2},
        {kAdd, 0xFFFFFFFFu, 2},
        {kSub, 5, 8},
        {kMul, 7, 6},
        {kMul, 0x80000000u, 2},
        {kDiv, 10, 3},
        {kCdiv, 10, 3},
        {kCdiv, 0xFFFFFFFFu, 2},
        {kXor, 0xF0, 0x0F},
        {kAnd, 0xF0, 0x18},
        {kOr, 0xF0, 0x0F},
        {kShl, 1, 4},
        {kShl, 1, 32},
        {kShl, 5, 40},
        {kShr, 16, 2},
        {kShr, 16, 32},
        {kMod, 10, 3},
        {kLt, 1, 2},
        {kLt, 2, 1},
        {kEq, 7, 7},
        {kEq, 7, 8},
    };
    each_path([&](Path path) {
        for (const auto& c : cases) {
            Program p;
            one(p, Engine::Load, kConst, 0, c.a);
            one(p, Engine::Load, kConst, 1, c.b);
            one(p, Engine::Alu, c.op, 2, 0, 1);
            const std::uint32_t mem0[] = {0};
            auto m = run_prog(p, mem0, path);
            CHECK_EQ(m.cores()[0].scratch[2], ref_alu(c.op, c.a, c.b));
        }
    });
}

void test_div_zero_checked_throws_fast_is_zero() {
    const std::uint8_t ops[] = {kDiv, kMod, kCdiv};
    for (std::uint8_t op : ops) {
        Program p;
        one(p, Engine::Load, kConst, 0, 10);
        one(p, Engine::Load, kConst, 1, 0);
        one(p, Engine::Alu, op, 2, 0, 1);
        const std::uint32_t mem0[] = {0};
        CHECK_THROWS(run_prog(p, mem0, Path::Checked));
        auto fast = run_prog(p, mem0, Path::Fast);
        CHECK_EQ(fast.cores()[0].scratch[2], 0);
        auto linear = run_prog(p, mem0, Path::Linear);
        CHECK_EQ(linear.cores()[0].scratch[2], 0);
    }
}

void test_checked_oob_matches_oracle() {
    const std::uint32_t mem0[8] = {};
    {
        Program p;
        one(p, Engine::Load, kConst, 0, 99);
        one(p, Engine::Load, kLoad, 1, 0);
        CHECK_THROWS(run_prog(p, mem0, Path::Checked));
    }
    {
        Program p;
        one(p, Engine::Load, kConst, 0, 99);
        one(p, Engine::Load, kConst, 1, 1);
        one(p, Engine::Store, kStore, 0, 1);
        CHECK_THROWS(run_prog(p, mem0, Path::Checked));
    }
    {
        Program p;
        one(p, Engine::Load, kConst, 0, 1);
        one(p, Engine::Valu, kAdd, 1530, 0, 0);
        CHECK_THROWS(run_prog(p, mem0, Path::Checked));
    }
}

void test_deferred_scratch_write() {
    each_path([](Path path) {
        Program p;
        one(p, Engine::Load, kConst, 0, 5);
        one(p, Engine::Load, kConst, 1, 7);
        p.begin_bundle();
        p.add(Engine::Alu, kAdd, 0, 0, 1);
        p.add(Engine::Alu, kAdd, 2, 0, 0);
        p.end_bundle();
        const std::uint32_t mem0[] = {0};
        auto m = run_prog(p, mem0, path);
        CHECK_EQ(m.cores()[0].scratch[0], 12);
        CHECK_EQ(m.cores()[0].scratch[2], 10);
    });
}

// --- VALU ---

void test_valu_alu_ops() {
    each_path([](Path path) {
        Program p;
        for (int i = 0; i < kVlen; ++i) {
            one(p, Engine::Load, kConst, static_cast<std::uint32_t>(i), 10 + i);
            one(p, Engine::Load, kConst, static_cast<std::uint32_t>(8 + i), 3);
        }
        one(p, Engine::Valu, kAdd, 16, 0, 8);
        one(p, Engine::Valu, kXor, 24, 0, 8);
        const std::uint32_t mem0[] = {0};
        auto m = run_prog(p, mem0, path);
        for (int i = 0; i < kVlen; ++i) {
            CHECK_EQ(m.cores()[0].scratch[16 + i], static_cast<std::uint32_t>(13 + i));
            CHECK_EQ(m.cores()[0].scratch[24 + i], static_cast<std::uint32_t>((10 + i) ^ 3));
        }
    });
}

void test_valu_broadcast_madd() {
    each_path([](Path path) {
        Program p;
        one(p, Engine::Load, kConst, 0, 3);
        one(p, Engine::Valu, kBroadcast, 8, 0);
        for (int i = 0; i < kVlen; ++i)
            one(p, Engine::Load, kConst, static_cast<std::uint32_t>(16 + i), 2);
        one(p, Engine::Valu, kMadd, 24, 8, 16, 8);
        const std::uint32_t mem0[] = {0};
        auto m = run_prog(p, mem0, path);
        for (int i = 0; i < kVlen; ++i) CHECK_EQ(m.cores()[0].scratch[24 + i], 9);
    });
}

void test_valu_deferred() {
    each_path([](Path path) {
        Program p;
        for (int i = 0; i < kVlen; ++i) {
            one(p, Engine::Load, kConst, static_cast<std::uint32_t>(i), 1);
            one(p, Engine::Load, kConst, static_cast<std::uint32_t>(8 + i), 4);
        }
        p.begin_bundle();
        p.add(Engine::Valu, kAdd, 0, 0, 8);   // 5 into dest 0..7
        p.add(Engine::Valu, kAdd, 16, 0, 0);  // still sees old 1+1
        p.end_bundle();
        const std::uint32_t mem0[] = {0};
        auto m = run_prog(p, mem0, path);
        for (int i = 0; i < kVlen; ++i) {
            CHECK_EQ(m.cores()[0].scratch[i], 5);
            CHECK_EQ(m.cores()[0].scratch[16 + i], 2);
        }
    });
}

// --- load / store ---

void test_scalar_load_store() {
    each_path([](Path path) {
        std::vector<std::uint32_t> mem(8, 0);
        mem[4] = 77;
        Program p;
        one(p, Engine::Load, kConst, 0, 4);
        one(p, Engine::Load, kLoad, 1, 0);
        one(p, Engine::Load, kConst, 2, 5);
        one(p, Engine::Store, kStore, 2, 1);
        auto m = run_prog(p, mem, path);
        CHECK_EQ(m.mem()[5], 77);
        CHECK_EQ(m.cores()[0].scratch[1], 77);
    });
}

void test_load_offset() {
    each_path([](Path path) {
        std::vector<std::uint32_t> mem(32, 0);
        mem[20] = 77;
        Program p;
        one(p, Engine::Load, kConst, 8, 10);
        one(p, Engine::Load, kConst, 11, 20);
        one(p, Engine::Load, kLoadOff, 0, 8, 3);
        auto m = run_prog(p, mem, path);
        CHECK_EQ(m.cores()[0].scratch[3], 77);
    });
}

void test_peak_bundle_write_buffers() {
    Program p;
    p.begin_bundle();
    for (int i = 0; i < 12; ++i) p.add(Engine::Alu, kAdd, static_cast<std::uint32_t>(i), 0, 0);
    for (int i = 0; i < 6; ++i) {
        p.add(Engine::Valu, kAdd, static_cast<std::uint32_t>(32 + i * 8), 0, 0);
    }
    p.add(Engine::Load, kVLoad, 80, 0);
    p.add(Engine::Load, kVLoad, 88, 0);
    p.add(Engine::Store, kVStore, 0, 80);
    p.add(Engine::Store, kVStore, 0, 88);
    p.add(Engine::Flow, kVSelect, 96, 80, 80, 88);
    p.end_bundle();
    one(p, Engine::Flow, kHalt);
    const std::uint32_t mem0[32] = {};
    each_path([&](Path path) {
        auto m = run_prog(p, mem0, path);
        CHECK(m.cycle() >= 1);
    });
}

void test_vload_vstore() {
    each_path([](Path path) {
        std::vector<std::uint32_t> mem(32, 0);
        for (int i = 0; i < 8; ++i) mem[static_cast<std::size_t>(10 + i)] = 100 + i;
        Program p;
        one(p, Engine::Load, kConst, 0, 10);
        one(p, Engine::Load, kVLoad, 8, 0);
        one(p, Engine::Load, kConst, 1, 20);
        one(p, Engine::Store, kVStore, 1, 8);
        auto m = run_prog(p, mem, path);
        for (int i = 0; i < 8; ++i) CHECK_EQ(m.mem()[20 + i], static_cast<std::uint32_t>(100 + i));
    });
}

void test_deferred_mem_write() {
    each_path([](Path path) {
        std::vector<std::uint32_t> mem(8, 0);
        mem[0] = 99;
        Program p;
        one(p, Engine::Load, kConst, 1, 0);
        one(p, Engine::Load, kConst, 2, 7);
        p.begin_bundle();
        p.add(Engine::Store, kStore, 1, 2);
        p.add(Engine::Load, kLoad, 3, 1);
        p.end_bundle();
        auto m = run_prog(p, mem, path);
        CHECK_EQ(m.cores()[0].scratch[3], 99);
        CHECK_EQ(m.mem()[0], 7);
    });
}

// --- flow ---

void test_select_and_vselect() {
    each_path([](Path path) {
        Program p;
        one(p, Engine::Load, kConst, 0, 1);
        one(p, Engine::Load, kConst, 1, 9);
        one(p, Engine::Load, kConst, 2, 8);
        one(p, Engine::Flow, kSelect, 3, 0, 1, 2);
        one(p, Engine::Load, kConst, 4, 0);
        one(p, Engine::Flow, kSelect, 5, 4, 1, 2);
        for (int i = 0; i < kVlen; ++i) {
            one(p, Engine::Load, kConst, static_cast<std::uint32_t>(16 + i), i & 1);
            one(p, Engine::Load, kConst, static_cast<std::uint32_t>(24 + i), 10);
            one(p, Engine::Load, kConst, static_cast<std::uint32_t>(32 + i), 20);
        }
        one(p, Engine::Flow, kVSelect, 40, 16, 24, 32);
        const std::uint32_t mem0[] = {0};
        auto m = run_prog(p, mem0, path);
        CHECK_EQ(m.cores()[0].scratch[3], 9);
        CHECK_EQ(m.cores()[0].scratch[5], 8);
        for (int i = 0; i < kVlen; ++i) {
            const std::uint32_t want = (i & 1) ? 10u : 20u;
            CHECK_EQ(m.cores()[0].scratch[40 + i], want);
        }
    });
}

void test_add_imm_wrap() {
    each_path([](Path path) {
        Program p;
        one(p, Engine::Load, kConst, 0, 0xFFFFFFFFu);
        one(p, Engine::Flow, kAddImm, 1, 0, 2);
        const std::uint32_t mem0[] = {0};
        auto m = run_prog(p, mem0, path);
        CHECK_EQ(m.cores()[0].scratch[1], 1);
    });
}

void test_halt_skips_tail() {
    each_path([](Path path) {
        Program p;
        one(p, Engine::Load, kConst, 0, 1);
        one(p, Engine::Flow, kHalt);
        one(p, Engine::Load, kConst, 1, 99);
        const std::uint32_t mem0[] = {0};
        auto m = run_prog(p, mem0, path);
        CHECK_EQ(m.cores()[0].scratch[0], 1);
        CHECK_EQ(m.cores()[0].scratch[1], 0);
        CHECK(m.cores()[0].state == State::Stopped);
        CHECK_EQ(m.cycle(), 2);
    });
}

void test_pause_resume() {
    Program p;
    one(p, Engine::Load, kConst, 0, 1);
    one(p, Engine::Flow, kPause);
    one(p, Engine::Load, kConst, 1, 2);
    const std::uint32_t mem0[] = {0};
    Machine m(mem0, p);
    m.run();
    CHECK_EQ(m.cores()[0].scratch[0], 1);
    CHECK_EQ(m.cores()[0].scratch[1], 0);
    CHECK(m.cores()[0].state == State::Paused);
    CHECK_EQ(m.cycle(), 2);
    m.run();
    CHECK_EQ(m.cores()[0].scratch[1], 2);
    CHECK(m.cores()[0].state == State::Stopped);
}

void test_pause_disabled_is_nop() {
    each_path([](Path path) {
        if (path == Path::Checked) return;
        Program p;
        one(p, Engine::Load, kConst, 0, 1);
        one(p, Engine::Flow, kPause);
        one(p, Engine::Load, kConst, 1, 2);
        const std::uint32_t mem0[] = {0};
        Machine m(mem0, p);
        m.set_enable_pause(false);
        if (path == Path::Fast || path == Path::Linear) m.set_enable_debug(false);
        m.run();
        CHECK_EQ(m.cores()[0].scratch[1], 2);
        CHECK(m.cores()[0].state == State::Stopped);
        CHECK_EQ(m.cycle(), 3);
    });
    Program p;
    one(p, Engine::Load, kConst, 0, 1);
    one(p, Engine::Flow, kPause);
    one(p, Engine::Load, kConst, 1, 2);
    const std::uint32_t mem0[] = {0};
    Machine m(mem0, p);
    m.set_enable_pause(false);
    m.run();
    CHECK_EQ(m.cores()[0].scratch[1], 2);
}

void test_jump_absolute() {
    Program p;
    one(p, Engine::Load, kConst, 0, 1);
    one(p, Engine::Load, kConst, 1, 9);
    one(p, Engine::Load, kConst, 2, 8);
    one(p, Engine::Flow, kSelect, 3, 0, 1, 2);
    one(p, Engine::Flow, kJump, 0, 6);
    one(p, Engine::Load, kConst, 4, 99);
    one(p, Engine::Load, kConst, 4, 7);
    const std::uint32_t mem0[] = {0};
    for (auto path : {Path::Checked, Path::Fast}) {
        auto m = run_prog(p, mem0, path);
        CHECK_EQ(m.cores()[0].scratch[3], 9);
        CHECK_EQ(m.cores()[0].scratch[4], 7);
    }
}

void test_cond_jump_taken_and_not() {
    auto make = [](std::uint32_t cond) {
        Program p;
        one(p, Engine::Load, kConst, 0, cond);
        one(p, Engine::Flow, kCJump, 0, 0, 4);
        one(p, Engine::Load, kConst, 1, 99);
        one(p, Engine::Flow, kHalt);
        one(p, Engine::Load, kConst, 1, 7);
        one(p, Engine::Flow, kHalt);
        return p;
    };
    const std::uint32_t mem0[] = {0};
    for (auto path : {Path::Checked, Path::Fast}) {
        auto taken = run_prog(make(1), mem0, path);
        CHECK_EQ(taken.cores()[0].scratch[1], 7);
        auto not_taken = run_prog(make(0), mem0, path);
        CHECK_EQ(not_taken.cores()[0].scratch[1], 99);
    }
}

void test_cond_jump_rel() {
    Program p;
    one(p, Engine::Load, kConst, 0, 1);
    one(p, Engine::Flow, kCJumpRel, 0, 0, 2);
    one(p, Engine::Load, kConst, 1, 99);
    one(p, Engine::Flow, kHalt);
    one(p, Engine::Load, kConst, 1, 7);
    one(p, Engine::Flow, kHalt);
    const std::uint32_t mem0[] = {0};
    for (auto path : {Path::Checked, Path::Fast}) {
        auto m = run_prog(p, mem0, path);
        CHECK_EQ(m.cores()[0].scratch[1], 7);
    }
}

void test_jump_indirect() {
    Program p;
    one(p, Engine::Load, kConst, 0, 4);
    one(p, Engine::Flow, kJumpInd, 0, 0);
    one(p, Engine::Load, kConst, 1, 99);
    one(p, Engine::Flow, kHalt);
    one(p, Engine::Load, kConst, 1, 7);
    one(p, Engine::Flow, kHalt);
    const std::uint32_t mem0[] = {0};
    for (auto path : {Path::Checked, Path::Fast}) {
        auto m = run_prog(p, mem0, path);
        CHECK_EQ(m.cores()[0].scratch[1], 7);
    }
}

void test_coreid() {
    Program p;
    one(p, Engine::Flow, kCoreId, 0);
    one(p, Engine::Flow, kHalt);
    const std::uint32_t mem0[] = {0};
    each_path([&](Path path) {
        auto m = run_prog(p, mem0, path, 1);
        CHECK_EQ(m.cores()[0].scratch[0], 0);
    });
    auto m2 = run_prog(p, mem0, Path::Checked, 2);
    CHECK_EQ(m2.cores()[0].scratch[0], 0);
    CHECK_EQ(m2.cores()[1].scratch[0], 1);
    CHECK_EQ(m2.cycle(), 2);
}

void test_trace_write_all_paths() {
    Program p;
    one(p, Engine::Load, kConst, 0, 42);
    one(p, Engine::Flow, kTrace, 0, 0);
    const std::uint32_t mem0[] = {0};
    each_path([&](Path path) {
        auto m = run_prog(p, mem0, path);
        CHECK_EQ(m.cores()[0].trace_buf.size(), 1);
        CHECK_EQ(m.cores()[0].trace_buf[0], 42);
    });
}

void test_multicore_coreid_branch() {
    Program p;
    one(p, Engine::Flow, kCoreId, 0);
    one(p, Engine::Flow, kCJump, 0, 0, 4);
    one(p, Engine::Load, kConst, 1, 10);
    one(p, Engine::Flow, kHalt);
    one(p, Engine::Load, kConst, 1, 20);
    one(p, Engine::Flow, kHalt);
    const std::uint32_t mem0[] = {0};
    auto m = run_prog(p, mem0, Path::Checked, 2);
    CHECK_EQ(m.cores()[0].scratch[1], 10);
    CHECK_EQ(m.cores()[1].scratch[1], 20);
    CHECK_EQ(m.cycle(), 4);
}

// --- debug / cycles ---

void test_debug_only_no_cycle() {
    each_path([](Path path) {
        Program p;
        one(p, Engine::Load, kConst, 0, 1);
        one(p, Engine::Debug, kDbgNop);
        const std::uint32_t mem0[] = {0};
        auto m = run_prog(p, mem0, path);
        CHECK_EQ(m.cycle(), 1);
    });
}

void test_debug_compare_match_and_mismatch() {
    Program p;
    one(p, Engine::Load, kConst, 0, 7);
    one(p, Engine::Debug, kDbgCmp, 0);
    const std::uint32_t mem0[] = {0};
    const std::uint32_t ok[] = {7};
    const std::uint8_t present[] = {1};
    Machine good(mem0, p);
    good.set_debug_expected(ok, present);
    good.run();
    CHECK_EQ(good.cores()[0].scratch[0], 7);

    const std::uint32_t bad[] = {8};
    Machine fail(mem0, p);
    fail.set_debug_expected(bad, present);
    CHECK_THROWS(fail.run());
}

void test_debug_compare_skipped_when_disabled() {
    Program p;
    one(p, Engine::Load, kConst, 0, 7);
    one(p, Engine::Debug, kDbgCmp, 0);
    const std::uint32_t mem0[] = {0};
    const std::uint32_t bad[] = {8};
    const std::uint8_t present[] = {1};
    Machine m(mem0, p);
    m.set_debug_expected(bad, present);
    m.set_enable_debug(false);
    m.run();
    CHECK_EQ(m.cores()[0].scratch[0], 7);
}

void test_debug_vcompare() {
    Program p;
    for (int i = 0; i < kVlen; ++i)
        one(p, Engine::Load, kConst, static_cast<std::uint32_t>(i), 10 + i);
    one(p, Engine::Debug, kDbgVCmp, 0);
    const std::uint32_t mem0[] = {0};
    std::array<std::uint32_t, 8> vals{};
    std::array<std::uint8_t, 8> present{};
    for (int i = 0; i < kVlen; ++i) {
        vals[static_cast<std::size_t>(i)] = 10 + i;
        present[static_cast<std::size_t>(i)] = 1;
    }
    Machine m(mem0, p);
    m.set_debug_expected(vals, present);
    m.run();
    CHECK_EQ(m.cores()[0].scratch[3], 13);
}

void test_debug_in_bundle_reads_old_scratch() {
    Program p;
    one(p, Engine::Load, kConst, 0, 3);
    one(p, Engine::Load, kConst, 1, 4);
    p.begin_bundle();
    p.add(Engine::Alu, kAdd, 2, 0, 1);
    p.add(Engine::Debug, kDbgCmp, 2);
    p.end_bundle();
    const std::uint32_t mem0[] = {0};
    const std::uint32_t old_zero[] = {0};
    const std::uint8_t present[] = {1};
    Machine m(mem0, p);
    m.set_debug_expected(old_zero, present);
    m.run();
    CHECK_EQ(m.cores()[0].scratch[2], 7);
}

// --- paths agree ---

void test_hash_all_paths() {
    const std::uint32_t input = 0x12345678u ^ 0x11111111u;
    Program p;
    one(p, Engine::Load, kConst, 0, input);
    for (int i = 0; i < 6; ++i) {
        const std::uint8_t op1[] = {kAdd, kXor, kAdd, kAdd, kAdd, kXor};
        const std::uint32_t v1[] = {0x7ED55D16u, 0xC761C23Cu, 0x165667B1u, 0xD3A2646Cu,
                                    0xFD7046C5u, 0xB55A4F09u};
        const std::uint8_t op2[] = {kAdd, kXor, kAdd, kXor, kAdd, kXor};
        const std::uint8_t op3[] = {kShl, kShr, kShl, kShl, kShl, kShr};
        const std::uint32_t v3[] = {12, 19, 5, 9, 3, 16};
        const std::uint32_t c1 = static_cast<std::uint32_t>(10 + i * 2);
        const std::uint32_t c3 = static_cast<std::uint32_t>(11 + i * 2);
        one(p, Engine::Load, kConst, c1, v1[i]);
        one(p, Engine::Load, kConst, c3, v3[i]);
        one(p, Engine::Alu, op1[i], 1, 0, c1);
        one(p, Engine::Alu, op3[i], 2, 0, c3);
        one(p, Engine::Alu, op2[i], 0, 1, 2);
    }
    one(p, Engine::Load, kConst, 3, 0);
    one(p, Engine::Store, kStore, 3, 0);
    const std::uint32_t mem0[] = {0, 0, 0, 0, 0, 0, 0, 0};
    const std::uint32_t expect = myhash(input);
    std::uint64_t cycles = 0;
    each_path([&](Path path) {
        auto m = run_prog(p, mem0, path);
        CHECK_EQ(m.mem()[0], expect);
        if (cycles == 0) cycles = m.cycle();
        CHECK_EQ(m.cycle(), cycles);
    });
}

void test_linear_pause_counts_as_cycle() {
    Program p;
    one(p, Engine::Load, kConst, 0, 40);
    one(p, Engine::Load, kConst, 1, 2);
    one(p, Engine::Alu, kAdd, 2, 0, 1);
    one(p, Engine::Flow, kPause);
    one(p, Engine::Flow, kHalt);
    const std::uint32_t mem0[] = {0};
    auto m = run_prog(p, mem0, Path::Linear);
    CHECK_EQ(m.cores()[0].scratch[2], 42);
    CHECK_EQ(m.cycle(), 5);
    CHECK(m.cores()[0].state == State::Stopped);
}

}  // namespace

int main() {
    setvbuf(stdout, nullptr, _IONBF, 0);
    std::printf("[1/8] decode / program\n");
    test_decode_op_tables();
    test_slot_limits();
    test_load_oneslot_matches_add();
    test_linear_ok_flags();
    test_debug_keys_assigned();
    test_ctor_rejects_bad_args();
    test_empty_program_and_short_mem();

    std::printf("[2/8] alu\n");
    test_alu_table();
    test_div_zero_checked_throws_fast_is_zero();
    test_checked_oob_matches_oracle();
    test_deferred_scratch_write();

    std::printf("[3/8] valu\n");
    test_valu_alu_ops();
    test_valu_broadcast_madd();
    test_valu_deferred();

    std::printf("[4/8] load/store\n");
    test_scalar_load_store();
    test_load_offset();
    test_vload_vstore();
    test_peak_bundle_write_buffers();
    test_deferred_mem_write();

    std::printf("[5/8] flow\n");
    test_select_and_vselect();
    test_add_imm_wrap();
    test_halt_skips_tail();
    test_pause_resume();
    test_pause_disabled_is_nop();
    test_jump_absolute();
    test_cond_jump_taken_and_not();
    test_cond_jump_rel();
    test_jump_indirect();
    test_coreid();
    test_trace_write_all_paths();
    test_multicore_coreid_branch();

    std::printf("[6/8] debug / cycles\n");
    test_debug_only_no_cycle();
    test_debug_compare_match_and_mismatch();
    test_debug_compare_skipped_when_disabled();
    test_debug_vcompare();
    test_debug_in_bundle_reads_old_scratch();

    std::printf("[7/8] path agreement\n");
    test_hash_all_paths();
    test_linear_pause_counts_as_cycle();

    std::printf("[8/8] done\n");
    return vliw_test::report("engine_tests");
}
