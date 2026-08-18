"""
# Anthropic's Original Performance Engineering Take-home (Release version)

Copyright Anthropic PBC 2026. Permission is granted to modify and use, but not
to publish or redistribute your solutions so it's hard to find spoilers.

# Task

- Optimize the kernel (in KernelBuilder.build_kernel) as much as possible in the
  available time, as measured by test_kernel_cycles on a frozen separate copy
  of the simulator.

Validate your results using `python tests/submission_tests.py` without modifying
anything in the tests/ folder.

We recommend you look through problem.py next.
"""

from collections import defaultdict
import random
import unittest

from problem import (
    Engine,
    DebugInfo,
    SLOT_LIMITS,
    VLEN,
    N_CORES,
    SCRATCH_SIZE,
    Machine,
    Tree,
    Input,
    HASH_STAGES,
    reference_kernel,
    build_mem_image,
    reference_kernel2,
    reference_final,
)


_PHASE_ID = {
    'unknown': 0,
    'init': 1,
    'ldst': 2,
    'hash': 3,
    'walk': 4,
    'store': 5,
    'gather': 6,
}


class _InstrView:
    """Lazy oneslot view: encode/profile read compact rows, PythonMachine indexes dicts."""

    __slots__ = ('_kb',)

    def __init__(self, kb: 'KernelBuilder'):
        self._kb = kb

    def __len__(self) -> int:
        return self._kb._n

    def __bool__(self) -> bool:
        return self._kb._n > 0

    def __iter__(self):
        kb = self._kb
        eng = kb._eng
        slots = kb._slots
        for i in range(kb._n):
            yield {eng[i]: [slots[i]]}

    def __getitem__(self, idx):
        kb = self._kb
        n = kb._n
        if isinstance(idx, slice):
            start, stop, step = idx.indices(n)
            return [{kb._eng[i]: [kb._slots[i]]} for i in range(start, stop, step)]
        i = idx if idx >= 0 else n + idx
        return {kb._eng[i]: [kb._slots[i]]}


