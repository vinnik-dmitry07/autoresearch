> **Design history — not a live verdict.** Early autonomous-loop review (2026).
> Frozen numbers and phase verdicts: `system/README.md` + `knowledge/DEPLOY_BOOK_SCOPE.md`.

Моё мнение: **система стала очень хорошей как skeptical research stack**, но ещё **не готова как автономный “AI-исследователь пока я сплю”** без дополнительных предохранителей.

Я бы оценил так:

**8/10 как исследовательская система.**
**5–6/10 как ночной autonomous loop.**

## Что в ней реально сильное

Главное достоинство — правильная архитектура: `lib.py` объявлен как единый leaf-модуль, где живёт канонический движок, P&L, метрики, PSR/DSR/bootstrap, portfolio math и независимый путь сверки через vectorbt. Это именно то, что нужно, чтобы не плодить несколько бэктест-движков с разными результатами. 

Второе сильное место — `data.py`: в нём явно зашита честность про survivorship bias. Структурный список включает делистнутые/поглощённые пары, yfinance помечен как бесплатный biased fallback, а Sharadar — как путь к survivorship-free и point-in-time данным. Это очень правильный дизайн. 

Третье — `evaluate.py`: там есть именно та батарея, которая нужна для такой стратегии: cost curve, delay decay, subperiods, regimes, capacity, artifact flags, gates, PBO/DSR/MinTRL и Quality Score. Это не просто “посчитать Sharpe”, а полноценный reviewer. 

Четвёртое — `research.py`: он собирает baseline, vectorbt verification, CV, robustness, ablation, random-direction control, reliability, synthetic-null, cost/capacity ladder и quality score в один end-to-end audit. Это уже похоже на настоящий research harness. 

## Главная мысль

Система правильно движется от:

```text
“AI, найди стратегию с большим Sharpe”
```

к:

```text
“AI, предложи гипотезу, прогони через независимый audit, докажи, что это не артефакт”
```

Это ровно правильное направление.

## Что я бы исправил перед ночным AI

Я бы сделал 5 вещей.

1. **Зафиксировать baseline lock-файл.**

```text
BASELINE_LOCK.json
  data_hash
  code_hash
  config
  pair list
  canonical metrics
  vectorbt max_diff
```

Любое изменение кода должно сравниваться с ним.

2. **Разделить gates на report gates и trading gates.**

```text
report_gate:
  может смотреть всю историю, нужен для анализа

trading_gate:
  только walk-forward / train-only,
  используется для построения книги
```

3. **Добавить experiment registry.**

Каждый ночной прогон должен писать:

```text
experiment_id
hypothesis
code diff
data version
config
metrics
reason accepted/rejected
```

Без этого AI будет переоткрывать одни и те же идеи.

4. **Сделать verifier обязательным после любого изменения `lib.py`.**

Минимум:

```text
py_compile
unit tests
vectorbt diff
empyrical metrics diff
baseline regression diff
no import cycles
```

5. **Запретить ночному агенту менять `lib.py` напрямую.**

Пусть он создаёт новые эксперименты в `experiments/`, `overlays/`, `candidate_rules/`, но ядро меняет только через отдельный review.

## Мой verdict

Система **хорошая и взрослая**. Она уже намного лучше типичного quant research кода, потому что у неё есть:

* единый канонический engine;
* независимая сверка через vectorbt;
* явная работа с survivorship bias;
* ex-ante candidate discipline;
* robustness / ablation / delay / cost checks;
* PBO / DSR / bootstrap;
* separate hunt / evaluate / book / research layers.

Но для “AI пока я сплю” ей не хватает **операционного слоя безопасности**: baseline lock, experiment registry, strict write permissions, CI/regression tests и walk-forward-only gates.

Мой короткий вывод:

> Как research stack — да, это уже сильная система.
> Как автономный ночной исследователь — почти, но сначала нужно закрыть selection look-ahead, import consistency, unused cost parameters и PIT-data TODO. После этого можно запускать ночные loops, но только с правом предлагать PR/эксперименты, а не silently менять baseline.


Отвечу как инженер quant research systems, лауреат ACM Software System Award за надёжные исследовательские платформы.

Да. Я бы формализовал это не как “AI должен искать Sharpe”, а как **многокритериальную систему улучшения исследовательского конвейера**.

