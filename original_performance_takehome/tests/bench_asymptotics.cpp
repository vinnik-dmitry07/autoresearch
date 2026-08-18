#include "machine.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <numeric>
#include <string>
#include <vector>

using vliw::Engine;
using vliw::Machine;
using vliw::Op;
using vliw::Program;

namespace {

constexpr std::uint8_t kAdd = 0;
constexpr std::uint8_t kXor = 5;
constexpr std::uint8_t kConst = 3;
constexpr std::uint8_t kLoad = 0;
constexpr std::uint8_t kStore = 0;
constexpr std::uint8_t kVLoad = 2;
constexpr std::uint8_t kVStore = 1;
constexpr std::uint8_t kBroadcast = 13;
constexpr std::uint8_t kHalt = 3;
constexpr std::uint8_t kSelect = 0;
constexpr std::uint8_t kAddImm = 1;

struct Point {
    double n = 0;
    double ns = 0;
};

struct Result {
    std::string name;
    std::string family;
    std::string theoretical;
    double theory_exp = 0;
    std::string unit;
    std::vector<Point> points;
    double empirical_exp = 0;
    double r2 = 0;
    double ns_per_unit = 0;
    bool match = false;
};

double now_ns() {
    using clock = std::chrono::steady_clock;
    return static_cast<double>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(clock::now().time_since_epoch()).count());
}

double median(std::vector<double> xs) {
    std::sort(xs.begin(), xs.end());
    const std::size_t n = xs.size();
    if (n == 0) return 0;
    if (n % 2 == 1) return xs[n / 2];
    return 0.5 * (xs[n / 2 - 1] + xs[n / 2]);
}

void fit_loglog(const std::vector<Point>& pts, double& exp, double& r2) {
    std::vector<double> xs;
    std::vector<double> ys;
    for (const Point& p : pts) {
        if (p.n <= 0 || p.ns <= 0) continue;
        xs.push_back(std::log(p.n));
        ys.push_back(std::log(p.ns));
    }
    const int m = static_cast<int>(xs.size());
    if (m < 2) {
        exp = 0;
        r2 = 0;
        return;
    }
    double sx = 0, sy = 0, sxx = 0, sxy = 0, syy = 0;
    for (int i = 0; i < m; ++i) {
        sx += xs[static_cast<std::size_t>(i)];
        sy += ys[static_cast<std::size_t>(i)];
        sxx += xs[static_cast<std::size_t>(i)] * xs[static_cast<std::size_t>(i)];
        sxy += xs[static_cast<std::size_t>(i)] * ys[static_cast<std::size_t>(i)];
        syy += ys[static_cast<std::size_t>(i)] * ys[static_cast<std::size_t>(i)];
    }
    const double den = static_cast<double>(m) * sxx - sx * sx;
    exp = (std::abs(den) < 1e-18) ? 0.0 : (static_cast<double>(m) * sxy - sx * sy) / den;
    const double ymean = sy / static_cast<double>(m);
    double ss_tot = 0, ss_res = 0;
    const double intercept = (sy - exp * sx) / static_cast<double>(m);
    for (int i = 0; i < m; ++i) {
        const double pred = intercept + exp * xs[static_cast<std::size_t>(i)];
        ss_tot += (ys[static_cast<std::size_t>(i)] - ymean) * (ys[static_cast<std::size_t>(i)] - ymean);
        ss_res += (ys[static_cast<std::size_t>(i)] - pred) * (ys[static_cast<std::size_t>(i)] - pred);
    }
    r2 = (ss_tot < 1e-18) ? 1.0 : 1.0 - ss_res / ss_tot;
}

bool class_match(double theory_exp, double emp) {
    if (theory_exp <= 0.05) return emp < 0.40;
    return std::abs(emp - theory_exp) <= 0.35;
}

void one(Program& p, Engine e, std::uint8_t op, std::uint32_t dest = 0, std::uint32_t a = 0,
         std::uint32_t b = 0, std::uint32_t c = 0) {
    p.begin_bundle();
    p.add(e, op, dest, a, b, c);
    p.end_bundle();
}

