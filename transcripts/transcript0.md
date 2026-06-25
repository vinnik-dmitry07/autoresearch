# Дурак стратегия без памяти
_Exported on 6/22/2026 at 16:13:10 PDT from Cursor (3.7.42)_

---

**User**

@program.md @README.md Существует карточная игра Дурак. Это игра с неполной информацией. Одна из стратегий это запоминание вышедших в отбой карт. Но я хочу сделать стратегию которая не будет пользоваться памятью. Вместо этого она будет делать вывод только исходя и карт в руке и карт на столе. Примеры эвристик: на каждом шаге использовать минимальную некозырную карту, если есть пара или тройка карт не сильно большего номинала, то использовать их вместо минимальной; если на тебя нападают, но у тебя нет карт выше той же масти, но есть несколько козырных карт, то предпочитать козырную карту того же номинала что и атакующая тебя, ведь это делает невозможным противнику подбросить новый номанал; если противник атакует хорошими парами или тройками и среди них есть дефицитные масти, то лучше забрать пары, ведь от пар легко избавится.

В игре будет два игрока. Игра должна симулироваться на ультраэфективном движке написаном на высокоуровневом C++23. Симуляции между новой и старой стратегией должны продолжаться пока не станет очевидно что одна из них доминирует. Эвристики должны быть минимальными и следовать бритве Оккама. Между двумя стратегиями с приблизительно одинаковыми результатами предпочитай ту у которой меньше эвристик. 

---

**Cursor**

Изучаю проект и существующую архитектуру перед планом.


Репозиторий сейчас — LLM autoresearch; кода Дурака нет. Нужны уточнения по правилам и структуре проекта.


**Уточнения по Дураку**

> **Какой вариант правил Дурака симулировать?**
> - Подкидной, 36 карт, 6 в руке, 2 игрока, подкидывание по номиналу (стандарт) ✔
> - Подкидной, 52 карты
> - Переводной (с возможностью перевода)
> - Другой вариант — опишу в чате

> **Как разместить проект в репозитории?**
> - Подпроект durak/ (train.py и LLM остаются)
> - Заменить LLM autoresearch на Durak autoresearch (новый program.md) ✔
> - Отдельный минимальный репо только для Durak

Уточнения получены. Формирую план замены LLM autoresearch на симулятор подкидного Дурака.


---

**User**

План в целом **сильный и правильный по направлению**, но я бы поправил несколько вещей до реализации. Главная идея хорошая: сделать не LLM-игрушку, а **экспериментальную лабораторию** для сравнения стратегий Дурака, где “память vs no-memory” проверяется миллионами партий и простота стратегии является частью objective.

Мой главный вывод: **как research-план — да; как текущая спецификация движка — ещё слишком много неоднозначностей правил и статистических ловушек.**

## Что в плане особенно хорошо

Первое: ты правильно отделяешь три слоя:

**движок правил** — фиксированный;
**baseline с памятью** — фиксированный;
**no-memory эвристика** — единственный редактируемый файл.

Это критично. Иначе агент начнёт “побеждать” через изменение правил, симулятора, условия остановки или baseline.

Второе: идея Occam-критерия очень хорошая. Для такой задачи это даже важнее, чем +0.2% win rate. Если две no-memory стратегии почти равны, надо выбирать ту, где меньше условий, меньше параметров и меньше специальных случаев.

Третье: 2 игрока, 36 карт, подкидной Дурак — правильная первая постановка. Переводить сразу в 3–6 игроков было бы ошибкой: там память, коалиционность и порядок подкидывания резко усложняют интерпретацию.

## Главная проблема: правила Дурака надо зафиксировать намного жёстче

Сейчас в правилах есть несколько мест, где движок может стать “не тем Дураком”, и стратегия начнёт оптимизироваться под артефакт.

Самое важное: фраза

> атакующий подкидывает только карты уже присутствующих на столе номиналов, не больше числа неотбитых атак

выглядит неверно или как минимум неоднозначно.

В подкидном Дураке обычно можно подкидывать карты номиналов, которые уже есть на столе, включая уже побитые карты. То есть если защитник побил 7♣ картой 9♣, на столе уже есть номиналы 7 и 9, и атакующий может подкинуть семёрку или девятку, если есть лимит. Подкидывание не должно зависеть только от числа **неотбитых** атак.

Лучше формализовать так:

**В течение боя атакующий может добавлять карты только тех рангов, которые уже присутствуют среди атакующих или защитных карт на столе. Общее число атакующих карт в бою не может превышать число карт в руке защитника на начало боя, а также выбранный лимит варианта, например 6.**

Ещё надо явно решить:

Кто ходит первым в первой партии: обладатель младшего козыря или случайный игрок?
Можно ли первым ходом атаковать несколькими картами одного ранга?
Лимит атаки — 6 карт или размер руки защитника на начало боя?
Если защитник берёт, кто ходит следующим? Обычно тот же атакующий.
Если защита успешна, ход переходит защитнику.
Что происходит, если оба игрока потенциально заканчивают карты после боя? Возможна ли ничья или всегда один победитель?
Добор: сначала атакующий, потом защитник — но если защитник взял, порядок добора всё равно надо явно зафиксировать.

Без этого autoresearch будет искать “дырки” не в стратегии, а в варианте правил.

## Вторая проблема: baseline с памятью сейчас описан немного нестрого

Вот это место надо поправить:

> unknown = 36 − known − карты оппонента

Идентичности карт оппонента неизвестны, можно знать только **размер руки оппонента**, но не множество карт. Поэтому нельзя буквально вычитать “карты оппонента”.

Корректнее:

