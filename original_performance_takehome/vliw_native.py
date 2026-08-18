from __future__ import annotations

from pathlib import Path
import ctypes
import struct
import sys
from typing import Any

_SLOT_STRUCT = struct.Struct('<BB2xIIII')

ROOT = Path(__file__).resolve().parent
_LIB = None


def _lib_path() -> Path:
    name = 'vliw_machine.dll' if sys.platform == 'win32' else 'libvliw_machine.so'
    return ROOT / 'build' / name


def cpp_available() -> bool:
    return _lib_path().is_file()


def _lib():
    global _LIB
    if _LIB is not None:
        return _LIB
    path = _lib_path()
    if not path.is_file():
        raise OSError(f'vliw native library not found: {path}')
    lib = ctypes.CDLL(str(path))
    lib.vliw_program_create.restype = ctypes.c_void_p
    lib.vliw_program_destroy.argtypes = [ctypes.c_void_p]
    lib.vliw_program_add_bundle.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    lib.vliw_program_add_bundle.restype = ctypes.c_int
    lib.vliw_program_load.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    lib.vliw_program_load.restype = ctypes.c_int
    lib.vliw_program_load_oneslot.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    lib.vliw_program_load_oneslot.restype = ctypes.c_int
    lib.vliw_program_debug_key_count.argtypes = [ctypes.c_void_p]
    lib.vliw_program_debug_key_count.restype = ctypes.c_int
    lib.vliw_program_profile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.vliw_program_profile.restype = ctypes.c_void_p
    lib.vliw_program_profile_ex.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_void_p,
    ]
    lib.vliw_program_profile_ex.restype = ctypes.c_void_p
    lib.vliw_profile_free.argtypes = [ctypes.c_void_p]
    lib.vliw_machine_create.argtypes = [
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_void_p,
    ]
    lib.vliw_machine_create.restype = ctypes.c_void_p
    lib.vliw_machine_destroy.argtypes = [ctypes.c_void_p]
    lib.vliw_machine_set_flags.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.vliw_machine_set_debug_expected.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    lib.vliw_machine_set_debug_expected.restype = ctypes.c_int
    lib.vliw_machine_run.argtypes = [ctypes.c_void_p]
    lib.vliw_machine_run.restype = ctypes.c_int
    lib.vliw_machine_cycle.argtypes = [ctypes.c_void_p]
    lib.vliw_machine_cycle.restype = ctypes.c_uint64
    lib.vliw_machine_mem_len.argtypes = [ctypes.c_void_p]
    lib.vliw_machine_mem_len.restype = ctypes.c_size_t
    lib.vliw_machine_mem.argtypes = [ctypes.c_void_p]
    lib.vliw_machine_mem.restype = ctypes.c_void_p
    lib.vliw_machine_mem_mut.argtypes = [ctypes.c_void_p]
    lib.vliw_machine_mem_mut.restype = ctypes.c_void_p
    lib.vliw_machine_pc.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.vliw_machine_pc.restype = ctypes.c_int
    lib.vliw_machine_state.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.vliw_machine_state.restype = ctypes.c_int
    lib.vliw_machine_scratch.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
    lib.vliw_machine_scratch.restype = ctypes.c_void_p
    lib.vliw_last_error.restype = ctypes.c_char_p
    _LIB = lib
    return lib


class VliwSlotDesc(ctypes.Structure):
    _fields_ = [
        ('engine', ctypes.c_uint8),
        ('op', ctypes.c_uint8),
        ('pad', ctypes.c_uint8 * 2),
        ('dest', ctypes.c_uint32),
        ('a', ctypes.c_uint32),
        ('b', ctypes.c_uint32),
        ('c', ctypes.c_uint32),
    ]


class VliwProfileExtra(ctypes.Structure):
    _fields_ = [
        ('scratch_addr', ctypes.POINTER(ctypes.c_uint32)),
        ('scratch_len', ctypes.POINTER(ctypes.c_uint16)),
        ('scratch_names', ctypes.POINTER(ctypes.c_char_p)),
        ('n_scratch', ctypes.c_int),
        ('phase', ctypes.POINTER(ctypes.c_uint8)),
        ('n_phase', ctypes.c_int),
        ('depth', ctypes.POINTER(ctypes.c_uint8)),
        ('n_depth', ctypes.c_int),
        ('forest_height', ctypes.c_int),
        ('rounds', ctypes.c_int),
        ('batch_size', ctypes.c_int),
    ]


