#include "machine.hpp"

#include <utility>
#include <vector>

namespace vliw {
namespace {

#if defined(_MSC_VER)
#define VLIW_INLINE __forceinline
#else
#define VLIW_INLINE inline __attribute__((always_inline))
#endif

[[noreturn]] void fail(const char* msg) { throw std::runtime_error(msg); }

// Unchecked ALU, same spirit as durak::lowest: precondition is a valid op.
// Fast path: div/mod/cdiv by zero yields 0. Checked path matches Python and throws.
VLIW_INLINE std::uint32_t eval_alu(std::uint8_t kind, std::uint32_t a1, std::uint32_t a2,
                                   bool checked = false) {
    if (checked && a2 == 0 && (kind == 3 || kind == 4 || kind == 10)) {
        fail("alu div/mod by zero");
    }
    switch (kind) {
        case 0:
            return a1 + a2;
        case 1:
            return a1 - a2;
        case 2:
            return a1 * a2;
        case 3:
            return a2 ? a1 / a2 : 0u;
        case 4: {
            if (a2 == 0) return 0;
            const std::uint64_t num = static_cast<std::uint64_t>(a1) + static_cast<std::uint64_t>(a2) - 1;
            return static_cast<std::uint32_t>(num / a2);
        }
        case 5:
            return a1 ^ a2;
        case 6:
            return a1 & a2;
        case 7:
            return a1 | a2;
        case 8:
            return a2 >= 32 ? 0u : (a1 << a2);
        case 9:
            return a2 >= 32 ? 0u : (a1 >> a2);
        case 10:
            return a2 ? a1 % a2 : 0u;
        case 11:
            return a1 < a2 ? 1u : 0u;
        case 12:
            return a1 == a2 ? 1u : 0u;
        default:
            return 0;
    }
}

inline constexpr std::array<Op, 13> kAluOps = {
    Op::AluAdd, Op::AluSub, Op::AluMul, Op::AluDiv, Op::AluCdiv, Op::AluXor, Op::AluAnd,
    Op::AluOr,  Op::AluShl, Op::AluShr, Op::AluMod, Op::AluLt,   Op::AluEq,
};

inline constexpr std::array<Op, 13> kValuAluOps = {
    Op::ValuAdd, Op::ValuSub, Op::ValuMul, Op::ValuDiv, Op::ValuCdiv, Op::ValuXor, Op::ValuAnd,
    Op::ValuOr,  Op::ValuShl, Op::ValuShr, Op::ValuMod, Op::ValuLt,   Op::ValuEq,
};

inline constexpr std::array<Op, 4> kLoadOps = {Op::Load, Op::LoadOffset, Op::VLoad, Op::Const};
inline constexpr std::array<Op, 2> kStoreOps = {Op::Store, Op::VStore};
inline constexpr std::array<Op, 11> kFlowOps = {
    Op::Select, Op::AddImm, Op::VSelect,      Op::Halt,         Op::Pause, Op::TraceWrite,
    Op::CondJump, Op::CondJumpRel, Op::Jump, Op::JumpIndirect, Op::CoreId,
};

int engine_index(Engine engine) { return static_cast<int>(engine); }

// Direct 1-slot issue: reads complete before the (at most VLEN) writes land.
// Matches ISA deferred-write semantics for a single slot without a write buffer.
VLIW_INLINE void exec_direct(std::uint32_t* scratch, std::uint32_t* mem, std::size_t mem_n, int& pc,
                             State& state, int core_id, bool enable_pause, const Slot& slot,
                             std::vector<std::uint32_t>* trace) {
    (void)mem_n;
    switch (slot.op) {
        case Op::AluAdd:
        case Op::AluSub:
        case Op::AluMul:
        case Op::AluDiv:
        case Op::AluCdiv:
        case Op::AluXor:
        case Op::AluAnd:
        case Op::AluOr:
        case Op::AluShl:
        case Op::AluShr:
        case Op::AluMod:
        case Op::AluLt:
        case Op::AluEq:
            scratch[slot.dest] = eval_alu(static_cast<std::uint8_t>(slot.op), scratch[slot.a],
                                          scratch[slot.b]);
            return;
        case Op::ValuAdd:
        case Op::ValuSub:
        case Op::ValuMul:
        case Op::ValuDiv:
        case Op::ValuCdiv:
        case Op::ValuXor:
        case Op::ValuAnd:
        case Op::ValuOr:
        case Op::ValuShl:
        case Op::ValuShr:
        case Op::ValuMod:
        case Op::ValuLt:
        case Op::ValuEq: {
            const auto kind = static_cast<std::uint8_t>(static_cast<int>(slot.op) -
                                                        static_cast<int>(Op::ValuAdd));
            std::uint32_t tmp[kVlen];
            for (int i = 0; i < kVlen; ++i)
                tmp[i] = eval_alu(kind, scratch[slot.a + static_cast<std::uint32_t>(i)],
                                  scratch[slot.b + static_cast<std::uint32_t>(i)]);
            for (int i = 0; i < kVlen; ++i) scratch[slot.dest + static_cast<std::uint32_t>(i)] = tmp[i];
            return;
        }
        case Op::ValuBroadcast: {
            const std::uint32_t v = scratch[slot.a];
            for (int i = 0; i < kVlen; ++i) scratch[slot.dest + static_cast<std::uint32_t>(i)] = v;
            return;
        }
        case Op::ValuMadd: {
            std::uint32_t tmp[kVlen];
            for (int i = 0; i < kVlen; ++i) {
                const std::uint32_t av = scratch[slot.a + static_cast<std::uint32_t>(i)];
                const std::uint32_t bv = scratch[slot.b + static_cast<std::uint32_t>(i)];
                const std::uint32_t cv = scratch[slot.c + static_cast<std::uint32_t>(i)];
                tmp[i] = av * bv + cv;
            }
            for (int i = 0; i < kVlen; ++i) scratch[slot.dest + static_cast<std::uint32_t>(i)] = tmp[i];
            return;
        }
        case Op::Load:
            scratch[slot.dest] = mem[scratch[slot.a]];
            return;
        case Op::LoadOffset:
            scratch[slot.dest + slot.b] = mem[scratch[slot.a + slot.b]];
            return;
        case Op::VLoad: {
            const std::uint32_t addr = scratch[slot.a];
            std::uint32_t tmp[kVlen];
            for (int i = 0; i < kVlen; ++i) tmp[i] = mem[addr + static_cast<std::uint32_t>(i)];
            for (int i = 0; i < kVlen; ++i) scratch[slot.dest + static_cast<std::uint32_t>(i)] = tmp[i];
            return;
        }
        case Op::Const:
            scratch[slot.dest] = slot.a;
            return;
        case Op::Store:
            mem[scratch[slot.dest]] = scratch[slot.a];
            return;
        case Op::VStore: {
            const std::uint32_t addr = scratch[slot.dest];
            std::uint32_t tmp[kVlen];
            for (int i = 0; i < kVlen; ++i) tmp[i] = scratch[slot.a + static_cast<std::uint32_t>(i)];
            for (int i = 0; i < kVlen; ++i) mem[addr + static_cast<std::uint32_t>(i)] = tmp[i];
            return;
        }
        case Op::Select:
            scratch[slot.dest] = scratch[slot.a] != 0 ? scratch[slot.b] : scratch[slot.c];
            return;
        case Op::AddImm:
            scratch[slot.dest] = scratch[slot.a] + slot.b;
            return;
        case Op::VSelect: {
            std::uint32_t tmp[kVlen];
            for (int i = 0; i < kVlen; ++i) {
                const std::uint32_t cond = scratch[slot.a + static_cast<std::uint32_t>(i)];
                tmp[i] = cond != 0 ? scratch[slot.b + static_cast<std::uint32_t>(i)]
                                   : scratch[slot.c + static_cast<std::uint32_t>(i)];
            }
            for (int i = 0; i < kVlen; ++i) scratch[slot.dest + static_cast<std::uint32_t>(i)] = tmp[i];
            return;
        }
        case Op::Halt:
            state = State::Stopped;
            return;
        case Op::Pause:
            if (enable_pause) state = State::Paused;
            return;
        case Op::TraceWrite:
            if (trace != nullptr) trace->push_back(scratch[slot.a]);
            return;
        case Op::CondJump:
            if (scratch[slot.a] != 0) pc = static_cast<int>(slot.b);
            return;
        case Op::CondJumpRel:
            if (scratch[slot.a] != 0) pc += static_cast<int>(static_cast<std::int32_t>(slot.b));
            return;
        case Op::Jump:
            pc = static_cast<int>(slot.a);
            return;
        case Op::JumpIndirect:
            pc = static_cast<int>(scratch[slot.a]);
            return;
        case Op::CoreId:
            scratch[slot.dest] = static_cast<std::uint32_t>(core_id);
            return;
        case Op::DebugCompare:
        case Op::DebugVCompare:
        case Op::Nop:
            return;
        default:
            return;
    }
}

#if defined(_MSC_VER)
#define VLIW_RESTRICT __restrict
#else
#define VLIW_RESTRICT __restrict__
#endif

// Linear stream: no PC, no jumps, pause is a counted nop. Returns false on Halt.
VLIW_INLINE bool exec_linear(std::uint32_t* VLIW_RESTRICT scratch,
                             std::uint32_t* VLIW_RESTRICT mem, const Slot& slot,
                             std::vector<std::uint32_t>* trace) {
    switch (slot.op) {
        case Op::AluAdd:
            scratch[slot.dest] = scratch[slot.a] + scratch[slot.b];
            return true;
        case Op::AluSub:
            scratch[slot.dest] = scratch[slot.a] - scratch[slot.b];
            return true;
        case Op::AluMul:
            scratch[slot.dest] = scratch[slot.a] * scratch[slot.b];
            return true;
        case Op::AluDiv:
            scratch[slot.dest] = scratch[slot.b] ? scratch[slot.a] / scratch[slot.b] : 0u;
            return true;
        case Op::AluCdiv: {
            const std::uint32_t b = scratch[slot.b];
            if (b == 0) {
                scratch[slot.dest] = 0;
                return true;
            }
            const std::uint64_t num =
                static_cast<std::uint64_t>(scratch[slot.a]) + static_cast<std::uint64_t>(b) - 1;
            scratch[slot.dest] = static_cast<std::uint32_t>(num / b);
            return true;
        }
        case Op::AluXor:
            scratch[slot.dest] = scratch[slot.a] ^ scratch[slot.b];
            return true;
        case Op::AluAnd:
            scratch[slot.dest] = scratch[slot.a] & scratch[slot.b];
            return true;
        case Op::AluOr:
            scratch[slot.dest] = scratch[slot.a] | scratch[slot.b];
            return true;
        case Op::AluShl: {
            const std::uint32_t sh = scratch[slot.b];
            scratch[slot.dest] = sh >= 32 ? 0u : (scratch[slot.a] << sh);
            return true;
        }
        case Op::AluShr: {
            const std::uint32_t sh = scratch[slot.b];
            scratch[slot.dest] = sh >= 32 ? 0u : (scratch[slot.a] >> sh);
            return true;
        }
        case Op::AluMod:
            scratch[slot.dest] = scratch[slot.b] ? scratch[slot.a] % scratch[slot.b] : 0u;
            return true;
        case Op::AluLt:
            scratch[slot.dest] = scratch[slot.a] < scratch[slot.b] ? 1u : 0u;
            return true;
        case Op::AluEq:
            scratch[slot.dest] = scratch[slot.a] == scratch[slot.b] ? 1u : 0u;
            return true;
        case Op::ValuAdd:
        case Op::ValuSub:
        case Op::ValuMul:
        case Op::ValuDiv:
        case Op::ValuCdiv:
        case Op::ValuXor:
        case Op::ValuAnd:
        case Op::ValuOr:
        case Op::ValuShl:
        case Op::ValuShr:
        case Op::ValuMod:
        case Op::ValuLt:
        case Op::ValuEq: {
            const auto kind = static_cast<std::uint8_t>(static_cast<int>(slot.op) -
                                                        static_cast<int>(Op::ValuAdd));
            std::uint32_t tmp[kVlen];
            for (int i = 0; i < kVlen; ++i)
                tmp[i] = eval_alu(kind, scratch[slot.a + static_cast<std::uint32_t>(i)],
                                  scratch[slot.b + static_cast<std::uint32_t>(i)]);
            for (int i = 0; i < kVlen; ++i) scratch[slot.dest + static_cast<std::uint32_t>(i)] = tmp[i];
            return true;
        }
        case Op::ValuBroadcast: {
            const std::uint32_t v = scratch[slot.a];
            for (int i = 0; i < kVlen; ++i) scratch[slot.dest + static_cast<std::uint32_t>(i)] = v;
            return true;
        }
        case Op::ValuMadd: {
            std::uint32_t tmp[kVlen];
            for (int i = 0; i < kVlen; ++i) {
                const std::uint32_t av = scratch[slot.a + static_cast<std::uint32_t>(i)];
                const std::uint32_t bv = scratch[slot.b + static_cast<std::uint32_t>(i)];
                const std::uint32_t cv = scratch[slot.c + static_cast<std::uint32_t>(i)];
                tmp[i] = av * bv + cv;
            }
            for (int i = 0; i < kVlen; ++i) scratch[slot.dest + static_cast<std::uint32_t>(i)] = tmp[i];
            return true;
        }
        case Op::Load:
            scratch[slot.dest] = mem[scratch[slot.a]];
            return true;
        case Op::LoadOffset:
            scratch[slot.dest + slot.b] = mem[scratch[slot.a + slot.b]];
            return true;
        case Op::VLoad: {
            const std::uint32_t addr = scratch[slot.a];
            std::uint32_t tmp[kVlen];
            for (int i = 0; i < kVlen; ++i) tmp[i] = mem[addr + static_cast<std::uint32_t>(i)];
            for (int i = 0; i < kVlen; ++i) scratch[slot.dest + static_cast<std::uint32_t>(i)] = tmp[i];
            return true;
        }
        case Op::Const:
            scratch[slot.dest] = slot.a;
            return true;
        case Op::Store:
            mem[scratch[slot.dest]] = scratch[slot.a];
            return true;
        case Op::VStore: {
            const std::uint32_t addr = scratch[slot.dest];
            std::uint32_t tmp[kVlen];
            for (int i = 0; i < kVlen; ++i) tmp[i] = scratch[slot.a + static_cast<std::uint32_t>(i)];
            for (int i = 0; i < kVlen; ++i) mem[addr + static_cast<std::uint32_t>(i)] = tmp[i];
            return true;
        }
        case Op::Select:
            scratch[slot.dest] = scratch[slot.a] != 0 ? scratch[slot.b] : scratch[slot.c];
            return true;
        case Op::AddImm:
            scratch[slot.dest] = scratch[slot.a] + slot.b;
            return true;
        case Op::VSelect: {
            std::uint32_t tmp[kVlen];
            for (int i = 0; i < kVlen; ++i) {
                const std::uint32_t cond = scratch[slot.a + static_cast<std::uint32_t>(i)];
                tmp[i] = cond != 0 ? scratch[slot.b + static_cast<std::uint32_t>(i)]
                                   : scratch[slot.c + static_cast<std::uint32_t>(i)];
            }
            for (int i = 0; i < kVlen; ++i) scratch[slot.dest + static_cast<std::uint32_t>(i)] = tmp[i];
            return true;
        }
        case Op::Halt:
            return false;
        case Op::CoreId:
            scratch[slot.dest] = 0;
            return true;
        case Op::TraceWrite:
            if (trace != nullptr) trace->push_back(scratch[slot.a]);
            return true;
        case Op::Pause:
        case Op::DebugCompare:
        case Op::DebugVCompare:
        case Op::Nop:
            return true;
        default:
            return true;
    }
}

}  // namespace

Op decode_op(Engine engine, std::uint8_t raw_op) {
    switch (engine) {
        case Engine::Alu:
            if (raw_op > 12) fail("unknown alu op");
            return kAluOps[raw_op];
        case Engine::Valu:
            if (raw_op <= 12) return kValuAluOps[raw_op];
            if (raw_op == 13) return Op::ValuBroadcast;
            if (raw_op == 14) return Op::ValuMadd;
            fail("unknown valu op");
        case Engine::Load:
            if (raw_op > 3) fail("unknown load op");
            return kLoadOps[raw_op];
        case Engine::Store:
            if (raw_op > 1) fail("unknown store op");
            return kStoreOps[raw_op];
        case Engine::Flow:
            if (raw_op > 10) fail("unknown flow op");
            return kFlowOps[raw_op];
        case Engine::Debug:
            if (raw_op == 0) return Op::DebugCompare;
            if (raw_op == 1) return Op::DebugVCompare;
            return Op::Nop;
        default:
            fail("unknown engine");
    }
}

void Program::reserve(std::size_t n_bundles, std::size_t n_slots) {
    bundles.reserve(n_bundles);
    slots.reserve(n_slots);
    if (linear_ok) linear.reserve(n_bundles);
}

void Program::note_linear(const Bundle& b) {
    if (!linear_ok) return;
    if (!(b.flags & kFlagNonDebug)) return;
    if (!(b.flags & kFlagSingle) || b.count != 1) {
        linear_ok = false;
        linear.clear();
        return;
    }
    switch (b.one.op) {
        case Op::CondJump:
        case Op::CondJumpRel:
        case Op::Jump:
        case Op::JumpIndirect:
            linear_ok = false;
            linear.clear();
            return;
        default:
            linear.push_back(b.one);
    }
}

void Program::begin_bundle() {
    if (open_) end_bundle();
    open_ = true;
    pending_n_ = 0;
    for (int& c : cur_counts_) c = 0;
    cur_non_debug_ = false;
}

void Program::end_bundle() {
    if (!open_) return;
    Bundle b;
    b.count = static_cast<std::uint16_t>(pending_n_);
    b.flags = 0;
    if (cur_non_debug_) b.flags |= kFlagNonDebug;
    if (b.count == 1) b.flags |= kFlagSingle;
    if (pending_n_ > 0) b.one = pending_[0];
    if (pending_n_ > 1) {
        b.begin = static_cast<std::uint32_t>(slots.size());
        slots.insert(slots.end(), pending_, pending_ + pending_n_);
    }
    note_linear(b);
    bundles.push_back(b);
    open_ = false;
    pending_n_ = 0;
}

void Program::load_oneslot(const void* data, int n) {
    struct Desc {
        std::uint8_t engine;
        std::uint8_t op;
        std::uint8_t pad[2];
        std::uint32_t dest;
        std::uint32_t a;
        std::uint32_t b;
        std::uint32_t c;
    };
    if (n < 0) fail("negative oneslot count");
    if (n > 0 && data == nullptr) fail("null oneslot data");
    if (open_) end_bundle();
    const auto* src = static_cast<const Desc*>(data);
    reserve(static_cast<std::size_t>(n), 0);
    for (int i = 0; i < n; ++i) {
        const Desc& s = src[i];
        const auto engine = static_cast<Engine>(s.engine);
        Slot slot;
        slot.op = decode_op(engine, s.op);
        slot.dest = static_cast<std::uint16_t>(s.dest);
        slot.a = s.a;
        slot.b = s.b;
        slot.c = s.c;
        if (slot.op == Op::DebugCompare) {
            slot.a = static_cast<std::uint32_t>(debug_key_count);
            debug_key_count += 1;
        } else if (slot.op == Op::DebugVCompare) {
            slot.a = static_cast<std::uint32_t>(debug_key_count);
            debug_key_count += kVlen;
        }
        Bundle b;
        b.count = 1;
        b.flags = kFlagSingle;
        if (engine != Engine::Debug) b.flags |= kFlagNonDebug;
        b.one = slot;
        note_linear(b);
        bundles.push_back(b);
    }
}

void Program::add(Engine engine, std::uint8_t raw_op, std::uint32_t dest, std::uint32_t a,
                  std::uint32_t b, std::uint32_t c) {
    if (!open_) begin_bundle();
    const int ei = engine_index(engine);
    if (ei < 0 || ei >= kNEngines) fail("unknown engine");
    cur_counts_[ei] += 1;
    if (cur_counts_[ei] > kSlotLimit[ei]) fail("slot limit exceeded");
    if (engine != Engine::Debug) cur_non_debug_ = true;
    if (pending_n_ >= kMaxSlotsPerBundle) fail("too many slots in one bundle");

    Slot slot;
    slot.op = decode_op(engine, raw_op);
    slot.dest = static_cast<std::uint16_t>(dest);
    slot.a = a;
    slot.b = b;
    slot.c = c;
    if (slot.op == Op::DebugCompare) {
        slot.a = static_cast<std::uint32_t>(debug_key_count);
        debug_key_count += 1;
    } else if (slot.op == Op::DebugVCompare) {
        slot.a = static_cast<std::uint32_t>(debug_key_count);
        debug_key_count += kVlen;
    }
    pending_[pending_n_++] = slot;
}

void Program::finalize() {
    if (open_) end_bundle();
}

Machine::Machine(std::span<const std::uint32_t> mem, Program program, int n_cores, int scratch_size)
    : program_(std::move(program)), scratch_size_(scratch_size) {
    if (n_cores < 1) fail("n_cores must be >= 1");
    if (scratch_size_ < 1 || scratch_size_ > kDefaultScratch) fail("scratch_size out of range");
    program_.finalize();
    mem_.assign(mem.begin(), mem.end());
    if (mem_.size() < 8) mem_.resize(8, 0);
    mem_.reserve(mem_.size() + 256);
    cores_.resize(static_cast<std::size_t>(n_cores));
    for (int i = 0; i < n_cores; ++i) cores_[static_cast<std::size_t>(i)].id = i;
    debug_expected_.assign(static_cast<std::size_t>(program_.debug_key_count), 0);
    debug_present_.assign(static_cast<std::size_t>(program_.debug_key_count), 0);
    prepare_linear();
}

void Machine::set_debug_expected(std::span<const std::uint32_t> vals,
                                 std::span<const std::uint8_t> present) {
    if (vals.size() != present.size()) fail("debug expected/present size mismatch");
    const std::size_t n = vals.size();
    if (n > debug_expected_.size()) {
        debug_expected_.resize(n, 0);
        debug_present_.resize(n, 0);
    }
    for (std::size_t i = 0; i < n; ++i) {
        debug_expected_[i] = vals[i];
        debug_present_[i] = present[i];
    }
}

void Machine::run() {
    for (Core& core : cores_) {
        if (core.state == State::Paused) core.state = State::Running;
    }
    if (cores_.size() == 1 && !enable_debug_) {
        run_fast();
        return;
    }
    run_checked();
}

bool Machine::prepare_linear() {
    if (linear_ready_) return linear_ok_;
    linear_ready_ = true;
    if (program_.linear_ok) {
        linear_ = std::move(program_.linear);
        linear_ok_ = true;
        return true;
    }
    linear_ok_ = false;
    return false;
}

void Machine::run_linear() {
    Core& core = cores_[0];
    std::uint32_t* const scratch = core.scratch;
    std::uint32_t* const mem = mem_.data();
    const Slot* const begin = linear_.data();
    const Slot* const end = begin + linear_.size();
    const Slot* slot = begin;
    for (; slot != end; ++slot) {
        if (!exec_linear(scratch, mem, *slot, &core.trace_buf)) {
            ++slot;
            core.state = State::Stopped;
            cycle_ += static_cast<std::uint64_t>(slot - begin);
            core.pc = static_cast<int>(program_.bundles.size());
            return;
        }
    }
    cycle_ += static_cast<std::uint64_t>(end - begin);
    core.pc = static_cast<int>(program_.bundles.size());
    core.state = State::Stopped;
}

void Machine::run_fast() {
    if (!enable_pause_ && cores_[0].pc == 0 && cores_[0].state == State::Running &&
        prepare_linear()) {
        run_linear();
        return;
    }
    Core& core = cores_[0];
    const Bundle* const bundles = program_.bundles.data();
    const std::size_t n_bundles = program_.bundles.size();
    std::uint32_t* const scratch = core.scratch;
    int pc = core.pc;
    State state = core.state;

    while (state == State::Running) {
        if (pc < 0 || static_cast<std::size_t>(pc) >= n_bundles) {
            state = State::Stopped;
            break;
        }
        const Bundle& bundle = bundles[pc];
        pc += 1;
        if (!(bundle.flags & kFlagNonDebug)) continue;
        if (bundle.flags & kFlagSingle) {
            exec_direct(scratch, mem_.data(), mem_.size(), pc, state, core.id, enable_pause_,
                        bundle.one, &core.trace_buf);
        } else {
            core.pc = pc;
            core.state = state;
            step_multi(bundle, core, false);
            pc = core.pc;
            state = core.state;
        }
        cycle_ += 1;
    }
    core.pc = pc;
    core.state = state;
}

void Machine::run_checked() {
    const std::size_t n_bundles = program_.bundles.size();
    bool running = true;
    while (running) {
        running = false;
        bool has_non_debug = false;
        for (Core& core : cores_) {
            if (core.state != State::Running) continue;
            if (core.pc < 0 || static_cast<std::size_t>(core.pc) >= n_bundles) {
                core.state = State::Stopped;
                continue;
            }
            const Bundle& bundle = program_.bundles[static_cast<std::size_t>(core.pc)];
            core.pc += 1;
            if (bundle.flags & kFlagNonDebug) {
                has_non_debug = true;
                if (bundle.flags & kFlagSingle || bundle.count <= 1) {
                    n_sw_ = 0;
                    n_mw_ = 0;
                    exec(bundle.one, core, true);
                    apply_writes(core, true);
                } else {
                    step_multi(bundle, core, true);
                }
            } else if (enable_debug_) {
                if (bundle.flags & kFlagSingle || bundle.count <= 1) {
                    n_sw_ = 0;
                    n_mw_ = 0;
                    exec(bundle.one, core, true);
                    apply_writes(core, true);
                } else {
                    step_multi(bundle, core, true);
                }
            }
            if (core.state == State::Running) running = true;
        }
        if (has_non_debug) cycle_ += 1;
    }
}

void Machine::apply_writes(Core& core, bool checked) {
    for (int i = 0; i < n_sw_; ++i) core.scratch[scratch_wb_[i].addr] = scratch_wb_[i].val;
    for (int i = 0; i < n_mw_; ++i) {
        const Write& w = mem_wb_[i];
        if (w.addr >= mem_.size()) {
            if (checked || w.addr > (1u << 24)) fail("mem write oob");
            mem_.resize(static_cast<std::size_t>(w.addr) + 1, 0);
        }
        mem_[w.addr] = w.val;
    }
    n_sw_ = 0;
    n_mw_ = 0;
}

void Machine::step_multi(const Bundle& bundle, Core& core, bool checked) {
    n_sw_ = 0;
    n_mw_ = 0;
    const Slot* const base = program_.slots.data() + bundle.begin;
    for (std::uint16_t i = 0; i < bundle.count; ++i) exec(base[i], core, checked);
    apply_writes(core, checked);
}

void Machine::write_scratch(std::uint32_t addr, std::uint32_t val, bool checked) {
    if (n_sw_ >= kMaxScratchWrites) fail("scratch write buffer full");
    if (addr >= static_cast<std::uint32_t>(scratch_size_)) fail("scratch write oob");
    (void)checked;
    scratch_wb_[n_sw_].addr = addr;
    scratch_wb_[n_sw_].val = val;
    ++n_sw_;
}

void Machine::write_mem(std::uint32_t addr, std::uint32_t val, bool checked) {
    if (n_mw_ >= kMaxMemWrites) fail("mem write buffer full");
    if (checked && addr >= mem_.size()) fail("mem write oob");
    mem_wb_[n_mw_].addr = addr;
    mem_wb_[n_mw_].val = val;
    ++n_mw_;
}

std::uint32_t Machine::read_mem(std::uint32_t addr, bool checked) const {
    if (checked && addr >= mem_.size()) fail("mem read oob");
    return mem_[addr];
}

std::uint32_t Machine::scratch_at(const Core& core, std::uint32_t addr, bool checked) const {
    if (checked && addr >= static_cast<std::uint32_t>(scratch_size_)) fail("scratch read oob");
    return core.scratch[addr];
}

void Machine::exec(const Slot& slot, Core& core, bool checked) {
    switch (slot.op) {
        case Op::AluAdd:
        case Op::AluSub:
        case Op::AluMul:
        case Op::AluDiv:
        case Op::AluCdiv:
        case Op::AluXor:
        case Op::AluAnd:
        case Op::AluOr:
        case Op::AluShl:
        case Op::AluShr:
        case Op::AluMod:
        case Op::AluLt:
        case Op::AluEq: {
            const std::uint32_t a1 = scratch_at(core, slot.a, checked);
            const std::uint32_t a2 = scratch_at(core, slot.b, checked);
            write_scratch(slot.dest, eval_alu(static_cast<std::uint8_t>(slot.op), a1, a2, checked),
                          checked);
            return;
        }
        case Op::ValuAdd:
        case Op::ValuSub:
        case Op::ValuMul:
        case Op::ValuDiv:
        case Op::ValuCdiv:
        case Op::ValuXor:
        case Op::ValuAnd:
        case Op::ValuOr:
        case Op::ValuShl:
        case Op::ValuShr:
        case Op::ValuMod:
        case Op::ValuLt:
        case Op::ValuEq: {
            const auto kind = static_cast<std::uint8_t>(static_cast<int>(slot.op) -
                                                        static_cast<int>(Op::ValuAdd));
            for (int i = 0; i < kVlen; ++i) {
                const std::uint32_t a1 = scratch_at(core, slot.a + static_cast<std::uint32_t>(i), checked);
                const std::uint32_t a2 = scratch_at(core, slot.b + static_cast<std::uint32_t>(i), checked);
                write_scratch(slot.dest + static_cast<std::uint32_t>(i),
                              eval_alu(kind, a1, a2, checked), checked);
            }
            return;
        }
        case Op::ValuBroadcast: {
            const std::uint32_t v = scratch_at(core, slot.a, checked);
            for (int i = 0; i < kVlen; ++i)
                write_scratch(slot.dest + static_cast<std::uint32_t>(i), v, checked);
            return;
        }
        case Op::ValuMadd: {
            for (int i = 0; i < kVlen; ++i) {
                const std::uint32_t av = scratch_at(core, slot.a + static_cast<std::uint32_t>(i), checked);
                const std::uint32_t bv = scratch_at(core, slot.b + static_cast<std::uint32_t>(i), checked);
                const std::uint32_t cv = scratch_at(core, slot.c + static_cast<std::uint32_t>(i), checked);
                write_scratch(slot.dest + static_cast<std::uint32_t>(i), av * bv + cv, checked);
            }
            return;
        }
        case Op::Load:
            write_scratch(slot.dest, read_mem(scratch_at(core, slot.a, checked), checked), checked);
            return;
        case Op::LoadOffset:
            write_scratch(slot.dest + slot.b,
                          read_mem(scratch_at(core, slot.a + slot.b, checked), checked), checked);
            return;
        case Op::VLoad: {
            const std::uint32_t addr = scratch_at(core, slot.a, checked);
            for (int i = 0; i < kVlen; ++i)
                write_scratch(slot.dest + static_cast<std::uint32_t>(i),
                              read_mem(addr + static_cast<std::uint32_t>(i), checked), checked);
            return;
        }
        case Op::Const:
            write_scratch(slot.dest, slot.a, checked);
            return;
        case Op::Store:
            write_mem(scratch_at(core, slot.dest, checked), scratch_at(core, slot.a, checked),
                      checked);
            return;
        case Op::VStore: {
            const std::uint32_t addr = scratch_at(core, slot.dest, checked);
            for (int i = 0; i < kVlen; ++i)
                write_mem(addr + static_cast<std::uint32_t>(i),
                          scratch_at(core, slot.a + static_cast<std::uint32_t>(i), checked), checked);
            return;
        }
        case Op::Select:
            write_scratch(slot.dest,
                          scratch_at(core, slot.a, checked) != 0 ? scratch_at(core, slot.b, checked)
                                                                : scratch_at(core, slot.c, checked),
                          checked);
            return;
        case Op::AddImm:
            write_scratch(slot.dest, scratch_at(core, slot.a, checked) + slot.b, checked);
            return;
        case Op::VSelect:
            for (int i = 0; i < kVlen; ++i) {
                const std::uint32_t cond = scratch_at(core, slot.a + static_cast<std::uint32_t>(i), checked);
                const std::uint32_t t = scratch_at(core, slot.b + static_cast<std::uint32_t>(i), checked);
                const std::uint32_t f = scratch_at(core, slot.c + static_cast<std::uint32_t>(i), checked);
                write_scratch(slot.dest + static_cast<std::uint32_t>(i), cond != 0 ? t : f, checked);
            }
            return;
        case Op::Halt:
            core.state = State::Stopped;
            return;
        case Op::Pause:
            if (enable_pause_) core.state = State::Paused;
            return;
        case Op::TraceWrite:
            core.trace_buf.push_back(scratch_at(core, slot.a, checked));
            return;
        case Op::CondJump:
            if (scratch_at(core, slot.a, checked) != 0) core.pc = static_cast<int>(slot.b);
            return;
        case Op::CondJumpRel:
            if (scratch_at(core, slot.a, checked) != 0)
                core.pc += static_cast<int>(static_cast<std::int32_t>(slot.b));
            return;
        case Op::Jump:
            core.pc = static_cast<int>(slot.a);
            return;
        case Op::JumpIndirect:
            core.pc = static_cast<int>(scratch_at(core, slot.a, checked));
            return;
        case Op::CoreId:
            write_scratch(slot.dest, static_cast<std::uint32_t>(core.id), checked);
            return;
        case Op::DebugCompare: {
            if (!enable_debug_) return;
            const std::uint32_t key = slot.a;
            if (key >= debug_present_.size() || !debug_present_[key]) fail("debug compare missing key");
            if (scratch_at(core, slot.dest, checked) != debug_expected_[key]) fail("debug compare mismatch");
            return;
        }
        case Op::DebugVCompare: {
            if (!enable_debug_) return;
            for (int i = 0; i < kVlen; ++i) {
                const std::uint32_t key = slot.a + static_cast<std::uint32_t>(i);
                if (key >= debug_present_.size() || !debug_present_[key])
                    fail("debug vcompare missing key");
                if (scratch_at(core, slot.dest + static_cast<std::uint32_t>(i), checked) !=
                    debug_expected_[key])
                    fail("debug vcompare mismatch");
            }
            return;
        }
        case Op::Nop:
            return;
        default:
            fail("unknown decoded op");
    }
}

}  // namespace vliw
