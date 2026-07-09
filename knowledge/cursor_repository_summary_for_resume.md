# Repository summary for resume
_Exported on 7/6/2026 at 21:00:13 PDT from Cursor (3.7.42)_

---

**User**

Write the repository summary for my resume

---

**Cursor**

Reviewing the repository to draft an accurate resume summary.


Checking the evolver harness and tech stack for a complete picture.


Here are resume-ready options at different lengths. Pick one style or mix bullet + one-liner.

---

### One-line (for a compact Projects row)

**autoresearch** — Autonomous research lab where LLM agents search memoryless card-game heuristics in a locked C++23 Durak engine; paired Monte Carlo eval (5M seeds) showed a ~200-line policy beating a memory-counting baseline at **69% win rate** (CI > 52%).

---

### Short paragraph (3–4 lines under project title)

**autoresearch — LLM-driven heuristic search in imperfect-information games**

Built an autonomous research system to test whether memoryless local heuristics can match memory-based play in two-player Durak. Implemented a deterministic C++23 rules engine, baseline ladder (random → memory-counting), and paired Monte Carlo evaluator; wired an LLM autoresearch loop with staged triage gates, Occam complexity scoring, and a Python evolver harness (parallel A0–A8 arms: MAP-Elites, novelty, sweeps, meta-agents). Discovered a zero-parameter heuristic that **beats the memory-counting opponent** on 5M-seed full eval (**69% point rate**, lower CI 0.689). Includes terminal and browser play UI plus Jupyter progress analysis.

---

### Bullet format (best for impact + tech stack)

**autoresearch** | *C++23, Python, CMake, LLM agents, Monte Carlo simulation*  
Autonomous lab for searching card-game heuristics under a locked rules contract.

- Designed a **C++23 Durak engine** with hidden-information observations, five baseline strategies, and **paired Monte Carlo evaluation** (up to 5M seeds, 95% CIs).
- Built an **LLM autoresearch loop** (experiment + meta modes): staged triage gates, keep/revert thresholds, forbidden-strategy checks, and durable control plane (`program.md`).
- Implemented a **Python evolver harness** with parallel search arms (MAP-Elites, novelty scoring, parameter sweeps, Claude/Cursor meta-agents) in isolated git worktrees.
- Achieved a **memoryless ~200-line heuristic** that **dominates a memory-counting baseline** (B2 vs B4: **0.689 point rate** vs 0.52 significance bar; B3 vs B2 ablation = 0.50, confirming no memory leakage).
- Shipped **terminal CLI + web UI** for human play against the agent and Jupyter charts for experiment tracking.

---

### Achievement-focused single bullet (if space is tight)

- Engineered an LLM-guided autoresearch pipeline (C++23 game sim + Python evolver) that evolved a memoryless Durak heuristic to **~69% win rate vs a memory-counting opponent** on 5M-seed evaluation, with staged gates and parallel search mechanisms (MAP-Elites, meta-agents).

---

### Optional keywords (for ATS or a Skills line)

`C++23` · `CMake` · `Python` · `Monte Carlo simulation` · `game AI / heuristics` · `LLM agents` · `autonomous experimentation` · `MAP-Elites` · `evolutionary search` · `statistical evaluation` · `imperfect-information games`

---

If you tell me your target role (e.g. ML engineer, systems, research engineer) and how much space you have (one bullet vs full project block), I can tighten this to one final version.

---

**User**

add that it is based on:
https://arxiv.org/html/2605.13821v1  
https://github.com/snarktank/ralph  
https://github.com/A-EVO-Lab/a-evolve  
https://github.com/rdi-berkeley/agents-last-exam/blob/main/ale_run/agents/ale_claw/README.md  
@knowledge/hyperagents_paper.txt 

---

**Cursor**

Reviewing the uploaded docs and how they connect to autoresearch so the resume summary cites them accurately.


Here are updated resume versions with lineage attribution woven in.

---

### One-line (compact Projects row)

