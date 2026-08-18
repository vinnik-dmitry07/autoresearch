#include "profiler.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace vliw {
namespace {

constexpr int kNEng = 6;
constexpr const char* kEngName[] = {"alu", "valu", "load", "store", "flow", "debug"};

Engine engine_of(Op op) {
    static constexpr Engine kMap[] = {
        Engine::Alu,    Engine::Alu,    Engine::Alu,    Engine::Alu,    Engine::Alu,
        Engine::Alu,    Engine::Alu,    Engine::Alu,    Engine::Alu,    Engine::Alu,
        Engine::Alu,    Engine::Alu,    Engine::Alu,  // AluAdd..AluEq
        Engine::Valu,   Engine::Valu,   Engine::Valu,   Engine::Valu,   Engine::Valu,
        Engine::Valu,   Engine::Valu,   Engine::Valu,   Engine::Valu,   Engine::Valu,
        Engine::Valu,   Engine::Valu,   Engine::Valu,   Engine::Valu,   Engine::Valu,  // ValuAdd..ValuMadd
        Engine::Load,   Engine::Load,   Engine::Load,   Engine::Load,                  // Load..Const
        Engine::Store,  Engine::Store,                                                 // Store..VStore
        Engine::Flow,   Engine::Flow,   Engine::Flow,   Engine::Flow,   Engine::Flow,
        Engine::Flow,   Engine::Flow,   Engine::Flow,   Engine::Flow,   Engine::Flow,
        Engine::Flow,  // Select..CoreId
        Engine::Debug,  Engine::Debug,  Engine::Debug,
    };
    const unsigned v = static_cast<unsigned>(op);
    return v < sizeof(kMap) / sizeof(kMap[0]) ? kMap[v] : Engine::Debug;
}

const char* op_name(Op op) {
    switch (op) {
        case Op::AluAdd:
            return "alu.+";
        case Op::AluSub:
            return "alu.-";
        case Op::AluMul:
            return "alu.*";
        case Op::AluDiv:
            return "alu.//";
        case Op::AluCdiv:
            return "alu.cdiv";
        case Op::AluXor:
            return "alu.^";
        case Op::AluAnd:
            return "alu.&";
        case Op::AluOr:
            return "alu.|";
        case Op::AluShl:
            return "alu.<<";
        case Op::AluShr:
            return "alu.>>";
        case Op::AluMod:
            return "alu.%";
        case Op::AluLt:
            return "alu.<";
        case Op::AluEq:
            return "alu.==";
        case Op::ValuAdd:
            return "valu.+";
        case Op::ValuSub:
            return "valu.-";
        case Op::ValuMul:
            return "valu.*";
        case Op::ValuDiv:
            return "valu.//";
        case Op::ValuCdiv:
            return "valu.cdiv";
        case Op::ValuXor:
            return "valu.^";
        case Op::ValuAnd:
            return "valu.&";
        case Op::ValuOr:
            return "valu.|";
        case Op::ValuShl:
            return "valu.<<";
        case Op::ValuShr:
            return "valu.>>";
        case Op::ValuMod:
            return "valu.%";
        case Op::ValuLt:
            return "valu.<";
        case Op::ValuEq:
            return "valu.==";
        case Op::ValuBroadcast:
            return "valu.vbroadcast";
        case Op::ValuMadd:
            return "valu.multiply_add";
        case Op::Load:
            return "load.load";
        case Op::LoadOffset:
            return "load.load_offset";
        case Op::VLoad:
            return "load.vload";
        case Op::Const:
            return "load.const";
        case Op::Store:
            return "store.store";
        case Op::VStore:
            return "store.vstore";
        case Op::Select:
            return "flow.select";
        case Op::AddImm:
            return "flow.add_imm";
        case Op::VSelect:
            return "flow.vselect";
        case Op::Halt:
            return "flow.halt";
        case Op::Pause:
            return "flow.pause";
        case Op::TraceWrite:
            return "flow.trace_write";
        case Op::CondJump:
            return "flow.cond_jump";
        case Op::CondJumpRel:
            return "flow.cond_jump_rel";
        case Op::Jump:
            return "flow.jump";
        case Op::JumpIndirect:
            return "flow.jump_indirect";
        case Op::CoreId:
            return "flow.coreid";
        case Op::DebugCompare:
            return "debug.compare";
        case Op::DebugVCompare:
            return "debug.vcompare";
        default:
            return "nop";
    }
}

bool is_jump(Op op) {
    return op == Op::CondJump || op == Op::CondJumpRel || op == Op::Jump || op == Op::JumpIndirect;
}

bool is_load_mem(Op op) { return op == Op::Load || op == Op::LoadOffset || op == Op::VLoad; }

bool is_store_mem(Op op) { return op == Op::Store || op == Op::VStore; }

struct AddrList {
    std::uint32_t v[24];
    int n = 0;
    void clear() { n = 0; }
    void push(std::uint32_t x) { v[n++] = x; }
    void add_range(std::uint32_t base, int k) {
        for (int i = 0; i < k; ++i) v[n++] = base + static_cast<std::uint32_t>(i);
    }
};

void scratch_reads(const Slot& s, AddrList& out) {
    out.clear();
    switch (s.op) {
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
            out.push(s.a);
            out.push(s.b);
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
        case Op::ValuEq:
            out.add_range(s.a, kVlen);
            out.add_range(s.b, kVlen);
            return;
        case Op::ValuBroadcast:
            out.push(s.a);
            return;
        case Op::ValuMadd:
            out.add_range(s.a, kVlen);
            out.add_range(s.b, kVlen);
            out.add_range(s.c, kVlen);
            return;
        case Op::Load:
        case Op::VLoad:
            out.push(s.a);
            return;
        case Op::LoadOffset:
            out.push(s.a + s.b);
            return;
        case Op::Const:
        case Op::Halt:
        case Op::Pause:
        case Op::Jump:
        case Op::CoreId:
        case Op::DebugCompare:
        case Op::DebugVCompare:
        case Op::Nop:
            return;
        case Op::Store:
            out.push(s.dest);
            out.push(s.a);
            return;
        case Op::VStore:
            out.push(s.dest);
            out.add_range(s.a, kVlen);
            return;
        case Op::Select:
            out.push(s.a);
            out.push(s.b);
            out.push(s.c);
            return;
        case Op::AddImm:
            out.push(s.a);
            return;
        case Op::VSelect:
            out.add_range(s.a, kVlen);
            out.add_range(s.b, kVlen);
            out.add_range(s.c, kVlen);
            return;
        case Op::TraceWrite:
        case Op::CondJump:
        case Op::CondJumpRel:
        case Op::JumpIndirect:
            out.push(s.a);
            return;
        default:
            return;
    }
}

void scratch_writes(const Slot& s, AddrList& out) {
    out.clear();
    switch (s.op) {
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
        case Op::Load:
        case Op::Const:
        case Op::Select:
        case Op::AddImm:
        case Op::CoreId:
            out.push(s.dest);
            return;
        case Op::LoadOffset:
            out.push(s.dest + s.b);
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
        case Op::ValuEq:
        case Op::ValuBroadcast:
        case Op::ValuMadd:
        case Op::VLoad:
        case Op::VSelect:
            out.add_range(s.dest, kVlen);
            return;
        default:
            return;
    }
}

std::uint64_t fnv1a(std::uint64_t h, std::uint64_t v) {
    h ^= v;
    return h * 1099511628211ull;
}

bool json_find(const char* json, const char* key, std::string* out) {
    if (!json || !key) return false;
    std::string pat = std::string("\"") + key + "\":";
    const char* p = std::strstr(json, pat.c_str());
    if (!p) return false;
    p += pat.size();
    while (*p == ' ') ++p;
    if (*p == '"') {
        ++p;
        const char* e = std::strchr(p, '"');
        if (!e) return false;
        *out = std::string(p, e);
        return true;
    }
    const char* e = p;
    while (*e && *e != ',' && *e != '}' && *e != ']' && *e != ' ') ++e;
    *out = std::string(p, e);
    return true;
}

bool json_i64(const char* json, const char* key, std::int64_t* out) {
    std::string s;
    if (!json_find(json, key, &s)) return false;
    *out = std::strtoll(s.c_str(), nullptr, 10);
    return true;
}

bool json_f64(const char* json, const char* key, double* out) {
    std::string s;
    if (!json_find(json, key, &s)) return false;
    *out = std::strtod(s.c_str(), nullptr);
    return true;
}

std::string json_escape(const std::string& s) {
    std::string o;
    o.reserve(s.size() + 8);
    for (char c : s) {
        if (c == '"' || c == '\\') {
            o.push_back('\\');
            o.push_back(c);
        } else {
            o.push_back(c);
        }
    }
    return o;
}

constexpr const char* kPhaseName[] = {"unknown", "init", "ldst", "hash", "walk", "store", "gather"};
constexpr int kNPhase = 7;
constexpr int kMaxDepth = 12;
constexpr int kTopK = 16;
constexpr const char* kRniName[] = {"0", "1", "2_3", "4_7", "8p"};
constexpr const char* kLimitName[] = {"alu", "valu", "load", "store", "flow", "policy", "none"};
constexpr const char* kLoadUseName[] = {"1", "2", "3", "4_7", "8_15", "16_31", "32p"};
constexpr int kSeriesMax = 256;

int load_use_bucket(int d) {
    if (d <= 1) return 0;
    if (d == 2) return 1;
    if (d == 3) return 2;
    if (d <= 7) return 3;
    if (d <= 15) return 4;
    if (d <= 31) return 5;
    return 6;
}

struct Rec {
    int issue = 0;
    int ready = 0;
    int slack = 0;
    int eng = 0;
    Op op = Op::Nop;
    int pred_issue = -1;
    Op pred_op = Op::Nop;
    std::uint8_t phase = 0;
};

struct PendingWrite {
    std::uint32_t addr = 0;
    int cp_raw = 1;
    int cp_waw = 1;
    int cp_mem = 1;
    Op op = Op::Nop;
};

int rni_bucket(int n) {
    if (n <= 0) return 0;
    if (n == 1) return 1;
    if (n <= 3) return 2;
    if (n <= 7) return 3;
    return 4;
}

bool slack_better(const Rec& a, const Rec& b) {
    if (a.slack != b.slack) return a.slack > b.slack;
    return a.issue < b.issue;
}

void consider_top(std::array<Rec, kTopK>& top, int& ntop, const Rec& r) {
    if (r.op == Op::Pause || r.op == Op::Halt || r.pred_issue < 0) return;
    if (ntop < kTopK) {
        top[static_cast<std::size_t>(ntop++)] = r;
        return;
    }
    int wi = 0;
    for (int i = 1; i < ntop; ++i) {
        const Rec& a = top[static_cast<std::size_t>(i)];
        const Rec& w = top[static_cast<std::size_t>(wi)];
        if (a.slack < w.slack || (a.slack == w.slack && a.issue > w.issue)) wi = i;
    }
    Rec& w = top[static_cast<std::size_t>(wi)];
    if (slack_better(r, w)) w = r;
}

}  // namespace