PHASE_ID = {
    'unknown': 0,
    'init': 1,
    'ldst': 2,
    'hash': 3,
    'walk': 4,
    'store': 5,
    'gather': 6,
}


ENGINE_ID = {'alu': 0, 'valu': 1, 'load': 2, 'store': 3, 'flow': 4, 'debug': 5}
ALU_OPS = {
    '+': 0,
    '-': 1,
    '*': 2,
    '//': 3,
    'cdiv': 4,
    '^': 5,
    '&': 6,
    '|': 7,
    '<<': 8,
    '>>': 9,
    '%': 10,
    '<': 11,
    '==': 12,
}
FLOW_OPS = {
    'select': 0,
    'add_imm': 1,
    'vselect': 2,
    'halt': 3,
    'pause': 4,
    'trace_write': 5,
    'cond_jump': 6,
    'cond_jump_rel': 7,
    'jump': 8,
    'jump_indirect': 9,
    'coreid': 10,
}


def _u32(val: int) -> int:
    return int(val) % (2**32)


_ENCODE_CACHE_MIN = 256
_ENCODE_CACHE: dict[tuple, 'EncodedProgram'] = {}


class EncodedProgram:
    __slots__ = (
        'buf',
        'n_slots',
        'keys',
        'oneslot',
        'begins',
        'counts',
        'n_bundles',
        'native',
        'phase_c',
        'phase_n',
        'depth_c',
        'depth_n',
        'shape',
        'scratch_id',
        'scratch_keep',
    )

    def __init__(
        self,
        buf: bytearray,
        n_slots: int,
        keys: list,
        oneslot: bool,
        begins: list[int] | None = None,
        counts: list[int] | None = None,
        n_bundles: int = 0,
    ):
        self.buf = buf
        self.n_slots = n_slots
        self.keys = keys
        self.oneslot = oneslot
        self.begins = begins
        self.counts = counts
        self.n_bundles = n_bundles
        self.native = None
        self.phase_c = None
        self.phase_n = 0
        self.depth_c = None
        self.depth_n = 0
        self.shape = None
        self.scratch_id = None
        self.scratch_keep = None

    def load_into(self, prog) -> None:
        lib = _lib()
        if self.oneslot:
            raw = (ctypes.c_char * len(self.buf)).from_buffer(self.buf) if self.n_slots else None
            if lib.vliw_program_load_oneslot(prog, raw, self.n_slots) != 0:
                raise RuntimeError(_err())
            return
        n_slots = self.n_slots
        n_bundles = self.n_bundles
        arr = (VliwSlotDesc * max(n_slots, 1))()
        if n_slots:
            ctypes.memmove(arr, bytes(self.buf), len(self.buf))
        begins = (ctypes.c_uint32 * max(n_bundles, 1))(*(self.begins or []))
        counts = (ctypes.c_uint16 * max(n_bundles, 1))(*(self.counts or []))
        if lib.vliw_program_load(
            prog, arr if n_slots else None, n_slots, begins, counts, n_bundles
        ) != 0:
            raise RuntimeError(_err())

    def ensure_native(self):
        if self.native:
            return self.native
        lib = _lib()
        prog = lib.vliw_program_create()
        if not prog:
            raise RuntimeError(_err())
        try:
            self.load_into(prog)
        except Exception:
            lib.vliw_program_destroy(prog)
            raise
        self.native = prog
        return prog

    def __del__(self):
        native = getattr(self, 'native', None)
        if not native:
            return
        self.native = None
        lib = _LIB
        if lib is None:
            return
        try:
            lib.vliw_program_destroy(native)
        except Exception:
            pass