**known_cards = своя рука + карты на столе + отбой + все карты, которые были видимы и не могли вернуться в скрытую зону. unknown_pool = 36 − known_cards. Из unknown_pool часть находится в руке оппонента, часть в колоде.**

Но есть тонкость: карты, которые были на столе и потом взяты защитником, становятся известными картами в руке защитника. Если потом этот игрок использует часть из них, память должна обновляться. То есть baseline с памятью — это не просто “отбой”, а belief-state tracker.

Для первой версии я бы сделал baseline проще и честнее:

**mem-strategy знает только отбой и ранее открытые карты, которые гарантированно не находятся в колоде. Она не пытается идеально реконструировать руку оппонента.**

Иначе ты быстро уйдёшь из “минимальный card counting” в полноценный hidden-state inference engine.

## Третья проблема: no-memory может почти наверняка проигрывать сильному mem-baseline

Это не значит, что идея плохая. Но цель “nopmem win_rate > 0.50 против mem” может быть слишком жёсткой, если baseline действительно использует память качественно.

Важный момент: no-memory стратегия может быть **лучше простой memory-strategy**, если baseline плохо использует память. Но если baseline хорошо считает вышедшие карты, особенно в late game, no-memory будет структурно слабее.

Поэтому я бы сделал три baseline-уровня:

**B0 random-legal** — sanity check.
**B1 simple no-memory** — минимальная карта / минимальная защита.
**B2 memory-counting** — настоящий целевой baseline.

Тогда прогресс стратегии будет виден даже если B2 непобедим:

сначала beat B0, потом beat B1, потом максимально приблизиться к B2.

Иначе агент может 100 итераций видеть только `ci_high < 0.50`, и ты не поймёшь, улучшает ли он что-то реально.

## Четвёртая проблема: Wilson CI при постоянном peeking даёт слишком оптимистичный сигнал

Если после каждого batch проверять:

```text
ci_low > 0.50
```

то это уже не обычный фиксированный тест. Это sequential testing. Чем чаще смотришь, тем выше шанс случайно пересечь границу.

Лучше один из вариантов:

**Вариант простой:** фиксировать заранее число игр, например 1M, 5M, 20M, и только потом смотреть CI.

**Вариант лучше:** использовать sequential probability ratio test или always-valid confidence sequence.

**Вариант практичный:** оставить batch progress, но статус `keep` давать только после фиксированного checkpoint: 100k, 500k, 1M, 5M. Не останавливаться на первом пересечении CI, если это не always-valid тест.

Для autoresearch я бы сделал так:

```text
quick_eval: 100k games
full_eval: 5M games
keep only if full_eval lower CI > previous_best + margin
```

А не просто `ci_low > 0.50`.

## Пятая проблема: надо использовать paired evaluation

Обычная оценка “mem против nopmem на случайных партиях” будет шумной.

Лучше для каждого seed делать две партии:

```text
seed S:
  game A: nopmem = player 0, mem = player 1
  game B: mem = player 0, nopmem = player 1
```

С одной и той же перетасовкой или симметричной парой раздач. Тогда ты сильно уменьшаешь дисперсию от “кому повезло с картами / козырем / первым ходом”.

Результат лучше считать не просто как win rate отдельных игр, а как paired score:

```text
+1 если nopmem выиграл больше партий в паре
 0 если split 1:1
-1 если mem выиграл больше партий в паре
```

Это даст более честную оценку превосходства стратегии, особенно если первый ход или козырь создают перекос.

## По скорости: `std::bitset<36>` нормально, но не максимум

Если цель реально “ультраэффективный движок”, я бы вместо `std::bitset<36>` использовал:

```cpp
using CardMask = uint64_t;
```

36 карт идеально помещаются в 64 бита. Тогда:

```cpp
hand & trump_mask
hand & rank_mask[rank]
std::countr_zero(mask)
mask &= mask - 1
```

Это будет проще, быстрее и прозрачнее для hot path.

`std::bitset<36>` удобен, но `uint64_t` лучше для симулятора на миллионы партий. Особенно если ты хочешь, чтобы агент мог быстро прогонять много вариантов.

Я бы сделал так:

```cpp
using Card = uint8_t;
using CardMask = uint64_t;

constexpr CardMask card_bit(Card c) {
    return 1ull << c;
}
```

И отдельно `rank_mask[9]`, `suit_mask[4]`, `trump_mask`.

## H1–H4 хорошие, но H4 опасная

H1–H3 выглядят разумно.

H1: минимальная некозырная карта — нормальный base prior.
H2: пара/тройка вместо одиночной, если не сильно дороже — хорошая эвристика сброса массы.
H3: козырь того же номинала, чтобы заблокировать подкидывание ранга — интересная и локально умная эвристика.

А вот H4:

> если противник атакует парами/тройками и среди них есть дефицитные масти, лучше забрать пары

Это может быть как сильной эвристикой, так и ловушкой. “Взять пары, потому что от пар легко избавиться” верно не всегда. В 2-player Дураке взять 4–6 карт может быть катастрофой, если колода ещё большая и ты теряешь темп.

Я бы H4 сделал не стартовым правилом, а экспериментальным флагом:

```text
H4_take_pairs_when_defense_expensive
```

И применял только если защита требует козырей или старших карт, а взятые карты образуют хорошие будущие группы.

То есть не “пара/тройка → беру”, а:

```text
беру, если стоимость защиты выше стоимости взятия
```

Но это уже усложнение. Для Occam v1 можно оставить H4, но я бы ожидал, что агент часто будет его удалять или ограничивать.

## Что я бы изменил в порядке реализации