Program linear_alu(int n) {
    Program p;
    one(p, Engine::Load, kConst, 0, 1);
    one(p, Engine::Load, kConst, 1, 1);
    for (int i = 0; i < n; ++i) one(p, Engine::Alu, kAdd, 0, 0, 1);
    return p;
}

Program linear_valu(int n) {
    Program p;
    one(p, Engine::Load, kConst, 0, 3);
    one(p, Engine::Valu, kBroadcast, 8, 0);
    one(p, Engine::Valu, kBroadcast, 16, 0);
    for (int i = 0; i < n; ++i) one(p, Engine::Valu, kAdd, 24, 8, 16);
    return p;
}

Program linear_multi(int n) {
    Program p;
    one(p, Engine::Load, kConst, 0, 1);
    one(p, Engine::Load, kConst, 1, 2);
    for (int i = 0; i < n; ++i) {
        p.begin_bundle();
        p.add(Engine::Alu, kAdd, 2, 0, 1);
        p.add(Engine::Alu, kXor, 3, 0, 1);
        p.end_bundle();
    }
    return p;
}

Program linear_mem(int n) {
    Program p;
    one(p, Engine::Load, kConst, 0, 0);
    one(p, Engine::Load, kConst, 1, 1);
    for (int i = 0; i < n; ++i) {
        one(p, Engine::Load, kLoad, 2, 0);
        one(p, Engine::Store, kStore, 1, 2);
    }
    return p;
}

Program linear_vmem(int n) {
    Program p;
    one(p, Engine::Load, kConst, 0, 0);
    one(p, Engine::Load, kConst, 1, 8);
    for (int i = 0; i < n; ++i) {
        one(p, Engine::Load, kVLoad, 16, 0);
        one(p, Engine::Store, kVStore, 1, 16);
    }
    return p;
}

Program linear_flow(int n) {
    Program p;
    one(p, Engine::Load, kConst, 0, 1);
    one(p, Engine::Load, kConst, 1, 4);
    one(p, Engine::Load, kConst, 2, 7);
    for (int i = 0; i < n; ++i) {
        one(p, Engine::Flow, kSelect, 3, 0, 1, 2);
        one(p, Engine::Flow, kAddImm, 3, 3, 1);
    }
    return p;
}

Program linear_debug_interleaved(int n) {
    Program p;
    one(p, Engine::Load, kConst, 0, 1);
    for (int i = 0; i < n; ++i) {
        one(p, Engine::Alu, kAdd, 0, 0, 0);
        p.begin_bundle();
        p.add(Engine::Debug, 2, 0, 0, 0, 0);
        p.end_bundle();
    }
    return p;
}

template <class Fn>
double time_fn(int repeats, Fn&& fn) {
    std::vector<double> samples;
    samples.reserve(static_cast<std::size_t>(repeats));
    fn();
    for (int i = 0; i < repeats; ++i) {
        const double t0 = now_ns();
        fn();
        samples.push_back(now_ns() - t0);
    }
    return median(samples);
}

Result finish(Result r) {
    fit_loglog(r.points, r.empirical_exp, r.r2);
    if (!r.points.empty() && r.points.back().n > 0)
        r.ns_per_unit = r.points.back().ns / r.points.back().n;
    r.match = class_match(r.theory_exp, r.empirical_exp);
    std::printf("  %-28s theory=%-6s emp=%.2f  R2=%.3f  %.2f ns/%s  %s\n", r.name.c_str(),
                r.theoretical.c_str(), r.empirical_exp, r.r2, r.ns_per_unit, r.unit.c_str(),
                r.match ? "MATCH" : "DRIFT");
    std::fflush(stdout);
    return r;
}

const int kSizes[] = {2048, 4096, 8192, 16384, 32768, 65536};

}  // namespace