class KernelBuilder:
    def __init__(self):
        self._eng: list = []
        self._slots: list = []
        self._phases = bytearray()
        self._depths = bytearray()
        self._n = 0
        self._instrs = None
        self._encoded: dict = {}
        self._has_debug = False
        self._billed_phases = None
        self._billed_depths = None
        self._body_repeat = None
        self._iter_consts = None
        self._shape = None
        self.scratch = {}
        self.scratch_debug = {}
        self.scratch_ptr = 0
        self.const_map = {}
        self._phase_name = 'init'
        self._phase_id = 1
        self._depth_id = 255

    @property
    def instrs(self):
        if self._instrs is None:
            self._instrs = _InstrView(self)
        return self._instrs

    @property
    def phases(self):
        return self._phases

    @property
    def depths(self):
        return self._depths

    @property
    def phase(self) -> str:
        return self._phase_name

    @phase.setter
    def phase(self, name: str) -> None:
        self._phase_name = name
        self._phase_id = _PHASE_ID.get(name, 0)

    def debug_info(self):
        return DebugInfo(scratch_map=self.scratch_debug)

    def build(self, slots: list[tuple[Engine, tuple]], vliw: bool = False):
        # Simple slot packing that just uses one slot per instruction bundle
        instrs = []
        for engine, slot in slots:
            instrs.append({engine: [slot]})
        return instrs

    def _reserve(self, cap: int) -> None:
        extra = cap - len(self._eng)
        if extra <= 0:
            return
        self._eng.extend([None] * extra)
        self._slots.extend([None] * extra)
        self._phases.extend(b'\x00' * extra)
        self._depths.extend(b'\xff' * extra)

    def add(self, engine, slot):
        i = self._n
        eng = self._eng
        if i >= len(eng):
            self._reserve(i + 256)
            eng = self._eng
        eng[i] = engine
        self._slots[i] = slot
        self._phases[i] = self._phase_id
        self._depths[i] = self._depth_id
        self._n = i + 1
        if engine == 'debug':
            self._has_debug = True
        if self._encoded:
            self._encoded.clear()
        self._billed_phases = None
        self._billed_depths = None
        if self._body_repeat is not None:
            self._body_repeat = None

    def add_rows(self, engines: list, slots: list, phase_ids: bytes) -> None:
        n = len(engines)
        i = self._n
        end = i + n
        if end > len(self._eng):
            self._reserve(end + 256)
        self._eng[i:end] = engines
        self._slots[i:end] = slots
        self._phases[i:end] = phase_ids
        self._depths[i:end] = bytes([self._depth_id]) * n
        self._n = end
        if self._encoded:
            self._encoded.clear()
        self._billed_phases = None
        self._billed_depths = None

    def _repeat_body(self, start: int, n: int, times: int) -> None:
        if times <= 0 or n <= 0:
            return
        eng = self._eng[start : start + n]
        slots = self._slots[start : start + n]
        ph = bytes(self._phases[start : start + n])
        dep = bytes(self._depths[start : start + n])
        self._eng = self._eng[: self._n]
        self._slots = self._slots[: self._n]
        self._phases = self._phases[: self._n]
        self._depths = self._depths[: self._n]
        self._eng.extend(eng * times)
        self._slots.extend(slots * times)
        self._phases.extend(ph * times)
        self._depths.extend(dep * times)
        self._n += n * times

    def billed_phases(self) -> bytearray:
        if not self._has_debug:
            return self._phases
        if self._billed_phases is None:
            self._billed_phases = bytearray(
                self._phases[i] for i in range(self._n) if self._eng[i] != 'debug'
            )
        return self._billed_phases

    def billed_depths(self) -> bytearray:
        if not self._has_debug:
            return self._depths
        if self._billed_depths is None:
            self._billed_depths = bytearray(
                self._depths[i] for i in range(self._n) if self._eng[i] != 'debug'
            )
        return self._billed_depths

    def _fill_round_depths(self, prefix_n: int, body_n: int, rounds: int, height: int) -> None:
        n = self._n
        if len(self._depths) < n:
            self._depths.extend(b'\xff' * (n - len(self._depths)))
        self._depths = self._depths[:n]
        span = height + 1 if height >= 0 else 1
        for rnd in range(rounds):
            depth = rnd % span
            start = prefix_n + rnd * body_n
            stop = min(start + body_n, n)
            if start < stop:
                self._depths[start:stop] = bytes([depth]) * (stop - start)
        self._billed_depths = None

    def ensure_encoded(self, skip_debug: bool = False):
        hit = self._encoded.get(skip_debug)
        if hit is not None:
            return hit
        from vliw_native import (
            _SLOT_STRUCT,
            encode_kernel_rows,
            repeat_encoded_body,
            stamp_encoded_iters,
        )
        import ctypes

        repeat = self._body_repeat
        consts = self._iter_consts
        if repeat is not None and not (skip_debug and self._has_debug):
            prefix_n, iter_n, batch_size, rounds = repeat
            body_n = iter_n * batch_size
            suffix_start = prefix_n + body_n * rounds
            suf_n = self._n - suffix_start
            tail = None
            if suf_n > 0:
                tail = encode_kernel_rows(
                    self._eng, self._slots, skip_debug, n=suf_n, start=suffix_start
                )
            if consts and len(consts) == batch_size and not self._has_debug:
                sz = _SLOT_STRUCT.size
                n_hash = iter_n - 18
                store_a = 7 + n_hash + 7
                patch_offs = (
                    12,
                    2 * sz + 12,
                    store_a * sz + 12,
                    (store_a + 2) * sz + 12,
                )
                prefix = encode_kernel_rows(
                    self._eng, self._slots, skip_debug, n=prefix_n
                )
                tmpl = encode_kernel_rows(
                    self._eng, self._slots, skip_debug, n=iter_n, start=prefix_n
                )
                hit = stamp_encoded_iters(
                    prefix, tmpl, consts, patch_offs, rounds, tail
                )
            else:
                head = encode_kernel_rows(
                    self._eng, self._slots, skip_debug, n=prefix_n + body_n
                )
                hit = repeat_encoded_body(head, prefix_n, body_n, rounds, tail)
        else:
            hit = encode_kernel_rows(self._eng, self._slots, skip_debug, n=self._n)
        raw = self.billed_phases() if skip_debug else self._phases
        hit.phase_c = (ctypes.c_uint8 * len(raw)).from_buffer_copy(raw)
        hit.phase_n = len(raw)
        raw_d = self.billed_depths() if skip_debug else self._depths
        if raw_d:
            hit.depth_c = (ctypes.c_uint8 * len(raw_d)).from_buffer_copy(raw_d)
            hit.depth_n = len(raw_d)
        hit.shape = self._shape
        self._encoded[skip_debug] = hit
        return hit

    def alloc_scratch(self, name=None, length=1):
        addr = self.scratch_ptr
        if name is not None:
            self.scratch[name] = addr
            self.scratch_debug[addr] = (name, length)
        self.scratch_ptr += length
        assert self.scratch_ptr <= SCRATCH_SIZE, 'Out of scratch space'
        return addr

    def scratch_const(self, val, name=None):
        cached = self.const_map.get(val)
        if cached is not None:
            return cached
        addr = self.alloc_scratch(name)
        self.add('load', ('const', addr, val))
        self.const_map[val] = addr
        return addr

    def _emit_rounds_nodebug(
        self,
        batch_size,
        rounds,
        i_consts,
        hash_ops,
        tmp1,
        tmp2,
        tmp3,
        tmp_idx,
        tmp_val,
        tmp_node_val,
        tmp_addr,
        inp_idx_p,
        inp_val_p,
        forest_p,
        n_nodes_s,
        zero_const,
        one_const,
        two_const,
    ):
        """One batch round, then memcpy the rows — rounds are identical without debug."""
        hash_slots = []
        for op1, c1, op2, op3, c3 in hash_ops:
            hash_slots.append((op1, tmp1, tmp_val, c1))
            hash_slots.append((op3, tmp2, tmp_val, c3))
            hash_slots.append((op2, tmp_val, tmp1, tmp2))
        n_hash = len(hash_slots)
        engines = (
            ['alu', 'load', 'alu', 'load', 'alu', 'load', 'alu']
            + ['alu'] * n_hash
            + ['alu', 'alu', 'flow', 'alu', 'alu', 'alu', 'flow']
            + ['alu', 'store', 'alu', 'store']
        )
        phases = bytes([2, 2, 2, 2, 2, 6, 2] + [3] * n_hash + [4] * 7 + [5] * 4)
        store_a = 7 + n_hash + 7
        store_b = store_a + 2
        ic0 = i_consts[0]
        base_slots = [
            ('+', tmp_addr, inp_idx_p, ic0),
            ('load', tmp_idx, tmp_addr),
            ('+', tmp_addr, inp_val_p, ic0),
            ('load', tmp_val, tmp_addr),
            ('+', tmp_addr, forest_p, tmp_idx),
            ('load', tmp_node_val, tmp_addr),
            ('^', tmp_val, tmp_val, tmp_node_val),
            *hash_slots,
            ('%', tmp1, tmp_val, two_const),
            ('==', tmp1, tmp1, zero_const),
            ('select', tmp3, tmp1, one_const, two_const),
            ('*', tmp_idx, tmp_idx, two_const),
            ('+', tmp_idx, tmp_idx, tmp3),
            ('<', tmp1, tmp_idx, n_nodes_s),
            ('select', tmp_idx, tmp1, tmp_idx, zero_const),
            ('+', tmp_addr, inp_idx_p, ic0),
            ('store', tmp_addr, tmp_idx),
            ('+', tmp_addr, inp_val_p, ic0),
            ('store', tmp_addr, tmp_val),
        ]
        prefix_n = self._n
        add_rows = self.add_rows
        for ic in i_consts:
            sl = base_slots.copy()
            sl[0] = ('+', tmp_addr, inp_idx_p, ic)
            sl[2] = ('+', tmp_addr, inp_val_p, ic)
            sl[store_a] = ('+', tmp_addr, inp_idx_p, ic)
            sl[store_b] = ('+', tmp_addr, inp_val_p, ic)
            add_rows(engines, sl, phases)
        body_n = self._n - prefix_n
        if rounds > 1:
            self._repeat_body(prefix_n, body_n, rounds - 1)
        self._iter_consts = i_consts
        return prefix_n, len(engines), batch_size, rounds

    def build_hash(self, val_hash_addr, tmp1, tmp2, round, i):
        slots = []
        for hi, (op1, val1, op2, op3, val3) in enumerate(HASH_STAGES):
            slots.append(('alu', (op1, tmp1, val_hash_addr, self.scratch_const(val1))))
            slots.append(('alu', (op3, tmp2, val_hash_addr, self.scratch_const(val3))))
            slots.append(('alu', (op2, val_hash_addr, tmp1, tmp2)))
            slots.append(('debug', ('compare', val_hash_addr, (round, i, 'hash_stage', hi))))
        return slots

    def build_kernel(
        self,
        forest_height: int,
        n_nodes: int,
        batch_size: int,
        rounds: int,
        emit_debug: bool = True,
    ):
        """
        Like reference_kernel2 but building actual instructions.
        Scalar implementation using only scalar ALU and load/store.
        """
        self._shape = (forest_height, rounds, batch_size)
        n_hash = 3 * len(HASH_STAGES)
        per = 7 + n_hash + 7 + 4
        if emit_debug:
            per += 3 + len(HASH_STAGES) + 1 + 2
            self._reserve(
                48 + 2 * len(HASH_STAGES) + batch_size + rounds * batch_size * per
            )
        else:
            self._reserve(48 + 2 * len(HASH_STAGES) + batch_size + batch_size * per + 2)
        tmp1 = self.alloc_scratch('tmp1')
        tmp2 = self.alloc_scratch('tmp2')
        tmp3 = self.alloc_scratch('tmp3')
        init_vars = [
            'rounds',
            'n_nodes',
            'batch_size',
            'forest_height',
            'forest_values_p',
            'inp_indices_p',
            'inp_values_p',
        ]
        for v in init_vars:
            self.alloc_scratch(v, 1)
        for i, v in enumerate(init_vars):
            self.add('load', ('const', tmp1, i))
            self.add('load', ('load', self.scratch[v], tmp1))

        zero_const = self.scratch_const(0)
        one_const = self.scratch_const(1)
        two_const = self.scratch_const(2)
        hash_ops = [
            (op1, self.scratch_const(val1), op2, op3, self.scratch_const(val3))
            for op1, val1, op2, op3, val3 in HASH_STAGES
        ]
        i_consts = [self.scratch_const(i) for i in range(batch_size)]

        self.add('flow', ('pause',))
        if emit_debug:
            self.add('debug', ('comment', 'Starting loop'))

        tmp_idx = self.alloc_scratch('tmp_idx')
        tmp_val = self.alloc_scratch('tmp_val')
        tmp_node_val = self.alloc_scratch('tmp_node_val')
        tmp_addr = self.alloc_scratch('tmp_addr')
        inp_idx_p = self.scratch['inp_indices_p']
        inp_val_p = self.scratch['inp_values_p']
        forest_p = self.scratch['forest_values_p']
        n_nodes_s = self.scratch['n_nodes']
        add = self.add

        if emit_debug:
            for rnd in range(rounds):
                self._depth_id = rnd % (forest_height + 1)
                for i in range(batch_size):
                    i_const = i_consts[i]
                    self.phase = 'ldst'
                    add('alu', ('+', tmp_addr, inp_idx_p, i_const))
                    add('load', ('load', tmp_idx, tmp_addr))
                    add('debug', ('compare', tmp_idx, (rnd, i, 'idx')))
                    add('alu', ('+', tmp_addr, inp_val_p, i_const))
                    add('load', ('load', tmp_val, tmp_addr))
                    add('debug', ('compare', tmp_val, (rnd, i, 'val')))
                    add('alu', ('+', tmp_addr, forest_p, tmp_idx))
                    self.phase = 'gather'
                    add('load', ('load', tmp_node_val, tmp_addr))
                    add('debug', ('compare', tmp_node_val, (rnd, i, 'node_val')))
                    self.phase = 'ldst'
                    add('alu', ('^', tmp_val, tmp_val, tmp_node_val))
                    self.phase = 'hash'
                    for hi, (op1, c1, op2, op3, c3) in enumerate(hash_ops):
                        add('alu', (op1, tmp1, tmp_val, c1))
                        add('alu', (op3, tmp2, tmp_val, c3))
                        add('alu', (op2, tmp_val, tmp1, tmp2))
                        add('debug', ('compare', tmp_val, (rnd, i, 'hash_stage', hi)))
                    add('debug', ('compare', tmp_val, (rnd, i, 'hashed_val')))
                    self.phase = 'walk'
                    add('alu', ('%', tmp1, tmp_val, two_const))
                    add('alu', ('==', tmp1, tmp1, zero_const))
                    add('flow', ('select', tmp3, tmp1, one_const, two_const))
                    add('alu', ('*', tmp_idx, tmp_idx, two_const))
                    add('alu', ('+', tmp_idx, tmp_idx, tmp3))
                    add('debug', ('compare', tmp_idx, (rnd, i, 'next_idx')))
                    add('alu', ('<', tmp1, tmp_idx, n_nodes_s))
                    add('flow', ('select', tmp_idx, tmp1, tmp_idx, zero_const))
                    add('debug', ('compare', tmp_idx, (rnd, i, 'wrapped_idx')))
                    self.phase = 'store'
                    add('alu', ('+', tmp_addr, inp_idx_p, i_const))
                    add('store', ('store', tmp_addr, tmp_idx))
                    add('alu', ('+', tmp_addr, inp_val_p, i_const))
                    add('store', ('store', tmp_addr, tmp_val))
        else:
            prefix_n, iter_n, batch_n, n_rounds = self._emit_rounds_nodebug(
                batch_size,
                rounds,
                i_consts,
                hash_ops,
                tmp1,
                tmp2,
                tmp3,
                tmp_idx,
                tmp_val,
                tmp_node_val,
                tmp_addr,
                inp_idx_p,
                inp_val_p,
                forest_p,
                n_nodes_s,
                zero_const,
                one_const,
                two_const,
            )

        self.phase = 'init'
        self._depth_id = 255
        add('flow', ('pause',))
        n = self._n
        self._eng = self._eng[:n]
        self._slots = self._slots[:n]
        self._phases = self._phases[:n]
        self._depths = self._depths[:n]
        if not emit_debug:
            self._body_repeat = (prefix_n, iter_n, batch_n, n_rounds)
            self._fill_round_depths(prefix_n, iter_n * batch_n, n_rounds, forest_height)