Я бы не начинал сразу с `strategy_mem`. Сначала надо получить идеально проверенный engine.

Лучший порядок:

1. `cards.hpp` на `uint64_t`, rank/suit/trump helpers.
2. Минимальный deterministic engine.
3. Golden tests на правила.
4. `strategy_random_legal`.
5. `strategy_basic_nomem`.
6. `simulate` с paired seeds.
7. Только потом `strategy_mem`.
8. Потом уже `strategy_heuristic`.

Почему: если сразу писать mem и heuristic, ты не поймёшь, кто виноват — движок, baseline, статистика или эвристика.

## Что обязательно добавить в `program.md`

Я бы добавил жёсткие запреты для агента:

```text
Agent may edit only durak/src/strategy_heuristic.cpp.
Agent must not change engine, simulator, RNG, baseline, tests, CMake flags, or stopping criteria.
Agent must not use static/global state to remember previous turns, cards, seeds, games, or opponent actions.
Agent must not infer hidden history through simulator artifacts.
Agent must not add I/O, files, networking, clock access, or randomness inside strategy_heuristic.cpp.
```

Особенно важно запретить `static` state. Иначе “no-memory” стратегия может случайно или намеренно стать memory-strategy через глобальные переменные.

Для C++ это критично:

```cpp
static std::array<int, 36> seen_cards;
```

— и всё, эксперимент сломан.

Нужно API сделать таким, чтобы strategy получает только `HandView`, а не `GameState`.

## Что добавить в README

README должен сразу отвечать на три вопроса:

1. **Что проверяем?**
   Может ли стратегия без памяти конкурировать со стратегией с card-counting memory в 2-player подкидном Дураке?

2. **Почему это интересно?**
   Потому что это тест локальных эвристик против belief-state inference в игре с неполной информацией.

3. **Что считается победой?**
   Не только win rate, но и простота стратегии: меньше правил при равном результате.

Я бы отдельно написал:

```text
This project is not trying to solve Durak globally.
It tests whether a memoryless local heuristic policy can approach or beat a fixed memory-based baseline under a locked rules engine.
```

Это защитит проект от ложного обещания “мы решили Дурака”.

## Мой итоговый вердикт

План хороший, но я бы переформулировал цель чуть честнее:

Не:

```text
найти no-memory стратегию, которая доминирует memory baseline
```

А:

```text
построить честный быстрый движок и измерить, насколько далеко минимальные no-memory эвристики могут дойти против фиксированных baseline-уровней, включая memory-counting.
```

Если no-memory реально пробьёт `>50%` против memory baseline — это будет сильный результат. Но даже если она дойдёт до 47–49% с 4–6 простыми правилами, это тоже может быть интересным результатом: значит большая часть силы в 2-player Дураке идёт не из памяти, а из локальной структуры руки/стола.

Главные правки перед запуском:

1. Жёстче зафиксировать правила подкидывания и лимиты атаки.
2. Заменить `std::bitset<36>` на `uint64_t`, если нужна максимальная скорость.
3. Сделать paired evaluation по seed/side.
4. Не использовать обычный Wilson CI как early stopping при постоянном peeking.
5. Добавить baseline ladder: random → basic no-memory → memory.
6. Запретить `static/global` state в no-memory стратегии.
7. Сначала довести engine тестами, потом писать autoresearch loop.

В таком виде проект становится намного более научным: не “агент хакает Дурака”, а маленькая лаборатория для проверки гипотезы **local heuristics vs memory in imperfect-information card play**.
Да, я с этой критикой почти полностью согласен. Это не “придирки”, а именно те места, где эксперимент может дать красивое число, но слабый вывод.

Самое важное исправление: **не ставить `nopmem > mem` как единственный критерий успеха**. Лучше разделить цель на две оси:

**1. Engineering goal:** построить быстрый, воспроизводимый, закрытый движок Дурака.
**2. Research goal:** измерить силу простых локальных эвристик без памяти относительно нескольких фиксированных ориентиров.

Я бы переписал экспериментальную схему так:

```text
B0: random legal strategy
B1: basic no-memory strategy
B2: heuristic no-memory strategy
B3: same heuristic logic + memory ablation
B4: independent stronger memory baseline
```

Тогда получаются разные выводы:

```text
B2 > B1  => эвристики реально добавляют силу
B3 > B2  => чистая ценность памяти при той же логике
B2 ~ B3  => память мало помогает именно этой логике
B2 > B4  => сильный результат: простая no-memory стратегия бьёт memory baseline
B2 < B4  => не провал, если B2 всё равно простая и сильная
```

Вот это гораздо научнее, чем один матч `nopmem vs mem`.

## Что я бы поменял в плане

Главная формулировка цели должна стать такой:

```text
Найти минимальную по числу правил стратегию без памяти, которая максимизирует win_rate против фиксированных baseline-уровней, и отдельно измерить вклад памяти через ablation: та же логика с памятью vs та же логика без памяти.
```

А не:

```text
Найти no-memory стратегию, которая обязательно доминирует memory baseline.
```

Потому что вторая цель может быть просто недостижима, если memory baseline написан грамотно.

## Самая важная архитектурная правка

Нужно добавить не одну `strategy_mem.cpp`, а два memory-слоя:

```text
strategy_heuristic.cpp
strategy_heuristic_mem.cpp
strategy_mem.cpp
```

Где:

`strategy_heuristic.cpp` — редактируемая no-memory стратегия.

`strategy_heuristic_mem.cpp` — та же стратегия, но с доступом к `MemoryView`. Этот файл не обязательно должен редактироваться агентом на первом этапе; можно автогенерировать или писать вручную как ablation-copy.