def encode_kernel_rows(
    engines: list,
    slots: list,
    skip_debug: bool = False,
    n: int | None = None,
    start: int = 0,
) -> EncodedProgram:
    """Pack compact KernelBuilder rows. Hot path is alu/load/store/flow oneslot."""
    if n is None:
        n = len(engines) - start
    slot_size = _SLOT_STRUCT.size
    buf = bytearray(n * slot_size)
    pack = _SLOT_STRUCT.pack_into
    alu = ALU_OPS
    keys: list = []
    out = 0
    mask = 0xFFFFFFFF
    end = start + n
    for i in range(start, end):
        name = engines[i]
        if skip_debug and name == 'debug':
            continue
        slot = slots[i]
        op = slot[0]
        off = out * slot_size
        if name == 'alu':
            pack(buf, off, 0, alu[op], slot[1], slot[2], slot[3], 0)
        elif name == 'load':
            if op == 'load':
                pack(buf, off, 2, 0, slot[1], slot[2], 0, 0)
            elif op == 'const':
                pack(buf, off, 2, 3, slot[1], slot[2] & mask, 0, 0)
            else:
                e, o, d, a, b, c = encode_slot(name, slot, keys)
                pack(buf, off, e, o, d, a, b, c)
        elif name == 'store':
            pack(buf, off, 3, 0 if op == 'store' else 1, slot[1], slot[2], 0, 0)
        elif name == 'flow':
            if op == 'select':
                pack(buf, off, 4, 0, slot[1], slot[2], slot[3], slot[4])
            elif op == 'pause':
                pack(buf, off, 4, 4, 0, 0, 0, 0)
            else:
                e, o, d, a, b, c = encode_slot(name, slot, keys)
                pack(buf, off, e, o, d, a, b, c)
        else:
            e, o, d, a, b, c = encode_slot(name, slot, keys)
            pack(buf, off, e, o, d, a, b, c)
        out += 1
    if out != n:
        buf = buf[: out * slot_size]
    return EncodedProgram(buf, out, keys, True, n_bundles=out)


def repeat_encoded_body(
    head: EncodedProgram,
    prefix_n: int,
    body_n: int,
    rounds: int,
    tail: EncodedProgram | None = None,
) -> EncodedProgram:
    """Copy [prefix][body] into [prefix][body]*rounds[tail]."""
    sz = _SLOT_STRUCT.size
    src = head.buf
    prefix = src[: prefix_n * sz]
    chunk = bytes(src[prefix_n * sz : (prefix_n + body_n) * sz])
    out = bytearray(prefix)
    if rounds == 1:
        out.extend(chunk)
    elif rounds > 1:
        out.extend(chunk * rounds)
    if tail is not None and tail.n_slots:
        out.extend(tail.buf)
    n_slots = prefix_n + body_n * rounds + (tail.n_slots if tail is not None else 0)
    keys = head.keys
    if tail is not None and tail.keys:
        keys = list(head.keys) + list(tail.keys)
    return EncodedProgram(out, n_slots, keys, True, n_bundles=n_slots)


def stamp_encoded_iters(
    prefix: EncodedProgram,
    tmpl: EncodedProgram,
    i_consts: list[int],
    patch_offs: tuple[int, ...],
    rounds: int,
    tail: EncodedProgram | None = None,
) -> EncodedProgram:
    """Repeat a oneslot iter, patching i_const u32s, then memcpy whole rounds."""
    sz = _SLOT_STRUCT.size
    step = tmpl.n_slots * sz
    blob = bytes(tmpl.buf)
    n_iter = len(i_consts)
    one = bytearray(step * n_iter)
    mv = memoryview(one)
    src = memoryview(blob)
    pack_ic = int.to_bytes
    po0, po1, po2, po3 = patch_offs
    for i, ic in enumerate(i_consts):
        off = i * step
        mv[off : off + step] = src
        raw = pack_ic(ic, 4, 'little')
        mv[off + po0 : off + po0 + 4] = raw
        mv[off + po1 : off + po1 + 4] = raw
        mv[off + po2 : off + po2 + 4] = raw
        mv[off + po3 : off + po3 + 4] = raw
    chunk = bytes(one)
    out = bytearray(prefix.buf)
    if rounds == 1:
        out.extend(chunk)
    elif rounds > 1:
        out.extend(chunk * rounds)
    if tail is not None and tail.n_slots:
        out.extend(tail.buf)
    n_slots = (
        prefix.n_slots
        + tmpl.n_slots * len(i_consts) * rounds
        + (tail.n_slots if tail is not None else 0)
    )
    return EncodedProgram(out, n_slots, prefix.keys, True, n_bundles=n_slots)


