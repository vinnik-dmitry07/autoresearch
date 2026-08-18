#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#ifdef _WIN32
#ifdef VLIW_EXPORTS
#define VLIW_API __declspec(dllexport)
#else
#define VLIW_API __declspec(dllimport)
#endif
#else
#define VLIW_API
#endif

typedef struct VliwProgram VliwProgram;
typedef struct VliwMachine VliwMachine;

typedef struct VliwSlotDesc {
    uint8_t engine;
    uint8_t op;
    uint8_t pad[2];
    uint32_t dest;
    uint32_t a;
    uint32_t b;
    uint32_t c;
} VliwSlotDesc;

VLIW_API VliwProgram* vliw_program_create(void);
VLIW_API void vliw_program_destroy(VliwProgram* p);
VLIW_API int vliw_program_add_bundle(VliwProgram* p, const VliwSlotDesc* slots, int n);
VLIW_API int vliw_program_load(VliwProgram* p, const VliwSlotDesc* slots, int n_slots,
                               const uint32_t* begins, const uint16_t* counts, int n_bundles);
VLIW_API int vliw_program_load_oneslot(VliwProgram* p, const VliwSlotDesc* slots, int n);
VLIW_API int vliw_program_debug_key_count(const VliwProgram* p);
typedef struct VliwProfileExtra {
    const uint32_t* scratch_addr;
    const uint16_t* scratch_len;
    const char* const* scratch_names;
    int n_scratch;
    const uint8_t* phase;
    int n_phase;
    const uint8_t* depth;
    int n_depth;
    int forest_height;
    int rounds;
    int batch_size;
} VliwProfileExtra;

// malloc'd JSON; free with vliw_profile_free. prev_json and extra may be null.
VLIW_API char* vliw_program_profile(const VliwProgram* p, const char* prev_json);
VLIW_API char* vliw_program_profile_ex(const VliwProgram* p, const char* prev_json,
                                       const VliwProfileExtra* extra);
VLIW_API void vliw_profile_free(char* json);

VLIW_API VliwMachine* vliw_machine_create(const uint32_t* mem, size_t mem_len, size_t n_cores,
                                          size_t scratch_size, const VliwProgram* program);
VLIW_API void vliw_machine_destroy(VliwMachine* m);
VLIW_API int vliw_machine_set_program(VliwMachine* m, const VliwProgram* p);
VLIW_API void vliw_machine_set_flags(VliwMachine* m, int enable_pause, int enable_debug);
VLIW_API int vliw_machine_set_debug_expected(VliwMachine* m, const uint32_t* vals,
                                             const uint8_t* present, size_t n);
VLIW_API int vliw_machine_run(VliwMachine* m);
VLIW_API uint64_t vliw_machine_cycle(const VliwMachine* m);
VLIW_API size_t vliw_machine_mem_len(const VliwMachine* m);
VLIW_API const uint32_t* vliw_machine_mem(const VliwMachine* m);
VLIW_API uint32_t* vliw_machine_mem_mut(VliwMachine* m);
VLIW_API int vliw_machine_pc(const VliwMachine* m, int core);
VLIW_API int vliw_machine_state(const VliwMachine* m, int core);
VLIW_API const uint32_t* vliw_machine_scratch(const VliwMachine* m, int core, size_t* len);
VLIW_API const uint32_t* vliw_machine_trace_buf(const VliwMachine* m, int core, size_t* len);
VLIW_API const char* vliw_last_error(void);

#ifdef __cplusplus
}
#endif