`strategy_mem.cpp` — отдельный сильный baseline с памятью, как sparring partner.

Иначе ты не узнаешь, что именно сработало: локальная логика или память.

## Правила движка надо зафиксировать вот так

Я бы явно записал в `program.md`:

```text
Variant: 2-player podkidnoy Durak, no transfer.

Attack limit:
Total number of attack cards in a battle must be <= min(6, defender_hand_size_at_battle_start).

Throw-in legality:
A card may be thrown in if its rank is already present among any table card in the current battle, including both attack and defense cards.

Turn transition:
If defense succeeds, all table cards go to discard and the defender becomes the next attacker.
If defender takes, defender takes all table cards and skips the next attack; the same attacker attacks again.

Draw order:
After each battle, players draw up to 6 from the deck. The attacker draws first, then the defender, using the roles from the battle that just ended.

No transfer:
Defender may only defend or take. There is no perevod / transfer move.

Draws:
If both players empty their hands after the deck is exhausted in the same battle, count the game as 0.5 win for each side.
```

Особенно важно: **H3 имеет смысл только если защитная карта тоже открывает номинал для подкидывания**. Если движок это не реализует, правило “бить козырем того же номинала” становится почти бессмысленным.

## Статистику я бы сделал проще, но честнее

Для первой версии не обязательно сразу городить Howard confidence sequences. Можно сделать практичный двухэтапный протокол:

```text
quick_eval: 100k paired deals
full_eval: 5M paired deals
```

А решение `keep/discard` принимать только на `full_eval`.

И критерий сделать не “просто выше 50%”, а с practical effect size:

```text
keep_vs_current_best if:
  win_rate_full >= best_win_rate + 0.005
  and lower_ci >= best_lower_ci
```

Для claims типа “доминирует memory baseline”:

```text
dominates if:
  lower_ci > 0.52
```

А не `lower_ci > 0.50`.

И обязательно paired evaluation:

```text
for each deal_seed:
  game A: heuristic player 0, baseline player 1
  game B: baseline player 0, heuristic player 1
```

Так ты убираешь перекос от первого хода, козыря и конкретной раздачи.

## Occam-критерий надо сделать не по `if`, а по manifest

Идея считать `if`-блоки сломается сразу. Агент может засунуть всё в один огромный `if`.

Лучше заставить стратегию явно объявлять правила:

```cpp
constexpr int kHeuristicCount = 4;
constexpr int kParameterCount = 2;
constexpr int kComplexityScore = 100 * kHeuristicCount + 10 * kParameterCount;
```

И в `strategy_heuristic.cpp` держать manifest:

```cpp
// HEURISTICS:
// H1 min_non_trump_attack
// H2 near_rank_group_attack delta=2
// H3 same_rank_trump_defense
// H4 take_expensive_pair_attack scarce_suit_threshold=1
```

Тогда агент может менять правила, но обязан обновлять complexity score. Да, это тоже можно геймить, но уже проще ловить ревью и тестами.

Ещё лучше: `simulate` печатает `strategy_name`, `heuristic_count`, `parameter_count`, `complexity_score`, которые возвращаются из стратегии через API.

## Минимальный набор sanity tests

Я бы добавил это как обязательный этап до autoresearch:

```text
engine_tests:
- legal defense: same suit higher beats, same suit lower fails
- trump beats non-trump
- non-trump cannot beat trump
- throw-in rank can match attack card rank
- throw-in rank can match defense card rank
- total attack cards <= min(6, defender_initial_hand_size)
- successful defense passes attack turn to defender
- take keeps attack turn with same attacker
- draw order attacker first, defender second
- simultaneous empty hands after deck exhaustion => draw

simulation_tests:
- random vs random with side pairing ~= 50%
- basic vs random wins clearly
- heuristic self-play paired ~= 50%
- mem self-play paired ~= 50%
- deterministic seed reproduces exact game
- no-memory strategy cannot use static/global state
```

Последний пункт сложный, но важный. Хотя бы grep/static check:

```text
forbidden in strategy_heuristic.cpp:
static
global mutable state
fstream
random_device
chrono
thread
filesystem
```

## Мой итог

Критика абсолютно по делу. Я бы принял её как изменение дизайна.

Финальная версия проекта должна быть не:

```text
memory baseline vs no-memory challenger
```

а:

```text
locked Durak engine + baseline ladder + no-memory heuristic search + memory ablation
```

Тогда даже если no-memory никогда не пробьёт сильный memory baseline, результат всё равно будет содержательным. Ты сможешь сказать:

```text
Простая стратегия без памяти с N правилами достигает X% против basic no-memory,
Y% против той же логики с памятью,
Z% против независимого memory-counting baseline.
Чистая ценность памяти в этой постановке ≈ Y - X.
```

Это уже нормальный исследовательский результат, а не просто “агент проиграл/выиграл у одного бота”.




---

**Cursor**

Обновляю план с учётом вашей критики: читаю текущий документ и вношу правки.


План обновлён в [.cursor/plans/durak_c++_autoresearch_adddc0bd.plan.md](d:\Projects\autoresearch\.cursor\plans\durak_c++_autoresearch_adddc0bd.plan.md). Кратко, что изменилось:

### Цель
Не «nopmem обязана побить mem», а **две оси**: закрытый движок + измерение силы простых локальных эвристик против **ladder B0–B4** и **ablation B2 vs B3** (чистая ценность памяти ≈ разница win rates).