std::string profile_json(const Program& program, const char* prev_json, const ProfileExtra* extra) {
    struct Cell {
        int last_issue = -1;
        int last_cp_raw = 0;
        int last_cp_waw = 0;
        int last_cp_mem = 0;
        int first_write = -1;
        int last_use = -1;
        int writes = 0;
        Op last_op = Op::Nop;
    };
    std::array<Cell, kDefaultScratch> cells{};
    int last_store_issue = -1;
    int last_store_cp_mem = 0;
    Op last_store_op = Op::Nop;

    std::array<std::int64_t, kNEng> eng_ops{};
    std::array<std::int64_t, 80> op_hist{};
    std::array<std::int64_t, kNPhase> phase_cycles{};
    std::array<std::int64_t, kNPhase> phase_alu{};
    std::array<std::int64_t, kNPhase> phase_valu{};
    std::array<std::int64_t, kNPhase> phase_load{};
    std::array<std::int64_t, kMaxDepth> depth_cycles{};
    std::array<std::int64_t, kMaxDepth> depth_gathers{};
    std::array<std::int64_t, kMaxDepth> depth_loads{};
    std::int64_t depth_unknown = 0;
    std::int64_t load_use_sum = 0;
    std::int64_t load_use_n = 0;
    std::int64_t war_same_cycle = 0;
    std::vector<int> load_use_d;
    std::vector<std::uint8_t> cycle_phase;
    std::array<int, kDefaultScratch> read_gen{};
    int war_gen = 1;
    const int nmax = static_cast<int>(program.bundles.size());
    load_use_d.reserve(4096);
    cycle_phase.reserve(static_cast<std::size_t>(nmax));
    const int hist_stride = nmax + 1;
    std::vector<int> slacks;
    slacks.reserve(static_cast<std::size_t>(nmax));
    std::array<Rec, kTopK> top_buf{};
    int ntop = 0;
    std::vector<int> ready_cnt(static_cast<std::size_t>(5) * static_cast<std::size_t>(hist_stride));
    std::vector<int> issue_cnt(static_cast<std::size_t>(5) * static_cast<std::size_t>(hist_stride));

    std::int64_t n_slots = 0;
    std::int64_t n_debug_bundles = 0;
    std::int64_t cycles = 0;
    int max_cp_raw = 0;
    int max_cp_waw = 0;
    int max_cp_mem = 0;
    std::int64_t slack_sum = 0;
    int slack_max = 0;
    bool has_jumps = false;
    std::uint64_t hash = 14695981039346656037ull;
    int billed_index = 0;

    AddrList reads;
    AddrList writes;
    PendingWrite pending[96];

    hash = fnv1a(hash, program.bundles.size());
    for (const Bundle& bundle : program.bundles) {
        const bool billed = (bundle.flags & kFlagNonDebug) != 0;
        if (!billed) {
            ++n_debug_bundles;
            continue;
        }
        const int issue = static_cast<int>(cycles);
        std::uint8_t phase = 0;
        if (extra && extra->phase && billed_index < extra->n_phase) {
            phase = extra->phase[billed_index];
            if (phase >= kNPhase) phase = 0;
        }
        int depth = -1;
        if (extra && extra->depth && billed_index < extra->n_depth) {
            const int raw_d = extra->depth[billed_index];
            if (raw_d < kMaxDepth) depth = raw_d;
        }
        ++phase_cycles[phase];
        if (depth >= 0) {
            ++depth_cycles[static_cast<std::size_t>(depth)];
        } else {
            ++depth_unknown;
        }
        ++billed_index;

        const Slot* slot_ptr = nullptr;
        int n = bundle.count;
        if (n <= 1) {
            slot_ptr = &bundle.one;
            n = bundle.count == 0 ? 0 : 1;
        } else {
            slot_ptr = program.slots.data() + bundle.begin;
        }

        int n_pending = 0;
        bool saw_store = false;
        Op store_op = Op::Nop;
        int store_cp_mem = 1;
        if (++war_gen == 0) {
            read_gen.fill(0);
            war_gen = 1;
        }
        for (int i = 0; i < n; ++i) {
            if (engine_of(slot_ptr[i].op) == Engine::Debug) continue;
            scratch_reads(slot_ptr[i], reads);
            for (int ri = 0; ri < reads.n; ++ri) {
                if (reads.v[ri] < static_cast<std::uint32_t>(kDefaultScratch)) {
                    read_gen[reads.v[ri]] = war_gen;
                }
            }
        }
        for (int i = 0; i < n; ++i) {
            if (engine_of(slot_ptr[i].op) == Engine::Debug) continue;
            scratch_writes(slot_ptr[i], writes);
            for (int wi = 0; wi < writes.n; ++wi) {
                if (writes.v[wi] < static_cast<std::uint32_t>(kDefaultScratch) &&
                    read_gen[writes.v[wi]] == war_gen) {
                    ++war_same_cycle;
                }
            }
        }

        for (int i = 0; i < n; ++i) {
            const Slot& slot = slot_ptr[i];
            const Engine eng = engine_of(slot.op);
            hash = fnv1a(hash, static_cast<std::uint64_t>(slot.op));
            hash = fnv1a(hash, slot.dest);
            hash = fnv1a(hash, slot.a);
            hash = fnv1a(hash, slot.b);
            hash = fnv1a(hash, slot.c);
            if (eng == Engine::Debug) continue;
            ++n_slots;
            ++eng_ops[static_cast<int>(eng)];
            if (eng == Engine::Alu) ++phase_alu[phase];
            if (eng == Engine::Valu) ++phase_valu[phase];
            if (eng == Engine::Load) ++phase_load[phase];
            if (slot.op == Op::Load || slot.op == Op::LoadOffset) {
                if (depth >= 0) ++depth_loads[static_cast<std::size_t>(depth)];
                if (phase == 6 && depth >= 0) ++depth_gathers[static_cast<std::size_t>(depth)];
            }
            const int oi = static_cast<int>(slot.op);
            if (oi >= 0 && oi < static_cast<int>(op_hist.size())) {
                ++op_hist[static_cast<std::size_t>(oi)];
            }
            if (is_jump(slot.op)) has_jumps = true;

            scratch_reads(slot, reads);
            scratch_writes(slot, writes);
            int ready = 0;
            int cp_raw = 1;
            int cp_waw = 1;
            int cp_mem = 1;
            int pred_issue = -1;
            Op pred_op = Op::Nop;
            auto bump_ready = [&](int pi, Op po) {
                if (pi < 0) return;
                const int r = pi + 1;
                if (r >= ready) {
                    ready = r;
                    pred_issue = pi;
                    pred_op = po;
                }
            };
            for (int ri = 0; ri < reads.n; ++ri) {
                const std::uint32_t addr = reads.v[ri];
                if (addr >= kDefaultScratch) continue;
                const Cell& cell = cells[addr];
                bump_ready(cell.last_issue, cell.last_op);
                if (cell.last_issue >= 0) {
                    cp_raw = std::max(cp_raw, cell.last_cp_raw + 1);
                    cp_waw = std::max(cp_waw, cell.last_cp_waw + 1);
                    cp_mem = std::max(cp_mem, cell.last_cp_mem + 1);
                }
                if (cell.first_write >= 0) {
                    cells[addr].last_use = std::max(cell.last_use, issue);
                }
            }
            for (int wi = 0; wi < writes.n; ++wi) {
                const std::uint32_t addr = writes.v[wi];
                if (addr >= kDefaultScratch) continue;
                const Cell& cell = cells[addr];
                bump_ready(cell.last_issue, cell.last_op);
                if (cell.last_issue >= 0) {
                    cp_waw = std::max(cp_waw, cell.last_cp_waw + 1);
                    cp_mem = std::max(cp_mem, cell.last_cp_mem + 1);
                }
            }
            if (is_load_mem(slot.op) && last_store_issue >= 0) {
                bump_ready(last_store_issue, last_store_op);
                cp_mem = std::max(cp_mem, last_store_cp_mem + 1);
            }

            const int slack = issue - ready;
            slacks.push_back(slack);
            slack_sum += slack;
            slack_max = std::max(slack_max, slack);
            max_cp_raw = std::max(max_cp_raw, cp_raw);
            max_cp_waw = std::max(max_cp_waw, cp_waw);
            max_cp_mem = std::max(max_cp_mem, cp_mem);

            Rec rec;
            rec.issue = issue;
            rec.ready = ready;
            rec.slack = slack;
            rec.eng = static_cast<int>(eng);
            rec.op = slot.op;
            rec.pred_issue = pred_issue;
            rec.pred_op = pred_op;
            rec.phase = phase;
            if (is_load_mem(pred_op) && pred_issue >= 0) {
                const int dist = issue - pred_issue;
                load_use_sum += dist;
                ++load_use_n;
                load_use_d.push_back(dist);
            }
            consider_top(top_buf, ntop, rec);
            if (rec.eng >= 0 && rec.eng <= 4) {
                const int rd = std::clamp(ready, 0, nmax);
                const int is = std::clamp(issue, 0, nmax);
                ++ready_cnt[static_cast<std::size_t>(rec.eng) * static_cast<std::size_t>(hist_stride) +
                            static_cast<std::size_t>(rd)];
                ++issue_cnt[static_cast<std::size_t>(rec.eng) * static_cast<std::size_t>(hist_stride) +
                            static_cast<std::size_t>(is)];
            }

            for (int wi = 0; wi < writes.n; ++wi) {
                const std::uint32_t addr = writes.v[wi];
                if (addr >= kDefaultScratch) continue;
                if (n_pending < 96) {
                    pending[n_pending++] = PendingWrite{addr, cp_raw, cp_waw, cp_mem, slot.op};
                }
            }
            if (is_store_mem(slot.op)) {
                saw_store = true;
                store_op = slot.op;
                store_cp_mem = cp_mem;
            }
        }
        for (int pi = 0; pi < n_pending; ++pi) {
            const PendingWrite& pw = pending[pi];
            Cell& cell = cells[pw.addr];
            if (cell.first_write < 0) cell.first_write = issue;
            cell.last_issue = issue;
            cell.last_cp_raw = pw.cp_raw;
            cell.last_cp_waw = pw.cp_waw;
            cell.last_cp_mem = pw.cp_mem;
            cell.last_use = std::max(cell.last_use, issue);
            cell.last_op = pw.op;
            ++cell.writes;
        }
        if (saw_store) {
            last_store_issue = issue;
            last_store_cp_mem = store_cp_mem;
            last_store_op = store_op;
        }
        cycle_phase.push_back(phase);
        ++cycles;
    }

    std::int64_t work_bound = 0;
    std::array<std::int64_t, kNEng> eng_bound{};
    std::array<double, kNEng> occ{};
    for (int e = 0; e < 5; ++e) {
        const int lim = kSlotLimit[e];
        eng_bound[static_cast<std::size_t>(e)] =
            lim > 0 ? (eng_ops[static_cast<std::size_t>(e)] + lim - 1) / lim : 0;
        work_bound = std::max(work_bound, eng_bound[static_cast<std::size_t>(e)]);
        const double den = static_cast<double>(std::max<std::int64_t>(cycles, 1)) * lim;
        occ[static_cast<std::size_t>(e)] =
            den > 0 ? static_cast<double>(eng_ops[static_cast<std::size_t>(e)]) / den : 0;
    }
    int floor_e = 0;
    constexpr int kFloorPref[] = {1, 2, 4, 0, 3};
    for (int e : kFloorPref) {
        if (eng_bound[static_cast<std::size_t>(e)] == work_bound) {
            floor_e = e;
            break;
        }
    }
    const std::int64_t overhead = std::max<std::int64_t>(0, cycles - work_bound);
    const double overhead_frac =
        cycles > 0 ? static_cast<double>(overhead) / static_cast<double>(cycles) : 0;

    int peak_live = 0;
    int cells_touched = 0;
    std::vector<int> live_delta(static_cast<std::size_t>(std::max<std::int64_t>(cycles, 0) + 2));
    {
        std::vector<std::pair<int, int>> ev;
        ev.reserve(64);
        for (const Cell& c : cells) {
            if (c.first_write < 0) continue;
            ++cells_touched;
            ev.emplace_back(c.first_write, 1);
            ev.emplace_back(c.last_use + 1, -1);
            if (c.first_write >= 0 && c.first_write <= cycles) {
                ++live_delta[static_cast<std::size_t>(c.first_write)];
            }
            const int end = std::min(c.last_use + 1, static_cast<int>(cycles));
            if (end >= 0 && end <= cycles) {
                --live_delta[static_cast<std::size_t>(end)];
            }
        }
        std::sort(ev.begin(), ev.end());
        int live = 0;
        for (const auto& [t, d] : ev) {
            live += d;
            peak_live = std::max(peak_live, live);
        }
    }

    std::array<std::int64_t, 5> rni_hist{};
    std::array<std::int64_t, 7> limit_hist{};
    std::array<std::int64_t, 5> port_full{};
    std::int64_t sat_cycles = 0;
    std::int64_t mix_valu_hungry = 0;
    std::int64_t mix_load_hungry = 0;
    std::int64_t mix_flow_hungry = 0;
    std::int64_t mix_balanced = 0;
    std::int64_t mix_empty = 0;
    std::int64_t zero_load_cycles = 0;
    std::int64_t load0_valu_lt6 = 0;
    std::int64_t live_sum = 0;
    std::array<std::int64_t, 13> occ_alu{};
    std::array<std::int64_t, 7> occ_valu{};
    std::array<std::int64_t, 3> occ_load{};
    std::array<std::int64_t, 3> occ_store{};
    std::array<std::int64_t, 2> occ_flow{};
    std::array<std::int64_t, 193> live_hist{};
    double rni_mean = 0;
    std::vector<char> mix_seq;
    std::array<std::vector<std::uint8_t>, 5> used_series{};
    std::vector<int> pressure_series;
    int series_n = 0;
    int series_stride = 1;
    const bool detail_series = eng_ops[1] > 0 && overhead_frac < 0.30;
    std::array<std::vector<std::uint8_t>, 5> used_by{};
    if (cycles > 0 && n_slots > 0) {
        mix_seq.reserve(static_cast<std::size_t>(cycles));
        const int ncy = static_cast<int>(cycles);
        if (detail_series) {
            series_n = ncy <= kSeriesMax ? ncy : kSeriesMax;
            series_stride = (ncy + series_n - 1) / series_n;
            pressure_series.assign(static_cast<std::size_t>(series_n), 0);
            for (int e = 0; e < 5; ++e) {
                used_series[static_cast<std::size_t>(e)].assign(
                    static_cast<std::size_t>(series_n), 0);
            }
        }
        for (int e = 0; e < 5; ++e) {
            used_by[static_cast<std::size_t>(e)].assign(static_cast<std::size_t>(ncy), 0);
        }
        auto at = [&](std::vector<int>& v, int e, int c) -> int& {
            return v[static_cast<std::size_t>(e) * static_cast<std::size_t>(hist_stride) +
                     static_cast<std::size_t>(c)];
        };
        std::int64_t rni_sum = 0;
        std::array<int, 5> ready_run{};
        std::array<int, 5> issue_run{};
        int live = 0;
        for (int c = 0; c < ncy; ++c) {
            live += live_delta[static_cast<std::size_t>(c)];
            live_sum += live;
            const int lh = std::min(live / 8, 192);
            ++live_hist[static_cast<std::size_t>(lh)];
            int pool = 0;
            int issued = 0;
            std::array<int, 5> want{};
            std::array<int, 5> used{};
            for (int e = 0; e < 5; ++e) {
                ready_run[static_cast<std::size_t>(e)] += at(ready_cnt, e, c);
                want[static_cast<std::size_t>(e)] =
                    ready_run[static_cast<std::size_t>(e)] - issue_run[static_cast<std::size_t>(e)];
                used[static_cast<std::size_t>(e)] = at(issue_cnt, e, c);
                pool += want[static_cast<std::size_t>(e)];
                issued += used[static_cast<std::size_t>(e)];
                issue_run[static_cast<std::size_t>(e)] += used[static_cast<std::size_t>(e)];
                const int u = std::min(used[static_cast<std::size_t>(e)], kSlotLimit[e]);
                used_by[static_cast<std::size_t>(e)][static_cast<std::size_t>(c)] =
                    static_cast<std::uint8_t>(u);
            }
            if (used[2] == 0) ++zero_load_cycles;
            if (used[2] == 0 && used[1] < 6) ++load0_valu_lt6;
            ++occ_alu[static_cast<std::size_t>(std::min(used[0], 12))];
            ++occ_valu[static_cast<std::size_t>(std::min(used[1], 6))];
            ++occ_load[static_cast<std::size_t>(std::min(used[2], 2))];
            ++occ_store[static_cast<std::size_t>(std::min(used[3], 2))];
            ++occ_flow[static_cast<std::size_t>(std::min(used[4], 1))];
            if (detail_series && series_n > 0) {
                const int bucket = std::min(c / series_stride, series_n - 1);
                for (int e = 0; e < 5; ++e) {
                    auto& cell =
                        used_series[static_cast<std::size_t>(e)][static_cast<std::size_t>(bucket)];
                    cell = static_cast<std::uint8_t>(
                        std::max<int>(cell, used[static_cast<std::size_t>(e)]));
                }
                pressure_series[static_cast<std::size_t>(bucket)] =
                    std::max(pressure_series[static_cast<std::size_t>(bucket)], live);
            }
            const int not_issued = std::max(0, pool - issued);
            rni_sum += not_issued;
            ++rni_hist[static_cast<std::size_t>(rni_bucket(not_issued))];
            int best = -1;
            double best_ratio = 0;
            for (int e = 0; e < 5; ++e) {
                const int lim = kSlotLimit[e];
                if (lim <= 0) continue;
                const int u = used[static_cast<std::size_t>(e)];
                const int w = want[static_cast<std::size_t>(e)];
                if (u >= lim && w > u) {
                    const double ratio = static_cast<double>(w) / static_cast<double>(lim);
                    if (ratio > best_ratio) {
                        best_ratio = ratio;
                        best = e;
                    }
                }
            }
            if (best >= 0) {
                ++limit_hist[static_cast<std::size_t>(best)];
            } else if (not_issued > 0) {
                ++limit_hist[5];
            } else {
                ++limit_hist[6];
            }
            for (int e = 0; e < 5; ++e) {
                const int lim = kSlotLimit[e];
                if (lim > 0 && used[static_cast<std::size_t>(e)] >= lim) {
                    ++port_full[static_cast<std::size_t>(e)];
                }
            }
            const int flim = kSlotLimit[floor_e];
            if (flim > 0 && used[static_cast<std::size_t>(floor_e)] * 5 >= flim * 4) {
                ++sat_cycles;
            }
            const double fv = static_cast<double>(used[1]) / 6.0;
            const double fl = static_cast<double>(used[2]) / 2.0;
            const double ff = static_cast<double>(used[4]) / 1.0;
            const double mx = std::max(fv, std::max(fl, ff));
            const double mn = std::min(fv, std::min(fl, ff));
            char cls = 'e';
            if (mx < 0.01) {
                ++mix_empty;
                cls = 'e';
            } else if (mx - mn <= 0.34) {
                ++mix_balanced;
                cls = 'b';
            } else if (mn == fv) {
                ++mix_valu_hungry;
                cls = 'v';
            } else if (mn == fl) {
                ++mix_load_hungry;
                cls = 'l';
            } else {
                ++mix_flow_hungry;
                cls = 'f';
            }
            mix_seq.push_back(cls);
        }
        rni_mean = static_cast<double>(rni_sum) / static_cast<double>(ncy);
    }

    struct RegionStat {
        std::int64_t cycles = 0;
        std::int64_t zero_load = 0;
        std::int64_t load0_valu_lt6 = 0;
        std::int64_t valu_unused = 0;
        std::int64_t load_unused = 0;
        std::int64_t store_unused = 0;
        std::int64_t alu_unused = 0;
        std::int64_t flow_unused = 0;
        std::array<std::int64_t, kNPhase> phase{};
    };
    int startup_end = 0;
    int drain_start = static_cast<int>(cycles);
    const int ncy_reg = static_cast<int>(cycles);
    while (startup_end < ncy_reg && startup_end < static_cast<int>(cycle_phase.size()) &&
           cycle_phase[static_cast<std::size_t>(startup_end)] == 1) {
        ++startup_end;
    }
    while (drain_start > startup_end && drain_start - 1 < static_cast<int>(cycle_phase.size()) &&
           cycle_phase[static_cast<std::size_t>(drain_start - 1)] == 1) {
        --drain_start;
    }
    if (!used_by[0].empty()) {
        while (drain_start > startup_end) {
            const int c = drain_start - 1;
            const int work = used_by[0][static_cast<std::size_t>(c)] +
                             used_by[1][static_cast<std::size_t>(c)] +
                             used_by[2][static_cast<std::size_t>(c)] +
                             used_by[3][static_cast<std::size_t>(c)];
            if (work == 0) {
                --drain_start;
            } else {
                break;
            }
        }
    }
    auto fill_region = [&](RegionStat& r, int lo, int hi) {
        for (int c = lo; c < hi; ++c) {
            ++r.cycles;
            if (c < static_cast<int>(cycle_phase.size())) {
                const int ph = cycle_phase[static_cast<std::size_t>(c)];
                if (ph >= 0 && ph < kNPhase) ++r.phase[static_cast<std::size_t>(ph)];
            }
            if (used_by[0].empty()) continue;
            const int ua = used_by[0][static_cast<std::size_t>(c)];
            const int uv = used_by[1][static_cast<std::size_t>(c)];
            const int ul = used_by[2][static_cast<std::size_t>(c)];
            const int us = used_by[3][static_cast<std::size_t>(c)];
            const int uf = used_by[4][static_cast<std::size_t>(c)];
            if (ul == 0) ++r.zero_load;
            if (ul == 0 && uv < 6) ++r.load0_valu_lt6;
            r.alu_unused += 12 - ua;
            r.valu_unused += 6 - uv;
            r.load_unused += 2 - ul;
            r.store_unused += 2 - us;
            r.flow_unused += 1 - uf;
        }
    };
    RegionStat region_startup;
    RegionStat region_steady;
    RegionStat region_drain;
    fill_region(region_startup, 0, startup_end);
    fill_region(region_steady, startup_end, drain_start);
    fill_region(region_drain, drain_start, ncy_reg);
    int pressure_p50 = 0;
    {
        std::int64_t seen = 0;
        const std::int64_t half = std::max<std::int64_t>(cycles, 1) / 2;
        for (int b = 0; b < 193; ++b) {
            seen += live_hist[static_cast<std::size_t>(b)];
            if (seen >= half) {
                pressure_p50 = b * 8;
                break;
            }
        }
    }
    const double pressure_mean =
        cycles > 0 ? static_cast<double>(live_sum) / static_cast<double>(cycles) : 0.0;

    std::vector<Rec> top;
    top.assign(top_buf.begin(), top_buf.begin() + ntop);
    std::sort(top.begin(), top.end(), slack_better);

    struct NamedLive {
        std::string name;
        std::uint32_t addr = 0;
        int length = 0;
        int first = -1;
        int last = -1;
        int writes = 0;
        int cells = 0;
        bool loop_carried = false;
    };
    std::vector<NamedLive> named;
    if (extra && extra->n_scratch > 0 && extra->scratch_addr && extra->scratch_len &&
        extra->scratch_names) {
        named.reserve(static_cast<std::size_t>(extra->n_scratch));
        const int span_cut = std::max(16, static_cast<int>(cycles / 8));
        for (int i = 0; i < extra->n_scratch; ++i) {
            const std::uint32_t base = extra->scratch_addr[i];
            const int length = extra->scratch_len[i];
            const char* nm = extra->scratch_names[i];
            NamedLive nl;
            nl.name = nm ? nm : "";
            nl.addr = base;
            nl.length = length;
            for (int o = 0; o < length; ++o) {
                const std::uint32_t addr = base + static_cast<std::uint32_t>(o);
                if (addr >= kDefaultScratch) break;
                const Cell& cell = cells[addr];
                if (cell.first_write < 0) continue;
                ++nl.cells;
                nl.writes += cell.writes;
                nl.first = nl.first < 0 ? cell.first_write : std::min(nl.first, cell.first_write);
                nl.last = std::max(nl.last, cell.last_use);
            }
            if (nl.cells == 0) continue;
            const int span = nl.last - nl.first + 1;
            nl.loop_carried = nl.writes >= 3 && span > span_cut;
            named.push_back(std::move(nl));
        }
        std::sort(named.begin(), named.end(), [](const NamedLive& a, const NamedLive& b) {
            if (a.writes != b.writes) return a.writes > b.writes;
            return (a.last - a.first) > (b.last - b.first);
        });
    }

    const int max_cp = max_cp_waw;
    const double ipc = cycles > 0 ? static_cast<double>(n_slots) / static_cast<double>(cycles) : 0;
    const double dep_p =
        cycles > 0 ? static_cast<double>(max_cp) / static_cast<double>(cycles) : 0;
    const double res_p =
        cycles > 0 ? static_cast<double>(work_bound) / static_cast<double>(cycles) : 0;
    const double sched_waste = 1.0 - std::max(dep_p, res_p);
    const double slack_mean =
        slacks.empty() ? 0.0 : static_cast<double>(slack_sum) / static_cast<double>(slacks.size());
    int slack_p50 = 0;
    if (!slacks.empty()) {
        std::nth_element(slacks.begin(), slacks.begin() + slacks.size() / 2, slacks.end());
        slack_p50 = slacks[slacks.size() / 2];
    }
    const char* idle_cause = "schedule";
    if (slack_p50 >= 1 && sched_waste >= 0.30) {
        idle_cause = "schedule";
    } else if (dep_p >= res_p && dep_p >= 0.45) {
        idle_cause = "deps";
    } else if (res_p >= 0.45) {
        idle_cause = "ports";
    }
    const char* bottleneck = "mixed";
    if (dep_p > res_p + 0.05) {
        bottleneck = "deps";
    } else if (res_p > dep_p + 0.05) {
        bottleneck = "ports";
    } else if (sched_waste >= 0.30) {
        bottleneck = "schedule";
    }

    std::vector<std::pair<std::int64_t, const char*>> tops;
    for (int i = 0; i < static_cast<int>(op_hist.size()); ++i) {
        if (op_hist[static_cast<std::size_t>(i)] > 0) {
            tops.emplace_back(op_hist[static_cast<std::size_t>(i)], op_name(static_cast<Op>(i)));
        }
    }
    std::sort(tops.begin(), tops.end(),
              [](const auto& a, const auto& b) { return a.first > b.first; });
    if (tops.size() > 8) tops.resize(8);

    auto n_op = [&](Op op) -> std::int64_t {
        const int i = static_cast<int>(op);
        if (i < 0 || i >= static_cast<int>(op_hist.size())) return 0;
        return op_hist[static_cast<std::size_t>(i)];
    };
    const std::int64_t gather_scalar = n_op(Op::Load);
    const std::int64_t vload_n = n_op(Op::VLoad);
    const std::int64_t const_n = n_op(Op::Const);
    const std::int64_t select_n = n_op(Op::Select);
    const std::int64_t vselect_n = n_op(Op::VSelect);
    const std::int64_t madd_n = n_op(Op::ValuMadd);
    const std::int64_t vstore_n = n_op(Op::VStore);
    const std::int64_t store_n = n_op(Op::Store);
    const double valu_per_load =
        eng_ops[2] > 0 ? static_cast<double>(eng_ops[1]) / static_cast<double>(eng_ops[2]) : 0;
    const double load_per_flow =
        eng_ops[4] > 0 ? static_cast<double>(eng_ops[2]) / static_cast<double>(eng_ops[4]) : 0;
    const double valu_per_flow =
        eng_ops[4] > 0 ? static_cast<double>(eng_ops[1]) / static_cast<double>(eng_ops[4]) : 0;
    const char* mix_imbalance = "balanced";
    if (eng_ops[1] == 0 && eng_ops[0] > eng_ops[2]) {
        mix_imbalance = "scalar_alu";
    } else if (eng_bound[2] > eng_bound[1] + std::max<std::int64_t>(eng_bound[1] / 6, 2)) {
        mix_imbalance = "load_heavy";
    } else if (eng_bound[1] > eng_bound[2] + std::max<std::int64_t>(eng_bound[2] / 6, 2)) {
        mix_imbalance = "valu_heavy";
    } else if (eng_bound[4] >= work_bound && work_bound > 0) {
        mix_imbalance = "flow_heavy";
    }

    auto ceil_div = [](std::int64_t a, std::int64_t b) -> std::int64_t {
        if (b <= 0) return 0;
        return (a + b - 1) / b;
    };
    const int shape_h = extra ? extra->forest_height : 0;
    const int shape_r = extra ? extra->rounds : 0;
    const int shape_b = extra ? extra->batch_size : 0;
    const std::int64_t item_rounds =
        (shape_r > 0 && shape_b > 0) ? static_cast<std::int64_t>(shape_r) * shape_b : 0;
    const std::int64_t tiles = shape_b >= 8 ? shape_b / 8 : (shape_b > 0 ? shape_b : 0);
    const std::int64_t valu_floor = ceil_div(eng_ops[1], 6);
    const std::int64_t alu_floor = ceil_div(eng_ops[0], 12);
    const std::int64_t load_floor = ceil_div(eng_ops[2], 2);
    const std::int64_t store_floor = ceil_div(eng_ops[3], 2);
    const std::int64_t flow_floor = eng_ops[4];
    const std::int64_t gather_floor = ceil_div(gather_scalar, 2);
    const std::int64_t gather_floor_all = item_rounds > 0 ? ceil_div(item_rounds, 2) : 0;
    const std::int64_t fused_hash_floor =
        (tiles > 0 && shape_r > 0) ? ceil_div(tiles * shape_r * 12, 6) : 0;
    const std::int64_t useful_op_floor = item_rounds > 0 ? ceil_div(item_rounds * 16, 60) : 0;
    const int peak_vecs = (peak_live + 7) / 8;
    const int cap_vecs = kDefaultScratch / 8;
    const double load_to_use =
        load_use_n > 0 ? static_cast<double>(load_use_sum) / static_cast<double>(load_use_n) : 0.0;
    int load_use_p50 = 0;
    int load_use_p95 = 0;
    std::array<std::int64_t, 7> load_use_hist{};
    if (!load_use_d.empty()) {
        auto sorted = load_use_d;
        std::sort(sorted.begin(), sorted.end());
        load_use_p50 = sorted[(sorted.size() - 1) / 2];
        load_use_p95 = sorted[(sorted.size() - 1) * 95 / 100];
        for (int d : load_use_d) ++load_use_hist[static_cast<std::size_t>(load_use_bucket(d))];
    }
    const double tiles_in_flight = eng_ops[1] > 0 ? static_cast<double>(peak_live) / 8.0 : 1.0;
    const double ii_est =
        item_rounds > 0 && region_steady.cycles > 0
            ? static_cast<double>(region_steady.cycles) / static_cast<double>(item_rounds)
            : 0.0;
    std::int64_t shallow_gathers = 0;
    for (int d = 0; d <= 3; ++d) shallow_gathers += depth_gathers[static_cast<std::size_t>(d)];
    int waw_conflicts = 0;
    int war_named_overlaps = 0;
    struct LiveOverlap {
        std::string a;
        std::string b;
        int cycles = 0;
    };
    std::vector<LiveOverlap> live_overlaps;
    for (std::size_t i = 0; i < named.size(); ++i) {
        for (std::size_t j = i + 1; j < named.size(); ++j) {
            const NamedLive& a = named[i];
            const NamedLive& b = named[j];
            if (a.last < b.first || b.last < a.first) continue;
            const int ov = std::min(a.last, b.last) - std::max(a.first, b.first) + 1;
            if (ov <= 0) continue;
            ++war_named_overlaps;
            if (a.writes >= 2 && b.writes >= 2) ++waw_conflicts;
            LiveOverlap row{a.name, b.name, ov};
            if (live_overlaps.size() < 8) {
                live_overlaps.push_back(std::move(row));
            } else {
                auto it = std::min_element(
                    live_overlaps.begin(), live_overlaps.end(),
                    [](const LiveOverlap& x, const LiveOverlap& y) { return x.cycles < y.cycles; });
                if (ov > it->cycles) *it = std::move(row);
            }
        }
    }
    std::sort(live_overlaps.begin(), live_overlaps.end(),
              [](const LiveOverlap& a, const LiveOverlap& b) { return a.cycles > b.cycles; });
    if (named.size() > 12) named.resize(12);
    std::string mix_rle;
    if (!mix_seq.empty()) {
        char cur = mix_seq[0];
        int run = 1;
        for (std::size_t i = 1; i <= mix_seq.size(); ++i) {
            if (i < mix_seq.size() && mix_seq[i] == cur) {
                ++run;
                continue;
            }
            if (!mix_rle.empty()) mix_rle += ',';
            mix_rle += cur;
            mix_rle += std::to_string(run);
            if (i < mix_seq.size()) {
                cur = mix_seq[i];
                run = 1;
            }
        }
    }
    const std::int64_t hash_like = n_op(Op::AluXor) + n_op(Op::ValuXor) + madd_n +
                                   n_op(Op::AluShl) + n_op(Op::ValuShl) + n_op(Op::AluShr) +
                                   n_op(Op::ValuShr);
    const bool hash_present = hash_like > 0;
    const bool index_stores = store_n + vstore_n > 0;
    const bool mux_used = vselect_n > 0 || (select_n > 8 && shallow_gathers == 0);
    const bool suspect_skip_hash = item_rounds > 64 && hash_like < item_rounds / 4;
    const bool suspect_cheat = gather_floor_all > 0 && cycles > 0 && cycles * 4 < gather_floor_all &&
                               eng_ops[1] == 0 && gather_scalar * 2 < item_rounds;

    struct Hyp {
        const char* tag;
        std::string why;
    };
    std::vector<Hyp> hyps;
    if (eng_ops[1] == 0) {
        hyps.push_back({"valu_unused", "valu_ops=0; SIMD ports idle"});
    }
    if (ipc < 1.5) {
        hyps.push_back({"pipeline", "ipc<1.5; pack independent work into one bundle"});
    }
    if (cycles > 0 && limit_hist[5] * 2 >= cycles) {
        hyps.push_back({"oneslot", "ready ops wait on 1-slot issue policy"});
    }
    if (max_cp_waw > max_cp_raw + 8 &&
        static_cast<double>(max_cp_waw) > static_cast<double>(max_cp_raw) * 1.15) {
        hyps.push_back({"store_lifetime", "cp_waw >> cp_raw; rename temps / shorten live ranges"});
    }
    if (gather_scalar > 8 && vselect_n * 4 < gather_scalar && vload_n == 0) {
        hyps.push_back({"gather", "many load.load, no vload/vselect; preload shallow levels"});
    }
    if (vselect_n > 0 && eng_bound[4] >= eng_bound[2] && eng_bound[4] > 0) {
        hyps.push_back({"index_pattern", "select-heavy; flow is near the port floor"});
    }
    if (cycles > 0 && phase_cycles[3] * 5 >= cycles * 2) {
        hyps.push_back({"hash", "hash dominates issue cycles; fuse or overlap with loads"});
    }
    if (floor_e == 2 || (gather_scalar > 0 && vload_n == 0 && eng_ops[1] == 0)) {
        hyps.push_back({"memory_layout", "scalar loads set the floor; vload or select-tree"});
    }
    if (eng_bound[4] == work_bound && work_bound > 0 && floor_e == 4) {
        hyps.push_back({"control_bounds", "flow is the port floor; trade vselect for valu"});
    }
    if (peak_live * 2 > kDefaultScratch) {
        hyps.push_back({"scratch", "live ranges near 1536; reuse short-lived vectors"});
    }
    if (shallow_gathers > 8) {
        hyps.push_back({"gather_depth", "L0-3 still gather; select-tree is cheaper"});
    }
    if (cycles > 64 && region_drain.cycles > 8 && region_drain.cycles * 8 >= cycles) {
        hyps.push_back({"tail_drain", "drain region is a large share of cycles"});
    }
    if (region_steady.cycles > 32 && eng_ops[1] > 0 &&
        region_steady.zero_load * 5 >= region_steady.cycles) {
        hyps.push_back({"steady_idle_load", "steady cycles often issue no load while VALU is used"});
    }
    if (suspect_skip_hash) {
        hyps.push_back({"integrity", "few hash-like ops vs item-rounds; possible hash skip"});
    }
    if (hyps.size() > 8) hyps.resize(8);

    std::vector<std::string> hints;
    if (eng_ops[1] == 0) hints.emplace_back("valu unused; SIMD ports are idle");
    if (ipc < 1.5) hints.emplace_back("low ipc; most bundles issue 1 slot");
    if (sched_waste >= 0.5) hints.emplace_back("idle is mostly schedule/policy, not RAW deps");
    if (dep_p >= 0.45) hints.emplace_back("critical path is a large share of cycles; shorten deps");
    if (res_p >= 0.45) hints.emplace_back("near engine port bound; reduce ops or change mix");
    if (n_slots > 1000 && cells_touched < 64) {
        hints.emplace_back("few scratch cells vs op count; temp reuse can serialize the loop");
    }
    if (peak_live * 2 > kDefaultScratch) hints.emplace_back("scratch lifetimes near capacity");
    if (has_jumps) hints.emplace_back("jumps present; ready/issue assumes fall-through order");
    if (max_cp_mem > max_cp_waw + 8 &&
        static_cast<double>(max_cp_mem) > static_cast<double>(max_cp_waw) * 1.15) {
        hints.emplace_back("cp_mem inflated by conservative store-to-load aliasing");
    }
    if (max_cp_waw > max_cp_raw + 8 &&
        static_cast<double>(max_cp_waw) > static_cast<double>(max_cp_raw) * 1.15) {
        hints.emplace_back("WAW/temp reuse lengthens the chain; more scratch names would shorten cp");
    }
    if (cycles > 0 && phase_cycles[3] * 5 >= cycles * 2) {
        hints.emplace_back("hash dominates issue cycles");
    }
    if (cycles > 0 && limit_hist[5] * 2 >= cycles) {
        hints.emplace_back("ready ops often wait on 1-slot issue policy, not port limits");
    }
    if (overhead > 0 && work_bound > 0 && overhead * 2 >= cycles) {
        hints.emplace_back("cycles >> port floor; mix or packing, not op count, is the gap");
    }
    if (gather_scalar > 8 && vselect_n == 0) {
        hints.emplace_back("L0-3 tree nodes: select-tree beats gather (8 loads); L5+ keep gather");
    }
    if (cycles > 64 && region_drain.cycles > 8 && region_drain.cycles * 8 >= cycles) {
        hints.emplace_back("tail drain is a large share of cycles; overlap stores with leftover compute");
    }
    if (region_steady.cycles > 32 && eng_ops[1] > 0 &&
        region_steady.zero_load * 5 >= region_steady.cycles) {
        hints.emplace_back("steady has many zero-load cycles; interleave gathers with hash");
    }

    char fp[17];
    std::snprintf(fp, sizeof(fp), "%016llx", static_cast<unsigned long long>(hash));

    std::int64_t prev_cycles = -1, prev_cp = -1, prev_wb = -1, prev_peak = -1;
    std::int64_t prev_raw = -1, prev_waw = -1, prev_mem = -1;
    std::int64_t prev_oh = -1, prev_gather = -1, prev_vsel = -1;
    std::array<std::int64_t, 5> prev_ops{-1, -1, -1, -1, -1};
    double prev_ipc = -1, prev_waste = -1;
    std::string prev_cause, prev_fp, prev_bn, prev_floor;
    const bool have_prev = prev_json && prev_json[0];
    if (have_prev) {
        json_i64(prev_json, "cycles_est", &prev_cycles);
        json_i64(prev_json, "critical_path", &prev_cp);
        json_i64(prev_json, "work_bound", &prev_wb);
        json_i64(prev_json, "peak_live", &prev_peak);
        json_i64(prev_json, "cp_raw", &prev_raw);
        json_i64(prev_json, "cp_waw", &prev_waw);
        json_i64(prev_json, "cp_mem", &prev_mem);
        json_i64(prev_json, "alu_ops", &prev_ops[0]);
        json_i64(prev_json, "valu_ops", &prev_ops[1]);
        json_i64(prev_json, "load_ops", &prev_ops[2]);
        json_i64(prev_json, "store_ops", &prev_ops[3]);
        json_i64(prev_json, "flow_ops", &prev_ops[4]);
        json_f64(prev_json, "ipc", &prev_ipc);
        json_f64(prev_json, "schedule_waste", &prev_waste);
        json_i64(prev_json, "overhead", &prev_oh);
        json_i64(prev_json, "gather_scalar", &prev_gather);
        json_i64(prev_json, "vselect_ops", &prev_vsel);
        json_find(prev_json, "idle_cause", &prev_cause);
        json_find(prev_json, "bottleneck", &prev_bn);
        json_find(prev_json, "floor_engine", &prev_floor);
        json_find(prev_json, "fingerprint", &prev_fp);
    }

    std::ostringstream o;
    o.setf(std::ios::fixed);
    o.precision(4);
    o << "{\n";
    o << "  \"fingerprint\": \"" << fp << "\",\n";
    o << "  \"assumes_linear\": " << (has_jumps ? "false" : "true") << ",\n";
    o << "  \"has_jumps\": " << (has_jumps ? "true" : "false") << ",\n";
    o << "  \"bundles\": " << program.bundles.size() << ",\n";
    o << "  \"debug_bundles\": " << n_debug_bundles << ",\n";
    o << "  \"slots\": " << n_slots << ",\n";
    o << "  \"cycles_est\": " << cycles << ",\n";
    o << "  \"ipc\": " << ipc << ",\n";
    o << "  \"work_bound\": " << work_bound << ",\n";
    o << "  \"floor\": " << work_bound << ",\n";
    o << "  \"floor_engine\": \"" << kEngName[floor_e] << "\",\n";
    o << "  \"overhead\": " << overhead << ",\n";
    o << "  \"overhead_frac\": " << overhead_frac << ",\n";
    o << "  \"saturation_cycles\": " << sat_cycles << ",\n";
    o << "  \"critical_path\": " << max_cp << ",\n";
    o << "  \"cp_raw\": " << max_cp_raw << ",\n";
    o << "  \"cp_waw\": " << max_cp_waw << ",\n";
    o << "  \"cp_mem\": " << max_cp_mem << ",\n";
    o << "  \"alu_ops\": " << eng_ops[0] << ",\n";
    o << "  \"valu_ops\": " << eng_ops[1] << ",\n";
    o << "  \"load_ops\": " << eng_ops[2] << ",\n";
    o << "  \"store_ops\": " << eng_ops[3] << ",\n";
    o << "  \"flow_ops\": " << eng_ops[4] << ",\n";
    o << "  \"dep_pressure\": " << dep_p << ",\n";
    o << "  \"resource_pressure\": " << res_p << ",\n";
    o << "  \"schedule_waste\": " << sched_waste << ",\n";
    o << "  \"idle_cause\": \"" << idle_cause << "\",\n";
    o << "  \"bottleneck\": \"" << bottleneck << "\",\n";
    o << "  \"slack_mean\": " << slack_mean << ",\n";
    o << "  \"slack_p50\": " << slack_p50 << ",\n";
    o << "  \"slack_max\": " << slack_max << ",\n";
    o << "  \"ready_not_issued_mean\": " << rni_mean << ",\n";
    o << "  \"peak_live\": " << peak_live << ",\n";
    o << "  \"scratch_capacity\": " << kDefaultScratch << ",\n";
    o << "  \"cells_touched\": " << cells_touched << ",\n";
    o << "  \"zero_load_cycles\": " << zero_load_cycles << ",\n";
    o << "  \"load0_valu_lt6\": " << load0_valu_lt6 << ",\n";
    o << "  \"war_same_cycle\": " << war_same_cycle << ",\n";
    o << "  \"war_named_overlaps\": " << war_named_overlaps << ",\n";
    o << "  \"phase_unknown\": " << phase_cycles[0] << ",\n";
    o << "  \"phase_init\": " << phase_cycles[1] << ",\n";
    o << "  \"phase_ldst\": " << phase_cycles[2] << ",\n";
    o << "  \"phase_hash\": " << phase_cycles[3] << ",\n";
    o << "  \"phase_walk\": " << phase_cycles[4] << ",\n";
    o << "  \"phase_store\": " << phase_cycles[5] << ",\n";
    o << "  \"phase_gather\": " << phase_cycles[6] << ",\n";
    o << "  \"gather_scalar\": " << gather_scalar << ",\n";
    o << "  \"vload_ops\": " << vload_n << ",\n";
    o << "  \"vstore_ops\": " << vstore_n << ",\n";
    o << "  \"store_scalar\": " << store_n << ",\n";
    o << "  \"const_ops\": " << const_n << ",\n";
    o << "  \"select_ops\": " << select_n << ",\n";
    o << "  \"vselect_ops\": " << vselect_n << ",\n";
    o << "  \"madd_ops\": " << madd_n << ",\n";
    o << "  \"mix_imbalance\": \"" << mix_imbalance << "\",\n";
    o << "  \"valu_per_load\": " << valu_per_load << ",\n";
    o << "  \"load_per_flow\": " << load_per_flow << ",\n";
    o << "  \"valu_per_flow\": " << valu_per_flow << ",\n";
    o << "  \"engines\": {\n";
    for (int e = 0; e < 5; ++e) {
        o << "    \"" << kEngName[e] << "\": {\"ops\": " << eng_ops[static_cast<std::size_t>(e)]
          << ", \"limit\": " << kSlotLimit[e]
          << ", \"occupancy\": " << occ[static_cast<std::size_t>(e)]
          << ", \"work_bound\": " << eng_bound[static_cast<std::size_t>(e)] << "}";
        o << (e == 4 ? "\n" : ",\n");
    }
    o << "  },\n";
    o << "  \"phases\": {";
    for (int i = 0; i < kNPhase; ++i) {
        if (i) o << ", ";
        o << "\"" << kPhaseName[i] << "\": " << phase_cycles[static_cast<std::size_t>(i)];
    }
    o << "},\n";
    o << "  \"ready_not_issued\": {";
    for (int i = 0; i < 5; ++i) {
        if (i) o << ", ";
        o << "\"" << kRniName[i] << "\": " << rni_hist[static_cast<std::size_t>(i)];
    }
    o << "},\n";
    o << "  \"limit_engine\": {";
    for (int i = 0; i < 7; ++i) {
        if (i) o << ", ";
        o << "\"" << kLimitName[i] << "\": " << limit_hist[static_cast<std::size_t>(i)];
    }
    o << "},\n";
    o << "  \"port_full\": {";
    for (int e = 0; e < 5; ++e) {
        if (e) o << ", ";
        o << "\"" << kEngName[e] << "\": " << port_full[static_cast<std::size_t>(e)];
    }
    o << "},\n";
    o << "  \"mix\": {";
    o << "\"target\": {\"valu\": 6, \"load\": 2, \"store\": 2, \"flow\": 1}";
    o << ", \"imbalance\": \"" << mix_imbalance << "\"";
    o << ", \"valu_per_load\": " << valu_per_load;
    o << ", \"load_per_flow\": " << load_per_flow;
    o << ", \"valu_per_flow\": " << valu_per_flow;
    o << ", \"valu_hungry\": " << mix_valu_hungry;
    o << ", \"load_hungry\": " << mix_load_hungry;
    o << ", \"flow_hungry\": " << mix_flow_hungry;
    o << ", \"balanced\": " << mix_balanced;
    o << ", \"empty\": " << mix_empty;
    o << ", \"rle\": \"" << mix_rle << "\"";
    o << "},\n";
    o << "  \"bounds\": {";
    o << "\"height\": " << shape_h << ", \"rounds\": " << shape_r << ", \"batch\": " << shape_b;
    o << ", \"item_rounds\": " << item_rounds;
    o << ", \"tiles\": " << tiles;
    o << ", \"alu_floor\": " << alu_floor;
    o << ", \"valu_floor\": " << valu_floor;
    o << ", \"load_floor\": " << load_floor;
    o << ", \"store_floor\": " << store_floor;
    o << ", \"flow_floor\": " << flow_floor;
    o << ", \"work_floor\": " << work_bound;
    o << ", \"gather_floor\": " << gather_floor;
    o << ", \"gather_floor_all_scalar\": " << gather_floor_all;
    o << ", \"fused_hash_floor\": " << fused_hash_floor;
    o << ", \"useful_op_floor\": " << useful_op_floor;
    o << ", \"peak_slots\": 23";
    o << ", \"ipc_vs_peak\": " << (ipc / 23.0);
    o << "},\n";
    o << "  \"gathers_by_depth\": {";
    {
        bool first = true;
        for (int d = 0; d < kMaxDepth; ++d) {
            if (depth_gathers[static_cast<std::size_t>(d)] == 0 &&
                depth_cycles[static_cast<std::size_t>(d)] == 0)
                continue;
            if (!first) o << ", ";
            first = false;
            o << "\"" << d << "\": {\"gathers\": " << depth_gathers[static_cast<std::size_t>(d)]
              << ", \"loads\": " << depth_loads[static_cast<std::size_t>(d)]
              << ", \"cycles\": " << depth_cycles[static_cast<std::size_t>(d)] << "}";
        }
        if (depth_unknown) {
            if (!first) o << ", ";
            o << "\"unknown\": {\"gathers\": 0, \"loads\": 0, \"cycles\": " << depth_unknown << "}";
        }
    }
    o << "},\n";
    o << "  \"alu_class\": {";
    o << "\"hash\": " << phase_alu[3];
    o << ", \"idx\": " << phase_alu[4];
    o << ", \"addr\": " << (phase_alu[2] + phase_alu[6]);
    o << ", \"init\": " << phase_alu[1];
    o << ", \"other\": " << (phase_alu[0] + phase_alu[5]);
    o << ", \"valu_hash\": " << phase_valu[3];
    o << "},\n";
    o << "  \"scratch_vectors\": {";
    o << "\"capacity_words\": " << kDefaultScratch;
    o << ", \"capacity_vecs\": " << cap_vecs;
    o << ", \"peak_live\": " << peak_live;
    o << ", \"peak_vecs\": " << peak_vecs;
    o << ", \"free_vecs\": " << std::max(0, cap_vecs - peak_vecs);
    o << ", \"cells_touched\": " << cells_touched;
    o << ", \"waw_conflicts\": " << waw_conflicts;
    o << ", \"war_same_cycle\": " << war_same_cycle;
    o << ", \"war_named_overlaps\": " << war_named_overlaps;
    o << "},\n";
    o << "  \"pipeline\": {";
    o << "\"tiles_in_flight\": " << tiles_in_flight;
    o << ", \"ii_est\": " << ii_est;
    o << ", \"item_rounds\": " << item_rounds;
    o << ", \"steady_cycles\": " << region_steady.cycles;
    o << ", \"load_to_use_mean\": " << load_to_use;
    o << ", \"load_to_use_p50\": " << load_use_p50;
    o << ", \"load_to_use_p95\": " << load_use_p95;
    o << ", \"load_to_use_n\": " << load_use_n;
    o << ", \"load_to_use_hist\": {";
    for (int i = 0; i < 7; ++i) {
        if (i) o << ", ";
        o << "\"" << kLoadUseName[i] << "\": " << load_use_hist[static_cast<std::size_t>(i)];
    }
    o << "}";
    o << ", \"shallow_gathers\": " << shallow_gathers;
    o << ", \"wavefront\": {";
    for (int i = 0; i < kNPhase; ++i) {
        if (i) o << ", ";
        o << "\"" << kPhaseName[i] << "\": " << region_steady.phase[static_cast<std::size_t>(i)];
    }
    o << "}";
    o << "},\n";
    auto emit_i64_arr = [&](const std::int64_t* v, int n) {
        o << "[";
        for (int i = 0; i < n; ++i) {
            if (i) o << ", ";
            o << v[i];
        }
        o << "]";
    };
    auto emit_u8_arr = [&](const std::vector<std::uint8_t>& v) {
        o << "[";
        for (std::size_t i = 0; i < v.size(); ++i) {
            if (i) o << ", ";
            o << static_cast<int>(v[i]);
        }
        o << "]";
    };
    auto emit_region = [&](const char* name, const RegionStat& r) {
        o << "\"" << name << "\": {";
        o << "\"cycles\": " << r.cycles;
        o << ", \"zero_load\": " << r.zero_load;
        o << ", \"load0_valu_lt6\": " << r.load0_valu_lt6;
        o << ", \"valu_unused_slots\": " << r.valu_unused;
        o << ", \"load_unused_slots\": " << r.load_unused;
        o << ", \"store_unused_slots\": " << r.store_unused;
        o << ", \"alu_unused_slots\": " << r.alu_unused;
        o << ", \"flow_unused_slots\": " << r.flow_unused;
        o << "}";
    };
    o << "  \"regions\": {";
    o << "\"startup_end\": " << startup_end;
    o << ", \"drain_start\": " << drain_start;
    o << ", ";
    emit_region("startup", region_startup);
    o << ", ";
    emit_region("steady", region_steady);
    o << ", ";
    emit_region("drain", region_drain);
    o << "},\n";
    auto emit_occ = [&](const char* name, int e, int limit, const std::int64_t* hist, int n) {
        const double mean =
            cycles > 0 ? static_cast<double>(eng_ops[static_cast<std::size_t>(e)]) /
                             static_cast<double>(cycles)
                       : 0.0;
        o << "\"" << name << "\": {\"limit\": " << limit << ", \"mean_used\": " << mean
          << ", \"full\": " << port_full[static_cast<std::size_t>(e)] << ", \"hist\": ";
        emit_i64_arr(hist, n);
        o << "}";
    };
    o << "  \"occupancy_hist\": {";
    emit_occ("alu", 0, 12, occ_alu.data(), 13);
    o << ", ";
    emit_occ("valu", 1, 6, occ_valu.data(), 7);
    o << ", ";
    emit_occ("load", 2, 2, occ_load.data(), 3);
    o << ", ";
    emit_occ("store", 3, 2, occ_store.data(), 3);
    o << ", ";
    emit_occ("flow", 4, 1, occ_flow.data(), 2);
    o << "},\n";
    o << "  \"occupancy_series\": {";
    o << "\"n\": " << series_n;
    o << ", \"stride\": " << series_stride;
    if (detail_series) {
        o << ", \"alu\": ";
        emit_u8_arr(used_series[0]);
        o << ", \"valu\": ";
        emit_u8_arr(used_series[1]);
        o << ", \"load\": ";
        emit_u8_arr(used_series[2]);
        o << ", \"store\": ";
        emit_u8_arr(used_series[3]);
        o << ", \"flow\": ";
        emit_u8_arr(used_series[4]);
    }
    o << "},\n";
    o << "  \"pressure\": {";
    o << "\"peak\": " << peak_live;
    o << ", \"p50\": " << pressure_p50;
    o << ", \"mean\": " << pressure_mean;
    o << ", \"n\": " << series_n;
    o << ", \"stride\": " << series_stride;
    o << ", \"series\": [";
    for (std::size_t i = 0; i < pressure_series.size(); ++i) {
        if (i) o << ", ";
        o << pressure_series[i];
    }
    o << "]";
    o << "},\n";
    o << "  \"live_overlaps\": [";
    for (std::size_t i = 0; i < live_overlaps.size(); ++i) {
        if (i) o << ", ";
        o << "{\"a\": \"" << json_escape(live_overlaps[i].a) << "\", \"b\": \""
          << json_escape(live_overlaps[i].b) << "\", \"cycles\": " << live_overlaps[i].cycles
          << "}";
    }
    o << "],\n";
    o << "  \"integrity\": {";
    o << "\"hash_ops_present\": " << (hash_present ? "true" : "false");
    o << ", \"index_stores\": " << (index_stores ? "true" : "false");
    o << ", \"mux_used\": " << (mux_used ? "true" : "false");
    o << ", \"hash_like_ops\": " << hash_like;
    o << ", \"suspect_skip_hash\": " << (suspect_skip_hash ? "true" : "false");
    o << ", \"suspect_cheat\": " << (suspect_cheat ? "true" : "false");
    o << "},\n";
    o << "  \"select_vs_gather\": {";
    o << "\"gather_scalar\": " << gather_scalar;
    o << ", \"vload\": " << vload_n;
    o << ", \"select\": " << select_n;
    o << ", \"vselect\": " << vselect_n;
    o << ", \"madd\": " << madd_n;
    o << ", \"levels\": [";
    o << "{\"level\": 0, \"gather\": \"1 valu + 8 load\", \"select\": \"free\", \"prefer\": \"select\"}, ";
    o << "{\"level\": 1, \"gather\": \"1 valu + 8 load\", \"select\": \"1 flow\", \"prefer\": \"select\"}, ";
    o << "{\"level\": 2, \"gather\": \"1 valu + 8 load\", \"select\": \"2 flow + 1 (flow|2 valu)\", \"prefer\": \"select\"}, ";
    o << "{\"level\": 3, \"gather\": \"1 valu + 8 load\", \"select\": \"4 flow + 3 (flow|2 valu)\", \"prefer\": \"select\"}, ";
    o << "{\"level\": 4, \"gather\": \"1 valu + 8 load\", \"select\": \"8 flow + 7 (flow|2 valu)\", \"prefer\": \"mixed\"}, ";
    o << "{\"level\": 5, \"gather\": \"1 valu + 8 load\", \"select\": \"16 flow + 15 (flow|2 valu)\", \"prefer\": \"gather\"}";
    o << "]},\n";
    o << "  \"hypotheses\": [";
    for (std::size_t i = 0; i < hyps.size(); ++i) {
        if (i) o << ", ";
        o << "{\"tag\": \"" << hyps[i].tag << "\", \"why\": \"" << json_escape(hyps[i].why) << "\"}";
    }
    o << "],\n";
    o << "  \"top_ops\": [";
    for (std::size_t i = 0; i < tops.size(); ++i) {
        if (i) o << ", ";
        o << "[\"" << tops[i].second << "\", " << tops[i].first << "]";
    }
    o << "],\n";
    o << "  \"top_slack\": [";
    for (std::size_t i = 0; i < top.size(); ++i) {
        if (i) o << ", ";
        const Rec& r = top[i];
        o << "{\"issue\": " << r.issue << ", \"ready\": " << r.ready << ", \"slack\": " << r.slack
          << ", \"op\": \"" << op_name(r.op) << "\", \"engine\": \""
          << kEngName[r.eng < 6 ? r.eng : 5] << "\", \"pred_op\": \""
          << (r.pred_issue >= 0 ? op_name(r.pred_op) : "") << "\", \"pred_issue\": " << r.pred_issue
          << "}";
    }
    o << "],\n";
    o << "  \"named_live\": [";
    for (std::size_t i = 0; i < named.size(); ++i) {
        if (i) o << ", ";
        const NamedLive& n = named[i];
        o << "{\"name\": \"" << json_escape(n.name) << "\", \"addr\": " << n.addr
          << ", \"len\": " << n.length << ", \"first\": " << n.first << ", \"last\": " << n.last
          << ", \"span\": " << (n.last - n.first + 1) << ", \"writes\": " << n.writes
          << ", \"cells\": " << n.cells << ", \"loop_carried\": " << (n.loop_carried ? "true" : "false")
          << "}";
    }
    o << "],\n";
    o << "  \"hints\": [";
    for (std::size_t i = 0; i < hints.size(); ++i) {
        if (i) o << ", ";
        o << "\"" << json_escape(hints[i]) << "\"";
    }
    o << "]";
    if (have_prev) {
        const bool cause_changed = !prev_cause.empty() && prev_cause != idle_cause;
        const bool bn_moved = !prev_bn.empty() && prev_bn != bottleneck;
        const bool floor_moved = !prev_floor.empty() && prev_floor != kEngName[floor_e];
        o << ",\n  \"diff\": {\n";
        o << "    \"same_program\": " << (prev_fp == fp ? "true" : "false") << ",\n";
        o << "    \"cycles_est\": " << (prev_cycles >= 0 ? cycles - prev_cycles : 0) << ",\n";
        o << "    \"critical_path\": " << (prev_cp >= 0 ? max_cp - prev_cp : 0) << ",\n";
        o << "    \"cp_raw\": " << (prev_raw >= 0 ? max_cp_raw - prev_raw : 0) << ",\n";
        o << "    \"cp_waw\": " << (prev_waw >= 0 ? max_cp_waw - prev_waw : 0) << ",\n";
        o << "    \"cp_mem\": " << (prev_mem >= 0 ? max_cp_mem - prev_mem : 0) << ",\n";
        o << "    \"alu_ops\": " << (prev_ops[0] >= 0 ? eng_ops[0] - prev_ops[0] : 0) << ",\n";
        o << "    \"valu_ops\": " << (prev_ops[1] >= 0 ? eng_ops[1] - prev_ops[1] : 0) << ",\n";
        o << "    \"load_ops\": " << (prev_ops[2] >= 0 ? eng_ops[2] - prev_ops[2] : 0) << ",\n";
        o << "    \"store_ops\": " << (prev_ops[3] >= 0 ? eng_ops[3] - prev_ops[3] : 0) << ",\n";
        o << "    \"flow_ops\": " << (prev_ops[4] >= 0 ? eng_ops[4] - prev_ops[4] : 0) << ",\n";
        o << "    \"work_bound\": " << (prev_wb >= 0 ? work_bound - prev_wb : 0) << ",\n";
        o << "    \"overhead\": " << (prev_oh >= 0 ? overhead - prev_oh : 0) << ",\n";
        o << "    \"gather_scalar\": " << (prev_gather >= 0 ? gather_scalar - prev_gather : 0) << ",\n";
        o << "    \"vselect_ops\": " << (prev_vsel >= 0 ? vselect_n - prev_vsel : 0) << ",\n";
        o << "    \"peak_live\": " << (prev_peak >= 0 ? peak_live - prev_peak : 0) << ",\n";
        o << "    \"ipc\": " << (prev_ipc >= 0 ? ipc - prev_ipc : 0) << ",\n";
        o << "    \"schedule_waste\": " << (prev_waste >= 0 ? sched_waste - prev_waste : 0) << ",\n";
        o << "    \"idle_cause_changed\": " << (cause_changed ? "true" : "false") << ",\n";
        o << "    \"floor_engine_changed\": " << (floor_moved ? "true" : "false") << ",\n";
        o << "    \"bottleneck_moved\": " << (bn_moved || cause_changed || floor_moved ? "true" : "false")
          << "\n";
        o << "  }";
    }
    o << "\n}\n";
    return o.str();
}

}  // namespace vliw
