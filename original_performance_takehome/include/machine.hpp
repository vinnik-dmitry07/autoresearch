#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <stdexcept>
#include <vector>

namespace vliw {

inline constexpr int kVlen = 8;
inline constexpr int kDefaultScratch = 1536;
inline constexpr int kNEngines = 6;

enum class Engine : std::uint8_t { Alu = 0, Valu = 1, Load = 2, Store = 3, Flow = 4, Debug = 5 };

enum class State : std::uint8_t { Running = 1, Paused = 2, Stopped = 3 };

enum class Op : std::uint8_t {
    AluAdd = 0,
    AluSub,
    AluMul,
    AluDiv,
    AluCdiv,
    AluXor,
    AluAnd,
    AluOr,
    AluShl,
    AluShr,
    AluMod,
    AluLt,
    AluEq,
    ValuAdd,
    ValuSub,
    ValuMul,
    ValuDiv,
    ValuCdiv,
    ValuXor,
    ValuAnd,
    ValuOr,
    ValuShl,
    ValuShr,
    ValuMod,
    ValuLt,
    ValuEq,
    ValuBroadcast,
    ValuMadd,
    Load,
    LoadOffset,
    VLoad,
    Const,
    Store,
    VStore,
    Select,
    AddImm,
    VSelect,
    Halt,
    Pause,
    TraceWrite,
    CondJump,
    CondJumpRel,
    Jump,
    JumpIndirect,
    CoreId,
    DebugCompare,
    DebugVCompare,
    Nop,
};

inline constexpr int kSlotLimit[kNEngines] = {12, 6, 2, 2, 1, 64};
inline constexpr int kMaxSlotsPerBundle =
    kSlotLimit[0] + kSlotLimit[1] + kSlotLimit[2] + kSlotLimit[3] + kSlotLimit[4] + kSlotLimit[5];
inline constexpr int kMaxScratchWrites =
    kSlotLimit[0] + kVlen * (kSlotLimit[1] + kSlotLimit[2] + kSlotLimit[4]);
inline constexpr int kMaxMemWrites = kVlen * kSlotLimit[3];

// Packed like durak::Move: trivial aggregate, no heap.
struct Slot {
    Op op = Op::Nop;
    std::uint16_t dest = 0;
    std::uint32_t a = 0;
    std::uint32_t b = 0;
    std::uint32_t c = 0;
};

inline constexpr std::uint16_t kFlagNonDebug = 1;
inline constexpr std::uint16_t kFlagSingle = 2;

struct Bundle {
    std::uint16_t count = 0;
    std::uint16_t flags = 0;
    Slot one{};  // first/only slot; avoids a second chase on the 1-slot path
    std::uint32_t begin = 0;
};

Op decode_op(Engine engine, std::uint8_t raw_op);

class Program {
public:
    void begin_bundle();
    void end_bundle();
    void add(Engine engine, std::uint8_t raw_op, std::uint32_t dest = 0, std::uint32_t a = 0,
             std::uint32_t b = 0, std::uint32_t c = 0);
    void finalize();
    // Packed records: engine, op, pad[2], dest, a, b, c (same as VliwSlotDesc).
    void load_oneslot(const void* slots, int n);

    std::vector<Bundle> bundles;
    std::vector<Slot> slots;
    std::vector<Slot> linear;
    int debug_key_count = 0;
    bool linear_ok = true;

    void reserve(std::size_t n_bundles, std::size_t n_slots);

private:
    void note_linear(const Bundle& b);

    bool open_ = false;
    int cur_counts_[kNEngines] = {};
    bool cur_non_debug_ = false;
    Slot pending_[kMaxSlotsPerBundle]{};
    int pending_n_ = 0;
};

// POD core: scratch lives inline, same idea as GameState::hands / deck.
struct Core {
    std::uint32_t scratch[kDefaultScratch]{};
    int id = 0;
    int pc = 0;
    State state = State::Running;
    std::vector<std::uint32_t> trace_buf;
};

class Machine {
public:
    Machine(std::span<const std::uint32_t> mem, Program program, int n_cores = 1,
            int scratch_size = kDefaultScratch);
    Machine(Machine&&) noexcept = default;
    Machine& operator=(Machine&&) noexcept = default;
    Machine(const Machine&) = default;
    Machine& operator=(const Machine&) = default;

    void run();
    void set_enable_pause(bool v) { enable_pause_ = v; }
    void set_enable_debug(bool v) { enable_debug_ = v; }
    void set_debug_expected(std::span<const std::uint32_t> vals, std::span<const std::uint8_t> present);

    std::uint64_t cycle() const { return cycle_; }
    std::span<const std::uint32_t> mem() const { return mem_; }
    std::span<std::uint32_t> mem_mut() { return mem_; }
    const std::vector<Core>& cores() const { return cores_; }
    std::vector<Core>& cores() { return cores_; }
    int scratch_size() const { return scratch_size_; }

private:
    void run_fast();
    void run_linear();
    void run_checked();
    bool prepare_linear();
    void step_multi(const Bundle& bundle, Core& core, bool checked);
    void exec(const Slot& slot, Core& core, bool checked);
    void apply_writes(Core& core, bool checked);
    void write_scratch(std::uint32_t addr, std::uint32_t val, bool checked);
    void write_mem(std::uint32_t addr, std::uint32_t val, bool checked);
    std::uint32_t read_mem(std::uint32_t addr, bool checked) const;
    std::uint32_t scratch_at(const Core& core, std::uint32_t addr, bool checked) const;

    Program program_;
    std::vector<Core> cores_;
    std::vector<std::uint32_t> mem_;
    std::vector<std::uint32_t> debug_expected_;
    std::vector<std::uint8_t> debug_present_;
    std::vector<Slot> linear_;
    int scratch_size_ = kDefaultScratch;
    std::uint64_t cycle_ = 0;
    bool enable_pause_ = true;
    bool enable_debug_ = true;
    bool linear_ready_ = false;
    bool linear_ok_ = false;

    struct Write {
        std::uint32_t addr;
        std::uint32_t val;
    };
    Write scratch_wb_[kMaxScratchWrites];
    Write mem_wb_[kMaxMemWrites];
    int n_sw_ = 0;
    int n_mw_ = 0;
};

}  // namespace vliw