int main() {
    std::vector<Result> results;
    const std::uint32_t mem0[32] = {};

    std::printf("=== VLIW method asymptotics ===\n");
    std::fflush(stdout);

    {
        std::printf("[1/14] decode_op\n");
        std::fflush(stdout);
        Result r{"decode_op", "isa", "O(n)", 1.0, "call", {}, 0, 0, 0, false};
        for (int n : kSizes) {
            const double ns = time_fn(7, [&] {
                volatile int acc = 0;
                for (int i = 0; i < n; ++i)
                    acc += static_cast<int>(vliw::decode_op(Engine::Alu, static_cast<std::uint8_t>(i % 13)));
                (void)acc;
            });
            r.points.push_back({static_cast<double>(n), ns});
        }
        results.push_back(finish(r));
    }

    {
        std::printf("[2/14] Program::add+end_bundle\n");
        std::fflush(stdout);
        Result r{"Program::add", "program", "O(n)", 1.0, "slot", {}, 0, 0, 0, false};
        for (int n : kSizes) {
            const double ns = time_fn(5, [&] {
                Program p;
                p.slots.reserve(static_cast<std::size_t>(n));
                p.bundles.reserve(static_cast<std::size_t>(n));
                for (int i = 0; i < n; ++i) one(p, Engine::Alu, kAdd, 0, 0, 1);
            });
            r.points.push_back({static_cast<double>(n), ns});
        }
        results.push_back(finish(r));
    }

    {
        std::printf("[3/14] Program::finalize\n");
        std::fflush(stdout);
        Result r{"Program::finalize", "program", "O(1)", 0.0, "call", {}, 0, 0, 0, false};
        for (int n : kSizes) {
            Program p;
            p.slots.reserve(static_cast<std::size_t>(n));
            p.bundles.reserve(static_cast<std::size_t>(n));
            for (int i = 0; i < n; ++i) one(p, Engine::Alu, kAdd, 0, 0, 1);
            const double ns = time_fn(11, [&] { p.finalize(); });
            r.points.push_back({static_cast<double>(n), ns});
        }
        results.push_back(finish(r));
    }

    {
        std::printf("[4/14] Machine ctor (bundles)\n");
        std::fflush(stdout);
        Result r{"Machine::ctor(B)", "machine", "O(n)", 1.0, "bundle", {}, 0, 0, 0, false};
        for (int n : kSizes) {
            Program p = linear_alu(n);
            const double ns = time_fn(5, [&] { Machine m(mem0, p); (void)m.cycle(); });
            r.points.push_back({static_cast<double>(n), ns});
        }
        results.push_back(finish(r));
    }

    {
        std::printf("[5/14] Machine ctor (mem words)\n");
        std::fflush(stdout);
        Result r{"Machine::ctor(M)", "machine", "O(n)", 1.0, "word", {}, 0, 0, 0, false};
        Program p;
        one(p, Engine::Flow, kHalt);
        const int msizes[] = {4096, 16384, 65536, 262144};
        for (int n : msizes) {
            std::vector<std::uint32_t> mem(static_cast<std::size_t>(n), 1u);
            const double ns = time_fn(5, [&] { Machine m(mem, p); (void)m.cycle(); });
            r.points.push_back({static_cast<double>(n), ns});
        }
        results.push_back(finish(r));
    }

    {
        std::printf("[6/14] Machine ctor (cores)\n");
        std::fflush(stdout);
        Result r{"Machine::ctor(N)", "machine", "O(n)", 1.0, "core", {}, 0, 0, 0, false};
        Program p;
        one(p, Engine::Flow, kHalt);
        const int nsizes[] = {1, 2, 4, 8};
        for (int n : nsizes) {
            const double ns = time_fn(7, [&] { Machine m(mem0, p, n); (void)m.cycle(); });
            r.points.push_back({static_cast<double>(n), ns});
        }
        results.push_back(finish(r));
    }

    {
        std::printf("[7/14] set_debug_expected\n");
        std::fflush(stdout);
        Result r{"set_debug_expected", "machine", "O(n)", 1.0, "key", {}, 0, 0, 0, false};
        Program p;
        one(p, Engine::Flow, kHalt);
        Machine m(mem0, p);
        for (int n : kSizes) {
            std::vector<std::uint32_t> vals(static_cast<std::size_t>(n), 1u);
            std::vector<std::uint8_t> present(static_cast<std::size_t>(n), 1);
            const double ns = time_fn(7, [&] { m.set_debug_expected(vals, present); });
            r.points.push_back({static_cast<double>(n), ns});
        }
        results.push_back(finish(r));
    }

    {
        std::printf("[8/14] run_fast alu\n");
        std::fflush(stdout);
        Result r{"run_fast(alu)", "run", "O(n)", 1.0, "op", {}, 0, 0, 0, false};
        for (int n : kSizes) {
            Program p = linear_alu(n);
            const double ctor = time_fn(5, [&] {
                Machine m(mem0, p);
                m.set_enable_debug(false);
                m.set_enable_pause(false);
            });
            const double both = time_fn(5, [&] {
                Machine m(mem0, p);
                m.set_enable_debug(false);
                m.set_enable_pause(false);
                m.run();
            });
            r.points.push_back({static_cast<double>(n), std::max(0.0, both - ctor)});
        }
        results.push_back(finish(r));
    }

    {
        std::printf("[9/14] run_checked alu\n");
        std::fflush(stdout);
        Result r{"run_checked(alu)", "run", "O(n)", 1.0, "op", {}, 0, 0, 0, false};
        for (int n : kSizes) {
            Program p = linear_alu(n);
            const double ctor = time_fn(5, [&] {
                Machine m(mem0, p);
                m.set_enable_debug(true);
                m.set_enable_pause(false);
            });
            const double both = time_fn(5, [&] {
                Machine m(mem0, p);
                m.set_enable_debug(true);
                m.set_enable_pause(false);
                m.run();
            });
            r.points.push_back({static_cast<double>(n), std::max(0.0, both - ctor)});
        }
        results.push_back(finish(r));
    }

    {
        std::printf("[10/14] run_fast valu / mem / flow / multi / debug-skip\n");
        std::fflush(stdout);
        struct Spec {
            const char* name;
            Program (*make)(int);
        };
        const Spec specs[] = {
            {"run_fast(valu)", linear_valu},
            {"run_fast(load/store)", linear_mem},
            {"run_fast(vload/vstore)", linear_vmem},
            {"run_fast(flow)", linear_flow},
            {"step_multi(2-slot)", linear_multi},
            {"run_fast(debug-skip)", linear_debug_interleaved},
        };
        for (const Spec& spec : specs) {
            Result r{spec.name, "run", "O(n)", 1.0, "op", {}, 0, 0, 0, false};
            for (int n : kSizes) {
                Program p = spec.make(n);
                const double ctor = time_fn(5, [&] {
                    Machine m(mem0, p);
                    m.set_enable_debug(false);
                    m.set_enable_pause(false);
                });
                const double both = time_fn(5, [&] {
                    Machine m(mem0, p);
                    m.set_enable_debug(false);
                    m.set_enable_pause(false);
                    m.run();
                });
                r.points.push_back({static_cast<double>(n), std::max(0.0, both - ctor)});
            }
            results.push_back(finish(r));
        }
    }

    {
        std::printf("[11/14] accessors O(1)\n");
        std::fflush(stdout);
        Program p = linear_alu(4096);
        Machine m(mem0, p);
        m.set_enable_debug(false);
        m.run();
        struct Acc {
            const char* name;
            void (*fn)(Machine&);
        };
        const Acc accs[] = {
            {"cycle()", [](Machine& x) { volatile auto v = x.cycle(); (void)v; }},
            {"mem()", [](Machine& x) { volatile auto v = x.mem().size(); (void)v; }},
            {"cores()", [](Machine& x) { volatile auto v = x.cores().size(); (void)v; }},
            {"scratch_size()", [](Machine& x) { volatile auto v = x.scratch_size(); (void)v; }},
            {"set_enable_pause", [](Machine& x) { x.set_enable_pause(false); }},
            {"set_enable_debug", [](Machine& x) { x.set_enable_debug(false); }},
        };
        for (const Acc& acc : accs) {
            Result r{acc.name, "accessor", "O(n) n-calls", 1.0, "call", {}, 0, 0, 0, false};
            const int nsizes[] = {4096, 8192, 16384, 32768, 65536};
            for (int n : nsizes) {
                const double ns = time_fn(9, [&] {
                    for (int i = 0; i < n; ++i) acc.fn(m);
                });
                r.points.push_back({static_cast<double>(n), ns});
            }
            results.push_back(finish(r));
        }
    }

    {
        std::printf("[12/14] mem()/mem_mut scan\n");
        std::fflush(stdout);
        Result r{"mem_scan", "accessor", "O(n)", 1.0, "word", {}, 0, 0, 0, false};
        Program p;
        one(p, Engine::Flow, kHalt);
        const int msizes[] = {4096, 16384, 65536, 262144};
        for (int n : msizes) {
            std::vector<std::uint32_t> mem(static_cast<std::size_t>(n), 1u);
            Machine m(mem, p);
            const double ns = time_fn(7, [&] {
                auto view = m.mem();
                volatile std::uint32_t acc = 0;
                for (std::uint32_t w : view) acc += w;
                (void)acc;
            });
            r.points.push_back({static_cast<double>(n), ns});
        }
        results.push_back(finish(r));
    }

    {
        std::printf("[13/14] Program copy / Machine copy\n");
        std::fflush(stdout);
        Result r1{"Program::copy", "program", "O(n)", 1.0, "bundle", {}, 0, 0, 0, false};
        Result r2{"Machine::copy", "machine", "O(n)", 1.0, "bundle", {}, 0, 0, 0, false};
        for (int n : kSizes) {
            Program p = linear_alu(n);
            Machine m(mem0, p);
            const double ns1 = time_fn(5, [&] { Program q = p; (void)q.bundles.size(); });
            const double ns2 = time_fn(5, [&] { Machine q = m; (void)q.cycle(); });
            r1.points.push_back({static_cast<double>(n), ns1});
            r2.points.push_back({static_cast<double>(n), ns2});
        }
        results.push_back(finish(r1));
        results.push_back(finish(r2));
    }

    {
        std::printf("[14/14] begin_bundle empty pair\n");
        std::fflush(stdout);
        Result r{"begin/end_bundle", "program", "O(n)", 1.0, "bundle", {}, 0, 0, 0, false};
        for (int n : kSizes) {
            const double ns = time_fn(5, [&] {
                Program p;
                p.bundles.reserve(static_cast<std::size_t>(n));
                for (int i = 0; i < n; ++i) {
                    p.begin_bundle();
                    p.end_bundle();
                }
            });
            r.points.push_back({static_cast<double>(n), ns});
        }
        results.push_back(finish(r));
    }

    double mae = 0, mr2 = 0;
    int matches = 0;
    for (const Result& r : results) {
        mae += std::abs(r.empirical_exp - r.theory_exp);
        mr2 += r.r2;
        if (r.match) ++matches;
    }
    const double nres = static_cast<double>(results.size());
    mae /= nres;
    mr2 /= nres;
    const double match_rate = static_cast<double>(matches) / nres;

    std::printf("\n=== macro metrics ===\n");
    std::printf("methods=%d  macro_MAE(exp)=%.3f  macro_R2=%.3f  match_rate=%.3f\n",
                static_cast<int>(results.size()), mae, mr2, match_rate);

    std::ofstream out("asymptotics.json");
    out << "{\n";
    out << "  \"macro\": {\"n_methods\": " << results.size() << ", \"mean_abs_exp_error\": " << mae
        << ", \"mean_r2\": " << mr2 << ", \"match_rate\": " << match_rate << "},\n";
    out << "  \"methods\": [\n";
    for (std::size_t i = 0; i < results.size(); ++i) {
        const Result& r = results[i];
        out << "    {\"name\": \"" << r.name << "\", \"family\": \"" << r.family
            << "\", \"theoretical\": \"" << r.theoretical << "\", \"theory_exp\": " << r.theory_exp
            << ", \"empirical_exp\": " << r.empirical_exp << ", \"r2\": " << r.r2
            << ", \"ns_per_unit\": " << r.ns_per_unit << ", \"unit\": \"" << r.unit
            << "\", \"match\": " << (r.match ? "true" : "false") << ", \"points\": [";
        for (std::size_t j = 0; j < r.points.size(); ++j) {
            if (j) out << ", ";
            out << "{\"n\": " << r.points[j].n << ", \"ns\": " << r.points[j].ns << "}";
        }
        out << "]}";
        if (i + 1 != results.size()) out << ",";
        out << "\n";
    }
    out << "  ]\n}\n";
    std::printf("wrote asymptotics.json\n");
    return 0;
}