def encode_program(program, skip_debug: bool = False) -> EncodedProgram:
    """Pack a program. KernelBuilder rows skip the dict walk."""
    kb = getattr(program, '_kb', None)
    if kb is None:
        ensure = getattr(program, 'ensure_encoded', None)
        if ensure is not None:
            return ensure(skip_debug)
    else:
        return kb.ensure_encoded(skip_debug)
    key = (id(program), len(program), skip_debug)
    if len(program) >= _ENCODE_CACHE_MIN:
        hit = _ENCODE_CACHE.get(key)
        if hit is not None:
            return hit
    keys: list = []
    n = len(program)
    slot_size = _SLOT_STRUCT.size
    buf = bytearray(n * slot_size)
    pack = _SLOT_STRUCT.pack_into
    out_i = 0
    oneslot = True
    for instr in program:
        if len(instr) != 1:
            oneslot = False
            break
        name, slots = next(iter(instr.items()))
        if len(slots) != 1:
            oneslot = False
            break
        if skip_debug and name == 'debug':
            continue
        engine, op, dest, a, b, c = encode_slot(name, slots[0], keys)
        pack(buf, out_i * slot_size, engine, op, dest, a, b, c)
        out_i += 1
    if not oneslot:
        packed = _encode_multi(program, skip_debug)
    else:
        if out_i != n:
            buf = buf[: out_i * slot_size]
        packed = EncodedProgram(buf, out_i, keys, True, n_bundles=out_i)
    if n >= _ENCODE_CACHE_MIN:
        _ENCODE_CACHE[key] = packed
    return packed


def _encode_multi(program: list, skip_debug: bool) -> EncodedProgram:
    keys: list = []
    rows = []
    begins = []
    counts = []
    for instr in program:
        begin = len(rows)
        for name, slots in instr.items():
            if skip_debug and name == 'debug':
                continue
            for slot in slots:
                rows.append(encode_slot(name, slot, keys))
        begins.append(begin)
        counts.append(len(rows) - begin)
    slot_size = _SLOT_STRUCT.size
    buf = bytearray(len(rows) * slot_size)
    pack = _SLOT_STRUCT.pack_into
    for i, (engine, op, dest, a, b, c) in enumerate(rows):
        pack(buf, i * slot_size, engine, op, dest, a, b, c)
    return EncodedProgram(buf, len(rows), keys, False, begins, counts, len(program))


def _as_phase(raw) -> int:
    if raw.__class__ is str:
        return PHASE_ID.get(raw, 0)
    return int(raw)


def _phase_ids(
    program,
    phases,
    omit_debug: bool,
    n_billed: int | None = None,
) -> list[int] | None:
    if not phases:
        return None
    if isinstance(phases, (bytes, bytearray, memoryview)):
        return list(phases)
    n_prog = len(program)
    if omit_debug and n_billed is not None and n_billed == n_prog:
        n = n_billed if n_billed <= len(phases) else len(phases)
        out = [0] * n_billed
        for i in range(n):
            out[i] = _as_phase(phases[i])
        return out
    out: list[int] = []
    out_append = out.append
    for i, instr in enumerate(program):
        if omit_debug:
            key = next(iter(instr), None) if instr else None
            if key == 'debug' and len(instr) == 1:
                continue
        raw = phases[i] if i < len(phases) else 0
        out_append(_as_phase(raw))
    return out


def _phase_ctypes(
    encoded: EncodedProgram,
    program,
    phases,
    omit_debug: bool,
):
    if encoded.phase_c is not None:
        return encoded.phase_c, encoded.phase_n
    kb = getattr(program, '_kb', None)
    if kb is not None and (phases is None or phases is kb.phases):
        raw = kb.billed_phases() if omit_debug else kb.phases
        arr = (ctypes.c_uint8 * len(raw)).from_buffer_copy(raw)
        encoded.phase_c = arr
        encoded.phase_n = len(raw)
        return arr, encoded.phase_n
    if not phases:
        return None, 0
    if isinstance(phases, (bytes, bytearray)):
        arr = (ctypes.c_uint8 * len(phases)).from_buffer_copy(phases)
        encoded.phase_c = arr
        encoded.phase_n = len(phases)
        return arr, encoded.phase_n
    n_billed = encoded.n_bundles or encoded.n_slots
    ids = _phase_ids(program, phases, omit_debug, n_billed=n_billed)
    if not ids:
        return None, 0
    arr = (ctypes.c_uint8 * len(ids))(*ids)
    encoded.phase_c = arr
    encoded.phase_n = len(ids)
    return arr, encoded.phase_n