### Правила (зафиксированы жёстко)
- Подкидывание по рангам **всех** карт на столе (атака + защита); лимит `min(6, рука защитника на старте боя)`.
- Бито → защитник атакует; беру → **тот же** атакующий.
- Добор: атакующий первым; ничья 0.5 при совместном опустошении рук.
- Первый ход: младший козырь; без перевода.

### Архитектура стратегий
- **B0** random, **B1** basic nomem, **B2** `strategy_heuristic.cpp` (агент), **B3** `strategy_heuristic_mem.cpp` (ablation), **B4** `strategy_mem.cpp` (сильный baseline).
- API: только `HandView` / `MemoryView`, не полный `GameState`.
- Memory: `known_out_of_play` и `unknown_pool`, без вычитания «карт оппонента».

### Данные и скорость
- `uint64_t CardMask` вместо `bitset<36>`.

### H4
- Убран из v1; H1–H3 в стартовом manifest. H4 — экспериментальный `take_when_defense_expensive`.

### Статистика
- **Paired evaluation** по seed (swap сторон).
- `quick_eval` 100k / `full_eval` 5M — **keep только на full_eval**.
- Без early stopping по Wilson при peeking.
- `keep`: `win_rate ≥ best + 0.005` и `lower_ci ≥ best_lower_ci`; **dominates**: `lower_ci > 0.52`.

### Occam
- Manifest + `kComplexityScore`, не подсчёт `if`; grep на `static`/I/O/RNG в heuristic файле.

### Порядок реализации
- Сначала engine + golden tests → B0/B1 → simulate paired → simulation_tests → B2 → B3 → B4 → docs.

Todos в плане пересобраны по этому порядку. Когда будете готовы к реализации — скажите «execute» / «начинай».

---

**User**

Да — эта версия **на порядок лучше предыдущей**. Теперь это уже не “mem vs nopmem и надеемся на чудо”, а нормальная лаборатория: locked engine, baseline ladder, ablation, paired eval, Occam через manifest, отдельное framing “не решить Дурака глобально”. Это правильная архитектура. 

Но я вижу **4 места, которые ещё надо поправить**, иначе потом агент или статистика снова начнут давать мутный сигнал.

## 1. B3 “та же логика что B2 + MemoryView” — пока недоопределено

Это главный оставшийся концептуальный риск.

Ты пишешь:

> B3 — `strategy_heuristic_mem.cpp`: копия логики B2 + MemoryView, фиксированный файл, не редактируется агентом.

Но если агент меняет B2, то B3 уже **не является той же логикой**. Через 10 итераций B2 ушёл, а B3 остался копией старой версии. Тогда ablation снова смешивает две переменные.

Лучшее решение:

```text
B2 = editable no-memory heuristic
B3 = current B2 logic wrapped with MemoryView features, generated or manually synchronized per accepted candidate
```

Или проще для v1:

```text
B3 используется только для final analysis accepted candidate, а не в каждом autoresearch step.
```

То есть autoresearch оптимизирует B2 против B1/B4, а после `keep` ты делаешь отдельный ablation:

```text
accepted B2
accepted B2 + memory hooks
compare B3 vs B2
```

Иначе “чистая ценность памяти” будет фикцией.

## 2. Формула “ценность памяти” через win_rate разности сомнительна

В плане:

```text
memory value ≈ win_rate(B3 vs B1) − win_rate(B2 vs B1)
```

Это лучше, чем ничего, но это не идеально, потому что win rate против третьего оппонента не обязательно линейно отражает силу.

Чище:

```text
Primary memory ablation:
B3 vs B2 directly, paired eval, same seeds.
```

А `B3 vs B1` и `B2 vs B1` оставить как дополнительную ladder-метрику.

То есть лучше написать:

```text
Чистая ценность памяти:
primary = paired score(B3 vs B2)
secondary = win_rate(B3 vs B1) − win_rate(B2 vs B1)
```

## 3. Paired score сейчас теряет информацию

Ты определяешь:

```text
+1 challenger выиграл больше игр в паре
0 split
-1 opponent выиграл больше
paired_win_rate = mean(paired_score > 0)
```

Так split становится просто “не win”, и результат может исказиться. Лучше считать очки:

```text
game win = 1
draw = 0.5
loss = 0

pair_score = challenger_points / 2
paired_win_rate = mean(pair_score)
```

Тогда:

```text
2-0 => 1.0
1.5-0.5 => 0.75
1-1 => 0.5
0.5-1.5 => 0.25
0-2 => 0.0
```

Это сохраняет информацию о ничьих и split-парах. Для CI лучше bootstrap по seeds или Wilson только если ты бинаризуешь pair outcomes. Wilson для дробных pair scores уже не совсем корректен.

Практичный вариант:

```text
report:
- point_rate = mean(pair_score)
- pair_win_rate = P(pair_score > 0.5)
- pair_loss_rate = P(pair_score < 0.5)
- split_rate = P(pair_score == 0.5)
```

А primary metric сделать `point_rate`.

## 4. “Одна и та же перетасовка” надо формализовать

Фраза:

```text
game A: challenger player 0
game B: challenger player 1
```

хорошая, но “одна и та же перетасовка” может быть реализована по-разному.

Нужно явно:

```text
For seed S, generate one deck order D.
Game A: deal D normally: player0 gets positions assigned to player0, player1 gets positions assigned to player1.
Game B: use the same D, but swap strategy assignment to seats, not cards.
```

Или наоборот:

```text
Game B swaps seats and card ownership symmetrically.
```

Это разные эксперименты. Я бы выбрал **swap strategies, same seats/cards**, потому что ты хочешь усреднить преимущество стратегии от seat assignment, а не создавать новую раздачу. Но надо быть аккуратным с правилом “младший козырь ходит первым”: seat advantage может быть меньше, чем hand advantage.

