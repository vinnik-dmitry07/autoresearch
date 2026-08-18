#include "c_api.h"

#include "machine.hpp"
#include "profiler.hpp"

#include <cstdlib>
#include <cstring>
#include <string>
#include <utility>

namespace {

thread_local std::string g_error;

void set_error(const char* msg) { g_error = msg ? msg : "unknown error"; }

}  // namespace

struct VliwProgram {
    vliw::Program impl;
};

struct VliwMachine {
    vliw::Machine impl;
    explicit VliwMachine(vliw::Machine m) : impl(std::move(m)) {}
};

extern "C" {

VliwProgram* vliw_program_create(void) {
    try {
        return new VliwProgram();
    } catch (const std::exception& e) {
        set_error(e.what());
        return nullptr;
    }
}

void vliw_program_destroy(VliwProgram* p) { delete p; }

int vliw_program_add_bundle(VliwProgram* p, const VliwSlotDesc* slots, int n) {
    if (!p || (n > 0 && !slots)) {
        set_error("null program/slots");
        return 1;
    }
    try {
        p->impl.begin_bundle();
        for (int i = 0; i < n; ++i) {
            const VliwSlotDesc& s = slots[i];
            p->impl.add(static_cast<vliw::Engine>(s.engine), s.op, s.dest, s.a, s.b, s.c);
        }
        p->impl.end_bundle();
        return 0;
    } catch (const std::exception& e) {
        set_error(e.what());
        return 1;
    }
}

int vliw_program_load(VliwProgram* p, const VliwSlotDesc* slots, int n_slots, const uint32_t* begins,
                      const uint16_t* counts, int n_bundles) {
    if (!p || (n_bundles > 0 && (!begins || !counts)) || (n_slots > 0 && !slots)) {
        set_error("null program/slots");
        return 1;
    }
    try {
        p->impl.reserve(static_cast<std::size_t>(n_bundles), static_cast<std::size_t>(n_slots));
        for (int i = 0; i < n_bundles; ++i) {
            const int begin = static_cast<int>(begins[i]);
            const int n = static_cast<int>(counts[i]);
            if (begin < 0 || n < 0 || begin + n > n_slots) {
                set_error("bundle range oob");
                return 1;
            }
            p->impl.begin_bundle();
            for (int j = 0; j < n; ++j) {
                const VliwSlotDesc& s = slots[begin + j];
                p->impl.add(static_cast<vliw::Engine>(s.engine), s.op, s.dest, s.a, s.b, s.c);
            }
            p->impl.end_bundle();
        }
        return 0;
    } catch (const std::exception& e) {
        set_error(e.what());
        return 1;
    }
}

int vliw_program_load_oneslot(VliwProgram* p, const VliwSlotDesc* slots, int n) {
    if (!p || (n > 0 && !slots)) {
        set_error("null program/slots");
        return 1;
    }
    try {
        p->impl.load_oneslot(slots, n);
        return 0;
    } catch (const std::exception& e) {
        set_error(e.what());
        return 1;
    }
}

int vliw_program_debug_key_count(const VliwProgram* p) {
    return p ? p->impl.debug_key_count : 0;
}

char* vliw_program_profile(const VliwProgram* p, const char* prev_json) {
    return vliw_program_profile_ex(p, prev_json, nullptr);
}

char* vliw_program_profile_ex(const VliwProgram* p, const char* prev_json,
                              const VliwProfileExtra* extra) {
    if (!p) {
        set_error("null program");
        return nullptr;
    }
    try {
        vliw::ProfileExtra ex;
        const vliw::ProfileExtra* px = nullptr;
        if (extra) {
            ex.scratch_addr = extra->scratch_addr;
            ex.scratch_len = extra->scratch_len;
            ex.scratch_names = extra->scratch_names;
            ex.n_scratch = extra->n_scratch;
            ex.phase = extra->phase;
            ex.n_phase = extra->n_phase;
            ex.depth = extra->depth;
            ex.n_depth = extra->n_depth;
            ex.forest_height = extra->forest_height;
            ex.rounds = extra->rounds;
            ex.batch_size = extra->batch_size;
            px = &ex;
        }
        const std::string json = vliw::profile_json(p->impl, prev_json, px);
        char* out = static_cast<char*>(std::malloc(json.size() + 1));
        if (!out) {
            set_error("out of memory");
            return nullptr;
        }
        std::memcpy(out, json.c_str(), json.size() + 1);
        return out;
    } catch (const std::exception& e) {
        set_error(e.what());
        return nullptr;
    }
}

void vliw_profile_free(char* json) { std::free(json); }

VliwMachine* vliw_machine_create(const uint32_t* mem, size_t mem_len, size_t n_cores,
                                 size_t scratch_size, const VliwProgram* program) {
    try {
        const std::span<const std::uint32_t> view(mem, mem_len);
        vliw::Program prog = program ? program->impl : vliw::Program{};
        return new VliwMachine(vliw::Machine(view, std::move(prog), static_cast<int>(n_cores),
                                             static_cast<int>(scratch_size)));
    } catch (const std::exception& e) {
        set_error(e.what());
        return nullptr;
    }
}

void vliw_machine_destroy(VliwMachine* m) { delete m; }

int vliw_machine_set_program(VliwMachine* m, const VliwProgram* p) {
    if (!m || !p) {
        set_error("null machine/program");
        return 1;
    }
    try {
        // Rebuild machine with the same memory/cores/scratch, new program.
        std::vector<std::uint32_t> mem(m->impl.mem().begin(), m->impl.mem().end());
        const int n_cores = static_cast<int>(m->impl.cores().size());
        const int scratch = m->impl.scratch_size();
        const bool pause = true;
        const bool debug = true;
        vliw::Program prog = p->impl;
        vliw::Machine next(mem, std::move(prog), n_cores, scratch);
        next.set_enable_pause(pause);
        next.set_enable_debug(debug);
        m->impl = std::move(next);
        return 0;
    } catch (const std::exception& e) {
        set_error(e.what());
        return 1;
    }
}

void vliw_machine_set_flags(VliwMachine* m, int enable_pause, int enable_debug) {
    if (!m) return;
    m->impl.set_enable_pause(enable_pause != 0);
    m->impl.set_enable_debug(enable_debug != 0);
}

int vliw_machine_set_debug_expected(VliwMachine* m, const uint32_t* vals, const uint8_t* present,
                                    size_t n) {
    if (!m) {
        set_error("null machine");
        return 1;
    }
    try {
        m->impl.set_debug_expected(std::span<const std::uint32_t>(vals, n),
                                   std::span<const std::uint8_t>(present, n));
        return 0;
    } catch (const std::exception& e) {
        set_error(e.what());
        return 1;
    }
}

int vliw_machine_run(VliwMachine* m) {
    if (!m) {
        set_error("null machine");
        return 1;
    }
    try {
        m->impl.run();
        return 0;
    } catch (const std::exception& e) {
        set_error(e.what());
        return 1;
    }
}

uint64_t vliw_machine_cycle(const VliwMachine* m) { return m ? m->impl.cycle() : 0; }

size_t vliw_machine_mem_len(const VliwMachine* m) { return m ? m->impl.mem().size() : 0; }

const uint32_t* vliw_machine_mem(const VliwMachine* m) { return m ? m->impl.mem().data() : nullptr; }

uint32_t* vliw_machine_mem_mut(VliwMachine* m) { return m ? m->impl.mem_mut().data() : nullptr; }

int vliw_machine_pc(const VliwMachine* m, int core) {
    if (!m || core < 0 || static_cast<std::size_t>(core) >= m->impl.cores().size()) return -1;
    return m->impl.cores()[static_cast<std::size_t>(core)].pc;
}

int vliw_machine_state(const VliwMachine* m, int core) {
    if (!m || core < 0 || static_cast<std::size_t>(core) >= m->impl.cores().size()) return 0;
    return static_cast<int>(m->impl.cores()[static_cast<std::size_t>(core)].state);
}

const uint32_t* vliw_machine_scratch(const VliwMachine* m, int core, size_t* len) {
    if (!m || core < 0 || static_cast<std::size_t>(core) >= m->impl.cores().size()) {
        if (len) *len = 0;
        return nullptr;
    }
    const auto& c = m->impl.cores()[static_cast<std::size_t>(core)];
    if (len) *len = static_cast<size_t>(m->impl.scratch_size());
    return c.scratch;
}

const uint32_t* vliw_machine_trace_buf(const VliwMachine* m, int core, size_t* len) {
    if (!m || core < 0 || static_cast<std::size_t>(core) >= m->impl.cores().size()) {
        if (len) *len = 0;
        return nullptr;
    }
    const auto& buf = m->impl.cores()[static_cast<std::size_t>(core)].trace_buf;
    if (len) *len = buf.size();
    return buf.data();
}

const char* vliw_last_error(void) { return g_error.c_str(); }

}  // extern "C"