def _scratch_extra(encoded: EncodedProgram, scratch_debug: dict | None):
    if not scratch_debug:
        return None
    sid = id(scratch_debug)
    if encoded.scratch_id == sid and encoded.scratch_keep is not None:
        return encoded.scratch_keep
    addrs: list[int] = []
    lens: list[int] = []
    names: list[bytes] = []
    for addr, meta in scratch_debug.items():
        name, length = meta
        addrs.append(int(addr))
        lens.append(int(length))
        names.append(str(name).encode('utf-8'))
    n = len(addrs)
    addr_arr = (ctypes.c_uint32 * n)(*addrs)
    len_arr = (ctypes.c_uint16 * n)(*lens)
    name_arr = (ctypes.c_char_p * n)(*names)
    pack = (addr_arr, len_arr, name_arr, names, n)
    encoded.scratch_id = sid
    encoded.scratch_keep = pack
    return pack


def profile_program(
    program: list,
    omit_debug: bool = True,
    prev_json: str | None = None,
    phases: list | None = None,
    scratch_debug: dict | None = None,
    depths=None,
    forest_height: int = 0,
    rounds: int = 0,
    batch_size: int = 0,
) -> dict:
    """C++ scheduler-aware profile. No Machine.run()."""
    import json

    encoded = encode_program(program, skip_debug=omit_debug)
    lib = _lib()
    prog = encoded.ensure_native()
    prev = prev_json.encode('utf-8') if prev_json else None
    extra = VliwProfileExtra()
    keep: list[Any] = [extra]
    ph, n_ph = _phase_ctypes(encoded, program, phases, omit_debug)
    if ph is not None and n_ph:
        extra.phase = ph
        extra.n_phase = n_ph
        keep.append(ph)
    kb = getattr(program, '_kb', None)
    if kb is None:
        kb = program if hasattr(program, 'billed_depths') else None
    if encoded.depth_c is not None and encoded.depth_n:
        extra.depth = encoded.depth_c
        extra.n_depth = encoded.depth_n
        keep.append(encoded.depth_c)
    elif depths is not None:
        raw_d = bytes(depths) if not isinstance(depths, (bytes, bytearray)) else depths
        arr_d = (ctypes.c_uint8 * len(raw_d)).from_buffer_copy(raw_d)
        extra.depth = arr_d
        extra.n_depth = len(raw_d)
        keep.append(arr_d)
    elif kb is not None:
        raw_d = kb.billed_depths() if omit_debug else kb.depths
        if raw_d:
            arr_d = (ctypes.c_uint8 * len(raw_d)).from_buffer_copy(raw_d)
            extra.depth = arr_d
            extra.n_depth = len(raw_d)
            keep.append(arr_d)
    shape = encoded.shape or (getattr(kb, '_shape', None) if kb is not None else None)
    if shape:
        extra.forest_height = int(forest_height or shape[0])
        extra.rounds = int(rounds or shape[1])
        extra.batch_size = int(batch_size or shape[2])
    else:
        extra.forest_height = int(forest_height)
        extra.rounds = int(rounds)
        extra.batch_size = int(batch_size)
    scratch = _scratch_extra(encoded, scratch_debug)
    if scratch is not None:
        addr_arr, len_arr, name_arr, names, n = scratch
        extra.scratch_addr = addr_arr
        extra.scratch_len = len_arr
        extra.scratch_names = name_arr
        extra.n_scratch = n
        keep.extend([addr_arr, len_arr, name_arr, names])
    raw = lib.vliw_program_profile_ex(prog, prev, ctypes.byref(extra))
    try:
        if not raw:
            raise RuntimeError(_err())
        text = ctypes.cast(raw, ctypes.c_char_p).value
        if not text:
            raise RuntimeError('empty profile json')
        return json.loads(text.decode('utf-8'))
    finally:
        if raw:
            lib.vliw_profile_free(raw)