Ещё лучше:

```text
For seed S:
A: challenger controls hand0, opponent hand1
B: challenger controls hand1, opponent hand0
same deck, same trump
```

Вот это настоящая paired symmetry.

## Мелкая, но важная правка по MemoryView

Сейчас:

```cpp
CardMask known_out_of_play;
CardMask hand;
CardMask table;
```

Название `known_out_of_play` конфликтует с фразой:

> карты взятые со стола — известны как в руке того, кто взял

Если карта известна как находящаяся в руке оппонента, она **не out_of_play**. Лучше разделить:

```cpp
CardMask known_discarded;
CardMask known_in_own_hand;
CardMask known_on_table;
CardMask known_in_opponent_hand;
CardMask seen_ever;
```

И потом:

```cpp
unknown_cards = ALL_CARDS
              - known_discarded
              - known_in_own_hand
              - known_on_table
              - known_in_opponent_hand;
```

Если не хочешь tracking known opponent hand, тогда честно убрать это из B4:

```text
B4 tracks discard/table only, not known opponent hand after take.
```

Но смешивать “out_of_play” и “known but in opponent hand” нельзя.

## Итоговый вердикт

Я бы этот план **принимал**, но с четырьмя патчами перед реализацией:

```text
1. B3 ablation синхронизировать с текущим B2 или запускать только post-keep.
2. Primary memory value = direct B3 vs B2, not only delta vs B1.
3. Primary paired metric = point_rate по seed-pairs, а не mean(score > 0).
4. MemoryView разделить на discarded / own / table / known opponent, либо упростить честно.
```

После этих правок это уже очень хорошая спецификация. Особенно нравится, что H4 отключён в v1: это правильный Occam-ход. Начинать с H1–H3 намного чище, а “беру дорогую пару” пусть доказывает свою полезность в цикле.


---

**Cursor**

Вношу четыре патчи в план.


Все четыре патчи внесены в план. Кратко по изменениям:

### 1. B3 ablation — post-keep only
Autoresearch loop: **B2 vs B0 / B1 / B4** только. B3 не в hot path. После `keep` — `simulate --ablate`: синхронизация accepted B2 → B3 + paired eval **B3 vs B2**. Агент не редактирует B3.

### 2. Ценность памяти
- **Primary:** `point_rate(B3 vs B2)` direct paired eval  
- **Secondary:** `win_rate(B3 vs B1) − win_rate(B2 vs B1)` — ladder, не substitute

### 3. Paired scoring
- Игры: win=1, draw=0.5, loss=0  
- `pair_score = (points_A + points_B) / 2`  
- **Primary metric:** `point_rate = mean(pair_score)`  
- Дополнительно: `pair_win_rate`, `pair_loss_rate`, `split_rate`  
- CI: **bootstrap по seeds** для `point_rate`; Wilson только для бинарного `pair_win_rate`

### 4. Deck symmetry
Один deck `D` из seed → фиксированные `hand0`/`hand1`. Game A: challenger на seat0; Game B: **swap strategies**, same cards/trump.

### MemoryView
Разделено: `known_discarded`, `known_in_own_hand`, `known_on_table`, `known_in_opponent_hand`, `seen_ever`. `unknown_cards` = ALL − union известных зон. B4 обновляет `known_in_opponent_hand` при взятии с стола.

План готов к реализации. Для старта — «execute» / «начинай».

---

**User**

Да, эта версия уже **почти финальная**. Она закрыла главные дыры: B3 вынесен из hot loop, ablation стал post-keep, `point_rate` заменил бинарный paired win, Wilson убран для дробной метрики, MemoryView разделён корректно, paired deck symmetry формализована. Это уже можно давать агенту как рабочую спецификацию. 

Осталось не архитектурное, а **исполнительное**: как именно сделать B3 “той же логикой + памятью”.

## Главный оставшийся риск: B3 auto-sync может быть фикцией

В плане написано:

```text
ablate harness — sync B2→B3 + B3 vs B2 eval
```

Но если `strategy_heuristic.cpp` — произвольный C++ файл, то “автоматически взять ту же логику и добавить MemoryView” почти невозможно без хрупкого codegen. Агент может переписать B2 так, что harness не сможет корректно синхронизировать B3.

Я бы заменил это на более жёсткий контракт:

```text
B2 must implement a pure policy core that consumes LocalFeatures.
B3 uses the same policy core, but LocalFeatures is extended with MemoryFeatures.
The no-memory version receives neutral/default memory features.
```

То есть не “копировать C++”, а заранее спроектировать интерфейс:

```cpp
struct LocalFeatures {
    CardMask hand;
    CardMask table_attack;
    CardMask table_defense;
    Card trump_card;
    int deck_count;
    int opponent_hand_count;
};

struct MemoryFeatures {
    CardMask unknown_cards;
    int unknown_trump_count;
    int unknown_rank_count[9];
    int known_opponent_rank_count[9];
};

Move choose_move_core(
    const LocalFeatures& local,
    const MemoryFeatures* memory
);
```

Тогда:

```text
B2 calls choose_move_core(local, nullptr)
B3 calls choose_move_core(local, &memory)
```

И ablation становится честным: одна policy core, разные доступные features.

## Второй риск: B3 может добавить не “память”, а новую стратегию

Даже если B3 post-keep, важно ограничить, что именно считается memory hook. Иначе B3 может получить не только память, но и новые эвристики.

Я бы записал:

```text
B3 may only use MemoryView for tie-breaks or replacing unknown-card priors.
B3 must not add new action classes that B2 does not consider.
B3 must preserve the same heuristic manifest plus memory_parameter_count.
```