**autoresearch** — Autonomous research lab synthesizing [AEvo](https://arxiv.org/html/2605.13821v1), [HyperAgents](https://github.com/facebookresearch/HyperAgents), [Ralph](https://github.com/snarktank/ralph), [A-Evolve](https://github.com/A-EVO-Lab/a-evolve), and [ALE Claw](https://github.com/rdi-berkeley/agents-last-exam/blob/main/ale_run/agents/ale_claw/README.md) to evolve memoryless Durak heuristics in a locked C++23 engine; **69% win rate vs memory-counting baseline** on 5M-seed eval.

---

### Short paragraph (3–4 lines)

**autoresearch — LLM-driven heuristic search in imperfect-information games**

Built an autonomous research system to test whether memoryless local heuristics can match memory-based play in two-player Durak. The harness combines ideas from **AEvo** (protected evaluator + meta-editing loop), **HyperAgents** (open-ended archive, parent selection, git-reset contract enforcement), **Ralph** (external budget-owned loop, fresh agent context per round), **A-Evolve** (reference implementation), and **ALE Claw** (minimal bounded inner-session loop with durable memory). Implemented a C++23 rules engine with paired Monte Carlo evaluation (5M seeds) and a Python evolver with parallel search arms (MAP-Elites, novelty, meta-agents). Discovered a zero-parameter ~200-line heuristic that **beats the memory-counting opponent** (**69% point rate**, lower CI 0.689).

---

### Bullet format (recommended)

**autoresearch** | *C++23, Python, LLM agents, Monte Carlo simulation*  
Autonomous lab for searching card-game heuristics under a locked rules contract.

- Synthesized five agent-evolution frameworks — [**AEvo**](https://arxiv.org/html/2605.13821v1) (harnessed meta-editing, protected scoring), [**HyperAgents**](https://github.com/facebookresearch/HyperAgents) (open-ended archive, probabilistic parent selection, allowlist reset), [**Ralph**](https://github.com/snarktank/ralph) (external loop + fresh context per iteration), [**A-Evolve**](https://github.com/A-EVO-Lab/a-evolve) (reference harness), and [**ALE Claw**](https://github.com/rdi-berkeley/agents-last-exam/blob/main/ale_run/agents/ale_claw/README.md) (minimal bounded inner loop, memory flush, DONE termination) — into a single Durak autoresearch pipeline.
- Designed a **C++23 Durak engine** with hidden-information observations, five baseline strategies, and **paired Monte Carlo evaluation** (up to 5M seeds, 95% CIs).
- Built a **Python evolver harness** with staged triage gates, git-reset contract protection, parallel A0–A8 search arms (MAP-Elites, novelty, sweeps, Claude/Cursor meta-agents), and isolated git worktrees.
- Achieved a **memoryless ~200-line heuristic** that **dominates a memory-counting baseline** (B2 vs B4: **0.689 point rate** vs 0.52 significance bar; B3 vs B2 ablation = 0.50).
- Shipped **terminal CLI + web UI** for human play and Jupyter charts for experiment tracking.

---

### Standalone “Based on” line (if you want attribution separate from impact bullets)

**Based on:** [Harnessing Agentic Evolution (AEvo)](https://arxiv.org/html/2605.13821v1) · [A-Evolve](https://github.com/A-EVO-Lab/a-evolve) · [HyperAgents](https://github.com/facebookresearch/HyperAgents) · [Ralph](https://github.com/snarktank/ralph) · [ALE Claw](https://github.com/rdi-berkeley/agents-last-exam/blob/main/ale_run/agents/ale_claw/README.md)

---

### What each source contributed (for interviews / cover letters)

| Source | Role in autoresearch |
|--------|----------------------|
| [**AEvo**](https://arxiv.org/html/2605.13821v1) | Two-phase loop (meta-editing + evolution segment); harness owns evaluation; meta-agent edits search mechanism, not candidates directly |
| [**A-Evolve**](https://github.com/A-EVO-Lab/a-evolve) | Reference implementation of the AEvo harness pattern |
| [**HyperAgents**](https://github.com/facebookresearch/HyperAgents) | Open-ended archive (not greedy hill-climbing); sigmoid × novelty parent selection; git-reset allowlists; MAP-Elites / island population models |
| [**Ralph**](https://github.com/snarktank/ralph) | External `for`-loop owns budget; fresh agent context each round; durable state in git + files (explicitly *not* its PRD `COMPLETE` stop sentinel) |
| [**ALE Claw**](https://github.com/rdi-berkeley/agents-last-exam/blob/main/ale_run/agents/ale_claw/README.md) | Minimal inner-session contract: bounded turns, flush-before-compaction memory, explicit DONE termination, narrow tool surface |

---

### Single achievement bullet (space-constrained)

- Built an agent-evolution harness (AEvo + HyperAgents + Ralph + ALE Claw) over a C++23 Durak simulator that evolved a memoryless heuristic to **~69% win rate vs a memory-counting opponent** on 5M-seed evaluation.

---

If you want one final version tailored to a specific role (research engineer vs systems vs ML), say which and how much space you have.