def encode_slot(engine: str, slot: tuple, debug_keys: list) -> tuple[int, int, int, int, int, int]:
    e = ENGINE_ID[engine]
    op = slot[0]
    if engine == 'alu':
        return e, ALU_OPS[op], slot[1], slot[2], slot[3], 0
    if engine == 'valu':
        if op == 'vbroadcast':
            return e, 13, slot[1], slot[2], 0, 0
        if op == 'multiply_add':
            return e, 14, slot[1], slot[2], slot[3], slot[4]
        return e, ALU_OPS[op], slot[1], slot[2], slot[3], 0
    if engine == 'load':
        if op == 'load':
            return e, 0, slot[1], slot[2], 0, 0
        if op == 'load_offset':
            return e, 1, slot[1], slot[2], slot[3], 0
        if op == 'vload':
            return e, 2, slot[1], slot[2], 0, 0
        if op == 'const':
            return e, 3, slot[1], _u32(slot[2]), 0, 0
    if engine == 'store':
        if op == 'store':
            return e, 0, slot[1], slot[2], 0, 0
        if op == 'vstore':
            return e, 1, slot[1], slot[2], 0, 0
    if engine == 'flow':
        code = FLOW_OPS[op]
        if op == 'select':
            return e, code, slot[1], slot[2], slot[3], slot[4]
        if op == 'add_imm':
            return e, code, slot[1], slot[2], _u32(slot[3]), 0
        if op == 'vselect':
            return e, code, slot[1], slot[2], slot[3], slot[4]
        if op in ('halt', 'pause'):
            return e, code, 0, 0, 0, 0
        if op == 'trace_write':
            return e, code, 0, slot[1], 0, 0
        if op == 'cond_jump':
            return e, code, 0, slot[1], slot[2], 0
        if op == 'cond_jump_rel':
            return e, code, 0, slot[1], _u32(slot[2]), 0
        if op == 'jump':
            return e, code, 0, slot[1], 0, 0
        if op == 'jump_indirect':
            return e, code, 0, slot[1], 0, 0
        if op == 'coreid':
            return e, code, slot[1], 0, 0, 0
    if engine == 'debug':
        if op == 'compare':
            debug_keys.append(slot[2])
            return e, 0, slot[1], 0, 0, 0
        if op == 'vcompare':
            debug_keys.extend(slot[2])
            return e, 1, slot[1], 0, 0, 0
        return e, 2, 0, 0, 0, 0
    raise NotImplementedError(f'unknown slot {engine} {slot}')


def _err() -> str:
    raw = _lib().vliw_last_error()
    return raw.decode('utf-8', 'replace') if raw else 'unknown native error'


class _MemView:
    def __init__(self, machine: 'FastMachine'):
        self._machine = machine

    def _ptr(self, mut: bool = False):
        lib = _lib()
        fn = lib.vliw_machine_mem_mut if mut else lib.vliw_machine_mem
        addr = fn(self._machine._m)
        n = lib.vliw_machine_mem_len(self._machine._m)
        if not addr:
            raise RuntimeError('native mem pointer is null')
        return ctypes.cast(addr, ctypes.POINTER(ctypes.c_uint32)), n

    def __len__(self) -> int:
        return int(_lib().vliw_machine_mem_len(self._machine._m))

    def __iter__(self):
        ptr, n = self._ptr(False)
        for i in range(n):
            yield int(ptr[i])

    def __getitem__(self, key):
        ptr, n = self._ptr(False)
        if isinstance(key, slice):
            start, stop, step = key.indices(n)
            return [int(ptr[i]) for i in range(start, stop, step)]
        idx = key if key >= 0 else n + key
        if idx < 0 or idx >= n:
            raise IndexError('mem index out of range')
        return int(ptr[idx])

    def __setitem__(self, key, val):
        ptr, n = self._ptr(True)
        if isinstance(key, slice):
            start, stop, step = key.indices(n)
            for i, item in zip(range(start, stop, step), val):
                ptr[i] = _u32(item)
            return
        idx = key if key >= 0 else n + key
        ptr[idx] = _u32(val)