Например допустимо:

```text
B2: выбирает минимальную некозырную карту
B3: среди равных минимальных некозырных выбирает ту, чей ранг чаще остался в unknown_pool
```

Недопустимо:

```text
B3: добавляет новую эвристику take/defend/throw-in, которой нет в B2
```

Иначе `B3 > B2` уже не чистая ценность памяти.

## Третья правка: primary loop не должен быть только B2 vs B4

Сейчас:

```text
Primary metric в loop: B2 vs B4 full_eval point_rate
```

Это нормально для финального claim, но для autoresearch может быть слишком жёстко. Если B4 сильный, все варианты будут сидеть в узком диапазоне 0.35–0.45, и агенту будет труднее понять локальный прогресс.

Я бы сделал primary score составным, но финальный claim оставить B4:

```text
search_score =
  0.50 * point_rate(B2 vs B4)
+ 0.30 * point_rate(B2 vs B1)
+ 0.20 * point_rate(B2 vs B0)
- complexity_penalty
```

А в README/program.md написать:

```text
B4 is the primary benchmark for reporting.
Composite ladder score is used only to stabilize search.
```

Если хочешь максимальную простоту — оставь как есть. Но practically ladder-score даст агенту более гладкий градиент.

## Четвёртая правка: bootstrap на 5M seeds может быть лишним

Bootstrap по 5M seeds × 1000 resamples может стать тяжелее самой симуляции, если делать наивно. Для `point_rate` с bounded scores `{0, 0.25, 0.5, 0.75, 1}` можно проще:

```text
mean ± 1.96 * std(pair_score) / sqrt(n)
```

А bootstrap оставить опциональным:

```text
--ci normal
--ci bootstrap
```

Для 5M paired seeds normal CI будет практически неотличим и намного быстрее.

## Что я бы поменял в тексте минимально

В `simulate-stats` todo:

```text
simulate: paired deck symmetry, point_rate + normal/optional bootstrap CI, quick/full eval
```

В B3 section:

```text
B3 is not generated from arbitrary C++.
B2 must expose a pure policy core. B3 reuses the same core with MemoryFeatures enabled.
Memory hooks may only affect tie-breaks / priors, not add new heuristic classes.
```

В метриках:

```text
Primary reporting metric: B2 vs B4 point_rate.
Optional search metric: ladder_score across B0/B1/B4.
```

## Итог

Я бы запускал реализацию после одного патча: **зафиксировать B2/B3 shared-core interface**. Без этого B3-ablation — красивый пункт в документе, но тяжёлый в исполнении.

После этой правки план выглядит очень зрелым:

```text
locked rules engine
deterministic paired evaluation
point scoring
baseline ladder
post-keep memory ablation
Occam complexity
forbidden-state checks
```

Это уже не просто “написать стратегию Дурака”, а нормальная экспериментальная система для проверки: сколько силы дают локальные эвристики, а сколько — память.


---

**Cursor**

Вношу финальные исполнительные правки в план: shared-core interface, ограничения B3, ladder score и CI.


Финальные исполнительные правки внесены. Ключевые изменения:

### Shared policy core (главный патч)
- Фиксированный [`policy_core.hpp`](../durak/include/policy_core.hpp): `LocalFeatures`, `MemoryFeatures`, `choose_move_core(local, memory*, legal)`.
- **B2** реализует core в `strategy_heuristic.cpp` (`memory == nullptr`).
- **B3** — фиксированный `strategy_heuristic_mem.cpp`: только wrapper + `MemoryFeatures`, вызывает **тот же** `choose_move_core(..., &memory)`.
- Никакого codegen/sync arbitrary C++.

### Контракт B3
- Memory только для tie-breaks / unknown priors.
- Нельзя добавлять новые action classes / эвристики только в memory branch.
- Тот же heuristic manifest; отдельно только `memory_parameter_count`.

### Метрики
- **Reporting:** `point_rate(B2 vs B4)`.
- **Search (keep/discard):** `search_score = 0.50·B4 + 0.30·B1 + 0.20·B0 − complexity_penalty`.
- README/program: B4 для claims, ladder score для градиента поиска.

### CI
- Default: **normal** `mean ± 1.96·SE`.
- `--ci bootstrap` — опционально.

### Порядок реализации
`policy_core.hpp` → engine → B0/B1 → simulate → B2 (`choose_move_core`) → **B3 wrapper** → B4.

План готов к реализации. Для старта — «execute» / «начинай».

---

**User**

Implement the plan as specified, it is attached for your reference. Do NOT edit the plan file itself.

To-do's from the plan have already been created. Do not create them again. Mark them as in_progress as you work, starting with the first one. Don't stop until you have completed all the to-dos.

---

**Cursor**

I'll implement the plan. Let me set up the todos and start building the C++ engine.

Let me first check the build toolchain availability while I start writing files.

No compilers on PATH. Let me search for installed toolchains (Visual Studio, MinGW, LLVM) in common locations.

Visual Studio is at `D:\Programs\Microsoft_Visual_Studio`. Let me locate its bundled CMake, Ninja, and the developer environment script.

Found the VS toolchain. Now let me write all the source files. Starting with the core headers.

Now the engine implementation.

Now the strategies. First the two no-memory baselines B0 and B1.

Now the agent-editable heuristic core (B2). I must keep it free of forbidden tokens (no `static`, `chrono`, `thread`, `fstream`, `filesystem`, `random`).

Now the independent memory baseline B4.

Now the simulation harness.

Now the tests, the forbidden-symbol check, and the CMake build.