_KERNEL_CACHE: dict[tuple, KernelBuilder] = {}


def get_kernel(
    forest_height: int,
    n_nodes: int,
    batch_size: int,
    rounds: int,
    emit_debug: bool = True,
) -> KernelBuilder:
    src = hash(KernelBuilder.build_kernel.__code__.co_code)
    key = (src, forest_height, n_nodes, batch_size, rounds, emit_debug)
    kb = _KERNEL_CACHE.get(key)
    if kb is None:
        kb = KernelBuilder()
        kb.build_kernel(forest_height, n_nodes, batch_size, rounds, emit_debug=emit_debug)
        kb.ensure_encoded(skip_debug=not emit_debug)
        _KERNEL_CACHE[key] = kb
    return kb


BASELINE = 147734

def do_kernel_test(
    forest_height: int,
    rounds: int,
    batch_size: int,
    seed: int = 123,
    trace: bool = False,
    prints: bool = False,
):
    print(f"{forest_height=}, {rounds=}, {batch_size=}")
    random.seed(seed)
    forest = Tree.generate(forest_height)
    inp = Input.generate(forest, batch_size, rounds)
    mem = build_mem_image(forest, inp)

    kb = get_kernel(forest.height, len(forest.values), len(inp.indices), rounds, emit_debug=True)

    value_trace = {}
    machine = Machine(
        mem,
        kb.instrs,
        kb.debug_info(),
        n_cores=N_CORES,
        value_trace=value_trace,
        trace=trace,
    )
    machine.prints = prints
    for i, ref_mem in enumerate(reference_kernel2(mem, value_trace)):
        machine.run()
        inp_values_p = ref_mem[6]
        if prints:
            print(machine.mem[inp_values_p : inp_values_p + len(inp.values)])
            print(ref_mem[inp_values_p : inp_values_p + len(inp.values)])
        assert (
            machine.mem[inp_values_p : inp_values_p + len(inp.values)]
            == ref_mem[inp_values_p : inp_values_p + len(inp.values)]
        ), f"Incorrect result on round {i}"
        inp_indices_p = ref_mem[5]
        if prints:
            print(machine.mem[inp_indices_p : inp_indices_p + len(inp.indices)])
            print(ref_mem[inp_indices_p : inp_indices_p + len(inp.indices)])
        # Updating these in memory isn't required, but you can enable this check for debugging
        # assert machine.mem[inp_indices_p:inp_indices_p+len(inp.indices)] == ref_mem[inp_indices_p:inp_indices_p+len(inp.indices)]

    print("CYCLES: ", machine.cycle)
    print("Speedup over baseline: ", BASELINE / machine.cycle)
    return machine.cycle