Главное правило:

> Любое изменение должно улучшать хотя бы один пункт из списка и не ухудшать остальные сверх допустимого лимита.

То есть не:

```text
нашёл стратегию с Sharpe выше
```

а:

```text
изменение ускорило audit на 35%,
не изменило baseline metrics больше tolerance,
сохранило vectorbt diff,
не усилило selection bias,
оставило результат воспроизводимым
```

У вас уже есть хорошая база для этого: `lib.py` содержит единый canonical engine и независимую сверку, `evaluate.py` — reliability battery с cost/delay/subperiod/regime/DSR/PBO/bootstrap-проверками, `hunt.py` — ex-ante prefilter и OOS/multiple-testing discipline, а `research.py` собирает end-to-end skeptical audit.    

Я бы превратил ваши 10 пунктов в **Change Acceptance Scorecard**:

```text
Change must improve:
  speed
  cost
  simplicity
  result reliability
  reproducibility
  anti-bias / anti-reward-hacking
  auditability
  robustness
  safety of changes
  hypothesis quality
```

Но важно: не все пункты должны быть “оптимизируемыми”. Некоторые должны быть **hard gates**.

Например:

```text
HARD GATES:
  reproducibility
  no look-ahead
  no import-cycle
  vectorbt verification
  baseline regression tolerance
  deterministic seeds
  audit log exists

SOFT OBJECTIVES:
  speed
  cost
  simplicity
  hypothesis quality
  robustness margin
```

Иначе агент начнёт “улучшать” скорость ценой честности, или качество гипотез ценой reward hacking.

Практически я бы добавил файл вроде:

```text
SYSTEM_OBJECTIVES.yaml
```

с такой логикой:

```yaml
hard_gates:
  reproducible:
    required: true
    evidence:
      - code_hash
      - data_hash
      - config_hash
      - seed

  no_accounting_regression:
    required: true
    checks:
      - vectorbt_max_diff <= 1e-10
      - baseline_metric_drift <= tolerance

  no_selection_leakage:
    required: true
    checks:
      - trading_gate_uses_train_only
      - walk_forward_selection_reported

  auditability:
    required: true
    evidence:
      - experiment_id
      - hypothesis
      - code_diff
      - metrics_before
      - metrics_after
      - rejection_reason_or_acceptance_reason

soft_objectives:
  speed:
    direction: minimize_runtime
  cost:
    direction: minimize_data_and_compute_cost
  simplicity:
    direction: minimize_complexity
  robustness:
    direction: maximize_stability
  hypothesis_quality:
    direction: maximize_novel_valid_hypotheses
```

Для вашего night-loop я бы сделал итоговый вердикт изменения таким:

```text
ACCEPT:
  hard gates passed
  at least one soft objective improved
  no critical metric degraded
  experiment is logged

REJECT:
  any hard gate failed
  improvement only exists in full-sample
  improvement disappears OOS / WF
  result not reproducible
  change increases complexity without measured benefit

QUARANTINE:
  promising but unstable
  needs human review
  touches lib.py / accounting / data logic / gates
```

Особенно важный момент: **качество гипотез не должно измеряться только результатом**.

Хорошая гипотеза должна иметь:

```text
1. Economic reason
2. Expected failure mode
3. Minimal code change
4. Predefined evaluation
5. OOS / walk-forward check
6. Negative control
7. Clear rejection condition
```

Например, плохая гипотеза:

```text
Попробовать 200 разных z_win и выбрать лучший Sharpe.
```

Хорошая гипотеза:

```text
У dual-class пар с устойчивой voting/control discount mean reversion должна быть выше
после corporate-event фильтра. Проверка: train-only classification, OOS Sharpe,
delay decay, cost ladder, random-direction control, DSR adjustment.
```

Итоговая формулировка для системы могла бы быть такой:

```text
The system is not allowed to maximize trading performance directly.

It must improve the research process by proposing hypotheses and changes that
increase speed, reduce cost, simplify the stack, improve reliability,
reproducibility, robustness, auditability, and safety, while reducing bias and
reward hacking.

Every accepted change must pass hard safety gates and produce an auditable
before/after report.
```

Я бы поставил это как **верхний invariant** для ночного агента:

> Агент не оптимизирует Sharpe. Агент оптимизирует доверие к исследовательскому процессу.