All source files are written. Let me create a Windows build helper that sets up the MSVC environment and uses the bundled CMake + Ninja, then run it.

Build succeeded. Now let me run the test suite.

The functional tests pass. The forbidden check tripped on the word "static" in a comment. Let me find all occurrences.

The only hit is the comment text. Let me reword it to avoid the literal token.

All tests pass. Let me update progress and run a quick speed/behavior check on the simulator.

The simulator works and the numbers are sensible: B2 is essentially neck-and-neck with the memory baseline B4 (0.491), strongly beats B1 (0.923) and B0 (0.960). Speed is ~65k games/s. Let me apply a couple of cheap performance wins before the full run — the biggest is that `LegalMoves` zero-initializes a 160-element array on every move generation.

Now let me avoid recomputing the table masks twice per decision by computing them once in `ask`.

Speed is now ~84k games/s. Good enough for the full run. Let me kick off the baseline full ladder evaluation in the background (5M paired seeds × 3 opponents ≈ 30M games) while I write the docs, and check the git state for the results row.

The shell is PowerShell. Let me run the git commands separately.

On `master` at `228791f`; `durak/` is untracked (I won't commit unless asked). Let me verify the baseline run started cleanly, then write the docs.

The output goes to `run.log`. Let me confirm progress there.

Running at ~125k games/s, B2 vs B4 holding at ~0.492. The full ladder will take ~4 minutes. Let me write the docs while it runs. First `program.md`.

Now the README with the research framing.

Docs are written. Let me check the baseline run progress.

B2 vs B4 finished at `point_rate=0.49211`. B1 and B0 are still running. Let me wait for the ladder to complete.

The run finished. Let me read the final ladder summary from the log.

Full baseline ladder is done. Let me also run the memory ablation (B3 vs B2) to complete the baseline picture, then I'll write `results.tsv`.

Ablation is exactly 0.50000 with a 100% split rate: with the v1 heuristics the memory tie-break never changes a decision (tied cards share a rank, hence the same unknown count), so memory adds nothing yet — an honest, measurable starting point and a clear target for the agent. The B3 wiring is confirmed correct (identical core, deterministic).

Let me write `results.tsv` and re-run the test suite (I changed `move.hpp`/`engine.cpp` after the last ctest).

All green. Let me check for any linter diagnostics on the new files and review the existing `.gitignore`.

The `.gitignore` already covers `build/` and `results.tsv`. Let me add the run logs so the autoresearch loop's output doesn't get committed.

Let me verify `results.tsv` is genuinely tab-separated and do a final end-to-end check of the `quick` eval path that the loop uses.

Everything works end to end. The `quick` path runs in ~1.3s per matchup, `results.tsv` is properly tab-separated. Let me mark the remaining todos complete.

All todos are complete. The Durak local-heuristics lab is built, tested, and the baseline is recorded.

## What was implemented

A C++23 engine and autoresearch harness under `durak/`, replacing the LLM loop's `program.md`/`README.md` while leaving the legacy Python files untouched.

**Locked engine** ([durak/src/engine.cpp](../durak/src/engine.cpp), [durak/include/cards.hpp](../durak/include/cards.hpp)) — 2-player podkidnoy, 36 cards, `uint64_t` card masks, deterministic seed-based shuffle. Throw-ins match any rank on the table (attack or defense), attack limit `min(6, defender hand at battle start)`, take keeps the attacker, bito passes the attack, attacker draws first, simultaneous-empty is a draw.

**Shared policy core** ([durak/include/policy_core.hpp](../durak/include/policy_core.hpp)) — the fixed `choose_move_core(local, memory*, legal)` signature. B2 calls it with `nullptr`; B3 calls the same function with memory enabled, so the ablation is honest by construction.

**Ladder** — B0 random, B1 basic, B2 the agent-editable heuristic (H1 min non-trump, H2 low group, H3 same-rank trump defense; manifest `complexity=310`), B3 fixed memory wrapper, B4 independent memory-counting baseline.

**Harness** ([durak/src/simulate.cpp](../durak/src/simulate.cpp)) — paired deck symmetry (swap strategies, same cards), `point_rate` with normal CI (bootstrap optional), `ladder`/`match`/`ablate`/`selfplay` modes, `search_score`, progress logging. Runs ~125–170k games/s.

**Tests** — golden engine tests, simulation sanity tests, and a `forbidden_check` CMake script that rejects `static`/IO/clock/RNG in the heuristic file. All pass.

## Baseline (5M paired seeds = 10M games each)

| Matchup | point_rate | 95% CI |
|---|---|---|
| B2 vs B4 (reporting) | 0.49211 | [0.49200, 0.49221] |
| B2 vs B1 | 0.92273 | [0.92258, 0.92288] |
| B2 vs B0 | 0.96087 | [0.96075, 0.96098] |
| B3 vs B2 (memory ablation) | 0.50000 | exact |

`search_score = 0.68404`, recorded in [results.tsv](../results.tsv).

Two notable findings: the three simple heuristics land essentially at parity with the memory-counting baseline (0.492, just shy of 50%), strongly beating the basic and random opponents. And the memory ablation is exactly 0.5 — with the v1 heuristics the memory tie-break never changes a decision (tied cards share a rank, so the unknown-count prior is identical), meaning memory contributes nothing yet. That is a clean, measurable starting point and an obvious target for the search loop.

To start the autonomous loop: `git checkout -b autoresearch/<tag>`, then iterate on [durak/src/strategy_heuristic.cpp](../durak/src/strategy_heuristic.cpp) per [program.md](../program.md). I did not commit anything (no request to).