def quick_kernel_check(
    forest_height: int,
    rounds: int,
    batch_size: int,
    seed: int = 123,
) -> int:
    """Submission-shaped check: cached kernel, no debug, one run, untraced ref."""
    random.seed(seed)
    forest = Tree.generate(forest_height)
    inp = Input.generate(forest, batch_size, rounds)
    mem = build_mem_image(forest, inp)
    kb = get_kernel(
        forest.height, len(forest.values), len(inp.indices), rounds, emit_debug=False
    )
    machine = Machine(
        mem,
        kb.instrs,
        kb.debug_info(),
        n_cores=N_CORES,
        value_trace={},
        omit_debug=True,
    )
    machine.enable_pause = False
    machine.enable_debug = False
    machine.run()
    ref = reference_final(list(mem))
    inp_values_p = ref[6]
    assert (
        machine.mem[inp_values_p : inp_values_p + len(inp.values)]
        == ref[inp_values_p : inp_values_p + len(inp.values)]
    ), 'Incorrect output values'
    return machine.cycle


class Tests(unittest.TestCase):
    def test_ref_kernels(self):
        """
        Test the reference kernels against each other
        """
        random.seed(123)
        for i in range(10):
            f = Tree.generate(4)
            inp = Input.generate(f, 10, 6)
            mem = build_mem_image(f, inp)
            reference_kernel(f, inp)
            for _ in reference_kernel2(mem, {}):
                pass
            assert inp.indices == mem[mem[5] : mem[5] + len(inp.indices)]
            assert inp.values == mem[mem[6] : mem[6] + len(inp.values)]

    def test_kernel_trace(self):
        # Full-scale example for performance testing
        do_kernel_test(10, 16, 256, trace=True, prints=False)

    # Passing this test is not required for submission, see submission_tests.py for the actual correctness test
    # You can uncomment this if you think it might help you debug
    # def test_kernel_correctness(self):
    #     for batch in range(1, 3):
    #         for forest_height in range(3):
    #             do_kernel_test(
    #                 forest_height + 2, forest_height + 4, batch * 16 * VLEN * N_CORES
    #             )

    def test_kernel_cycles(self):
        do_kernel_test(10, 16, 256)


# To run all the tests:
#    python perf_takehome.py
# To run a specific test:
#    python perf_takehome.py Tests.test_kernel_cycles
# Fast hypothesis loop (cycles + correctness, no Perfetto):
#    python check.py
#    python check.py --prof
# Optional small trace + native Perfetto:
#    python check.py --trace
# Full debug trace (slow):
#    python perf_takehome.py Tests.test_kernel_trace
#    perfetto --httpd trace.json

# To run the proper checks to see which thresholds you pass:
#    python tests/submission_tests.py

if __name__ == "__main__":
    unittest.main()