class FastMachine:
    def __init__(
        self,
        mem_dump: list[int],
        program: list,
        debug_info,
        n_cores: int = 1,
        scratch_size: int = 1536,
        trace: bool = False,
        value_trace: dict[Any, int] | None = None,
        omit_debug: bool = False,
    ):
        if trace:
            raise RuntimeError('FastMachine does not implement chrome tracing; use PythonMachine')
        if value_trace is None:
            value_trace = {}
        self.program = program
        self.debug_info = debug_info
        self.value_trace = value_trace
        self.prints = False
        self._enable_pause = True
        self._enable_debug = True
        self.trace = None
        self._m = None
        self._prog = None
        self._owns_prog = True

        self._n_cores = n_cores
        self._scratch_size = scratch_size
        self._cores = None
        encoded = encode_program(program, skip_debug=omit_debug)
        self._debug_keys = encoded.keys
        lib = _lib()
        if encoded.native is not None:
            self._prog = encoded.native
            self._owns_prog = False
        elif len(program) >= _ENCODE_CACHE_MIN:
            self._prog = encoded.ensure_native()
            self._owns_prog = False
        else:
            self._prog = lib.vliw_program_create()
            if not self._prog:
                raise RuntimeError(_err())
            encoded.load_into(self._prog)

        n_mem = len(mem_dump)
        raw = (ctypes.c_uint32 * n_mem)(*mem_dump)
        self._m = lib.vliw_machine_create(raw, len(mem_dump), n_cores, scratch_size, self._prog)
        if not self._m:
            raise RuntimeError(_err())
        if self._owns_prog and self._prog:
            lib.vliw_program_destroy(self._prog)
            self._prog = None
            self._owns_prog = False
        self.mem = _MemView(self)

    @property
    def cycle(self) -> int:
        return int(_lib().vliw_machine_cycle(self._m))

    @property
    def enable_pause(self) -> bool:
        return self._enable_pause

    @enable_pause.setter
    def enable_pause(self, value: bool) -> None:
        self._enable_pause = bool(value)
        _lib().vliw_machine_set_flags(self._m, int(self._enable_pause), int(self._enable_debug))

    @property
    def enable_debug(self) -> bool:
        return self._enable_debug

    @enable_debug.setter
    def enable_debug(self, value: bool) -> None:
        self._enable_debug = bool(value)
        _lib().vliw_machine_set_flags(self._m, int(self._enable_pause), int(self._enable_debug))

    def _push_debug_expected(self) -> None:
        n = len(self._debug_keys)
        if n == 0:
            return
        vals = (ctypes.c_uint32 * n)()
        present = (ctypes.c_uint8 * n)()
        for i, key in enumerate(self._debug_keys):
            if key in self.value_trace:
                present[i] = 1
                vals[i] = _u32(self.value_trace[key])
        if _lib().vliw_machine_set_debug_expected(self._m, vals, present, n) != 0:
            raise RuntimeError(_err())

    def run(self) -> None:
        lib = _lib()
        lib.vliw_machine_set_flags(self._m, int(self._enable_pause), int(self._enable_debug))
        if self._enable_debug:
            self._push_debug_expected()
        if lib.vliw_machine_run(self._m) != 0:
            raise RuntimeError(_err())

    @property
    def cores(self):
        if self._cores is None:
            from problem import Core
            self._cores = [
                Core(id=i, scratch=[0] * self._scratch_size, trace_buf=[])
                for i in range(self._n_cores)
            ]
        self._sync_cores()
        return self._cores

    def _sync_cores(self) -> None:
        lib = _lib()
        from problem import CoreState

        if self._cores is None:
            return
        for core in self._cores:
            core.pc = lib.vliw_machine_pc(self._m, core.id)
            core.state = CoreState(lib.vliw_machine_state(self._m, core.id))
            n = ctypes.c_size_t()
            addr = lib.vliw_machine_scratch(self._m, core.id, ctypes.byref(n))
            if addr and n.value:
                ptr = ctypes.cast(addr, ctypes.POINTER(ctypes.c_uint32))
                core.scratch = [int(ptr[i]) for i in range(n.value)]

    def scratch_map(self, core):
        res = {}
        for addr, (name, length) in self.debug_info.scratch_map.items():
            res[name] = core.scratch[addr : addr + length]
        return res

    def rewrite_slot(self, slot):
        return tuple(self.debug_info.scratch_map.get(s, (None, None))[0] or s for s in slot)

    def rewrite_instr(self, instr):
        res = {}
        for name, slots in instr.items():
            res[name] = [self.rewrite_slot(slot) for slot in slots]
        return res

    def __del__(self):
        lib = _LIB
        if lib is None:
            return
        if self._m:
            lib.vliw_machine_destroy(self._m)
            self._m = None
        if self._prog and self._owns_prog:
            lib.vliw_program_destroy(self._prog)
            self._prog = None
