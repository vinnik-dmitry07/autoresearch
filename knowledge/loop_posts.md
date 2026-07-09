> **Design history — not a live verdict.** External methodology notes unrelated to frozen deployment verdicts.

# Loop Engineering instead of Prompt Engineering from the creators of Fable and Mythos 👍

While we wait for the little issues between Anthropic and officials to be resolved ([Anthropic access update](https://www.anthropic.com/news/fable-mythos-access)), let’s turn to something eternal: the methodology of loop engineering.

Alongside the release of the Mythos and Fable models themselves, the creators of Anthropic’s harness shared a new pattern for working with coding agents. They called it [**Loop Engineering**](https://x.com/RLanceMartin/article/2064397389189071163). It is presented as an evolution of Prompt Engineering, but it complements Context Engineering.

In reality, this is a similar concept to Karpathy-style approaches to agent self-improvement through feedback from the environment. Why does this work? If you remember, in the technical reports for R1 models, the DeepSeek team used RLVR for training ([discussion](https://t.me/dealerAI/1092)). The models are placed in an environment where the reward is obtained automatically, without external models. As an example of such an environment, they used a compiler. In other words, the language model was originally tuned with RL for this kind of behavior.

But let’s return to how this is natively embedded into a harness.

The approach has three pillars:

## 1. Self-correction loop

The model performs an action → receives feedback from the environment, for example the code failed tests → corrects itself → repeats the cycle until it satisfies the defined criterion, for example until all tests pass.

This is familiar and resembles the ReAct loop: receive a task, make a plan, take an action, evaluate what happened, adjust the plan, and repeat. But the authors again raise the problem with the ReAct approach: it can become an echo chamber, because the model is evaluating itself, and, as the authors themselves admit, models are bad at evaluating their own work; see overconfidence bias. 🚬

We have raised this topic more than once in this channel and have also turned to colleagues in the field ([related post](https://t.me/dealerAI/1775)). That is why they introduce both environment-based evaluations, such as compilers and unit tests, and subagents in the form of other evaluator models.

## 2. Memory

A module that allows knowledge to accumulate between stages and even between sessions, and then be reused in the future. The model can write to memory as Markdown files in the repository: extracted lessons, successful patterns, and even failed moves. I remember [Manus](https://t.me/dealerAI/1351) doing the latter.

In future sessions, the model can consult this memory and begin work from a higher level, without repeating previous mistakes. This mechanism implements a five-stage approach:

fail → investigate → verify → distill → consult

In other words: make a mistake → investigate the cause → verify the hypothesis about why the mistake happened → write the correct conclusion into memory → consult that memory for previously saved moves.

Overall, it resembles our own behavior. You make a mistake, scratch your head, understand why you were wrong, remember what to do and what not to do, and move on. When you encounter a similar situation later, you already know what to do and how. 🧠

## 3. Rubrics and goal

Overall, the authors do not treat this as something native in the model. In practice, a rubric is an evaluation, and a goal is the task. But here they move away from evaluative judgments — score, rank, better/worse — toward clear, verifiable criteria: tests passed, build completed without errors, answer matches expected output, and so on. The criterion for reaching the goal is the rubric.

And finally, the advice of the day: invest not in “super-prompters,” but in engineers who design agent systems. This is a strategic shift from exploitation to architecture. The core skills become context engineering and loop engineering for complex multi-step tasks, while prompting remains useful for simple, fast, one-step scenarios.

Source beyond X: [Fable 5 loop design guide](https://explainx.ai/blog/fable-5-loop-design-self-correction-memory-guide-2026).

Prompt engineering is no longer fashionable. Welcome: loop engineering.

Today’s [viral tweet](https://x.com/steipete/status/2063697162748260627?s=46&t=pKf_FxsPGBd_YMIWTA8xgg) from the creator of OpenClaw:

> Reminder: you no longer need to prompt coding agents. You should design loops that prompt your agents.

Literally a month ago, Boris Cherny, the creator of Claude Code, said something similar. He noted that Claude has been writing 100% of his code for half a year, and [stated](https://www.linkedin.com/posts/othmane-khadri-b48162236_my-job-is-to-write-loops-not-prompt-claude-activity-7469316416534552577-vswz):

> I no longer write prompts. I run loops that prompt agents and figure out what to do. My job is to write loops. We will see this shift throughout the rest of the year.

In other words, vibe coding is no longer about giving a single agent one task at a time and prompting every step. It is about giving a system a task that it works on in a loop: it delegates subtasks to agents, checks execution, finds errors, sends them back for correction, and repeats the cycle until one final goal is reached.




Extracted from the uploaded pasted HTML. 



Saved as Markdown: [extracted_text_and_links.md](sandbox:/mnt/data/extracted_text_and_links.md)



## Title



**Designing loops with Fable 5**

Author: Lance Martin @RLanceMartin

Published: 2026-06-09T17:21:06.000Z



## Extracted text



Mythos-class models like Claude Fable 5 have changed the way many of us work at Anthropic. I want to share two tips for getting the most out of this class of models.



## Self-correction loops



There’s been a lot of interest in loops recently. [@bcherny](https://x.com/@bcherny) [has mentioned](https://x.com/sairahul1/status/2064279904989147577?s=20) that “(his) job is to write loops.” Letting models hillclimb on an evaluation is a common recipe for improving task performance: [/goal](https://code.claude.com/docs/en/goal) in Claude Code and [Outcomes](https://platform.claude.com/docs/en/managed-agents/define-outcomes) in Claude Managed Agent are primitives that let you apply this general recipe for your specific task.



As mentioned in our [prompting guide](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5), Fable 5 is good at self-correcting in a loop. A well designed goal or rubric adds feedback to the environment that Claude is running in. This let’s Claude run, collect feedback via the goal or rubric, self-correct, and proceed until the goal or rubric is satisfied.



[Image](https://pbs.twimg.com/media/HKYoS3maMAoXYHR?format=jpg&name=small)



I’ll share one toy example that I used to test Fable: [Parameter Golf](https://github.com/openai/parameter-golf) is an open source ML engineering challenge to train the best model that fits in a 16MB artifact in < 10 minutes on 8xH100s.



It’s a bit like [@karpathy](https://x.com/@karpathy)'s [autoresearch](https://github.com/karpathy/autoresearch) project: it tests the ability of an agent to edit basic training code, launch training, poll the log, read the score, and decide what experiment to run next.



I compared Fable 5 to Opus 4.7 on this challenge using [Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview). CMA provides [the agent harness as well as a hosted sandbox](https://www.anthropic.com/engineering/managed-agents), so it’s well-suited for long-running tasks with Fable 5. For Parameter Golf, I gave CMA access to 8xH100 GPUs as a [self-hosted sandbox](https://platform.claude.com/docs/en/managed-agents/self-hosted-sandboxes).



One subtle point: what does the judging is important. We’ve seen that models have problems with self-critique on their own outputs. Prithvi Rajasekaran wrote about this in our engineering blog [here](https://www.anthropic.com/engineering/harness-design-long-running-apps).



[Image](https://pbs.twimg.com/media/HKYo5xEaMAAjeKL?format=jpg&name=small)



We’ve found that a verifier sub-agent [tends to outperform](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5) self-critique with Fable 5, because grading is done in an independent context window. [Outcomes](https://platform.claude.com/docs/en/managed-agents/define-outcomes) in CMA handles this by spawning a grader sub-agent for you.



For each test, I supplied a rubric with nine checkable criteria. Then I ran Parameter Golf for up to 8 hours. The Outcomes grader confirmed that all experimental criteria were met before allowing Claude to stop the work.



Fable 5 improved the training pipeline ~6x more than Opus 4.7. Opus 4.7's first experiment produced a small win and nearly everything after followed the same template: adjust a scalar, measure, keep if positive.



## Memory



Memory is [another area where Fable excels](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices). We can think about this as a outer loop that spans across sessions: Claude writes to memory during a session and those memories can be retrieved in future sessions.



[@pgasawa](https://x.com/@pgasawa) and team recently published Continual Learning Bench 1.0, so I wanted to test this on Fable 5 vs earlier models.



Embedded X post link: [https://x.com/pgasawa/status/2051361012838957144](https://x.com/pgasawa/status/2051361012838957144)



I compared Fable 5, Opus 4.7, and Sonnet 4.6 on one of the tasks from the benchmark: the task asks an agent to answer sequential questions given access to a SQL database. Each question is a separate agent session and memory is provided.



For this, I used CMA with [memory](https://platform.claude.com/docs/en/managed-agents/memory), which gives each agent access to a mounted filesystem that can be shared across sessions.



[Image](https://pbs.twimg.com/media/HKYq6HvaMAEfFJg?format=jpg&name=small)



For this task, effective use of memory benefits from a progression: fail, investigate, verify, distill, and consult.



Sonnet 4.6 exits around step 1. Opus 4.7 exits around step 3. Fable 5 tends to complete the progression: in its strongest runs, verification coverage is up to 73% and it distills learnings into general rules that help with future tasks.



Rather than directly prompting and steering Fable 5, it's often better to design loops that let the model to self-correct in response to environment feedback and manage its own context.



To get started, see the [docs](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5) or ask Claude Code, which can use the built-in [/claude-api](https://github.com/anthropics/skills/tree/main/skills/claude-api) skill.



## Extracted links



1. Lance Martin: [https://www.twitter.com/RLanceMartin](https://www.twitter.com/RLanceMartin)

2. @bcherny: [https://x.com/@bcherny](https://x.com/@bcherny)

3. has mentioned: [https://x.com/sairahul1/status/2064279904989147577?s=20](https://x.com/sairahul1/status/2064279904989147577?s=20)

4. /goal: [https://code.claude.com/docs/en/goal](https://code.claude.com/docs/en/goal)

5. Outcomes: [https://platform.claude.com/docs/en/managed-agents/define-outcomes](https://platform.claude.com/docs/en/managed-agents/define-outcomes)

6. prompting guide: [https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5)

7. Parameter Golf: [https://github.com/openai/parameter-golf](https://github.com/openai/parameter-golf)

8. @karpathy: [https://x.com/@karpathy](https://x.com/@karpathy)

9. autoresearch: [https://github.com/karpathy/autoresearch](https://github.com/karpathy/autoresearch)

10. Claude Managed Agents: [https://platform.claude.com/docs/en/managed-agents/overview](https://platform.claude.com/docs/en/managed-agents/overview)

11. Anthropic Managed Agents article: [https://www.anthropic.com/engineering/managed-agents](https://www.anthropic.com/engineering/managed-agents)

12. self-hosted sandbox: [https://platform.claude.com/docs/en/managed-agents/self-hosted-sandboxes](https://platform.claude.com/docs/en/managed-agents/self-hosted-sandboxes)

13. harness design article: [https://www.anthropic.com/engineering/harness-design-long-running-apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)

14. Fable prompting guide: [https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5)

15. Claude prompting best practices: [https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)

16. @pgasawa: [https://x.com/@pgasawa](https://x.com/@pgasawa)

17. embedded post: [https://x.com/pgasawa/status/2051361012838957144](https://x.com/pgasawa/status/2051361012838957144)

18. memory docs: [https://platform.claude.com/docs/en/managed-agents/memory](https://platform.claude.com/docs/en/managed-agents/memory)

19. /claude-api skill: [https://github.com/anthropics/skills/tree/main/skills/claude-api](https://github.com/anthropics/skills/tree/main/skills/claude-api)


Peter Steinberger, creator of OpenClaw, who now works with OpenAI.
Yesterday he posted this:
"You shouldn't be prompting coding agents anymore. You should be designing loops that prompt your agents."
Then Boris Cherny, head of Claude Code at Anthropic, said the same thing differently:
"I don't prompt Claude anymore. I have loops running that prompt Claude and figure out what to do. My job is to write loops."
Two of the most senior AI engineers alive. Same message.
Most people read it and thought: what does that actually mean?
I went deep on it.
Here is everything — broken down simply.
No jargon. Just the mental model you need.
Save this. It will change how you think about AI.
BUT FIRST: THE REASON MOST PEOPLE NEVER BUILD LOOPS
Loops sound great. Then you see the bill.
Here is what nobody tells you upfront.
A single agent loop on a medium coding task: 50,000–200,000 tokens.
A fleet loop with an orchestrator and 3 specialists: 500,000–2,000,000 tokens.
A loop running on a schedule every morning: millions of tokens per week.
At standard API pricing, a week of serious loop engineering costs more than most people's entire monthly AI budget.
This is why Peter Steinberger's replies were full of people saying: 
"Easy for you to say — you have unlimited OpenAI access."
They are not wrong.
Loop engineering on a normal budget breaks fast.
Every retry costs. Every self-correction costs. Every subagent costs. Every verification pass costs.
The open loop that explores freely? Burns tokens at a rate that makes your eyes water.
This is the hidden blocker nobody talks about.
Loops are not hard to design.
They are hard to afford.
That is exactly what Chinese LLMs solve.
Models like DeepSeek, Kimi, and MiniMax make agent loops economically viable.
The biggest problem with autonomous agents is not intelligence.
It is token burn.
Loops consume tokens fast.
A single run can easily burn 50K–200K tokens.
Run multiple agents, schedule loops daily, or work on large codebases — and costs spiral quickly.
This is where DeepSeek changes the equation.
DeepSeek V4 is currently one of the cheapest frontier-level models for running loops at scale.
What you get:
→ 1M context window — built for large projects and long-running workflows
→ 384K max output — handles bigger generations without breaking
→ DeepSeek V4 Flash + Pro models
→ Extremely low token pricing
→ Tool calls + JSON output for agent workflows
→ High concurrency (up to 2500 requests on Flash)
Why the 1M context window matters:
Loops need memory.
A coding loop working on a large project needs to keep:
— previous runs
— current errors
— architecture docs
— test results
— codebase context
all in memory at the same time.
Most models lose context midway.
Your loop starts forgetting what happened earlier.
DeepSeek holds significantly more context, so long-running loops stay coherent.
And because pricing is so low:
Loops stop breaking the bank.
PART 1: THE OLD WAY VS THE NEW WAY
For the last two years, we prompted agents one task at a time.
You type a prompt. The agent responds. You review it. You fix what is wrong. You prompt again. You are the loop.
That is starting to change.
Instead of asking an agent to build a landing page and then driving every step yourself, you set up a loop that handles discovery, planning, the work, checking, and iterating — until the goal is met.
The difference:
Old way (prompting):
You → Prompt → Agent → Output → You review → You fix → Repeat
New way (looping):
You set the goal → Loop runs → Agent discovers → Plans → Executes → Verifies → Iterates → Done
You are not prompting each step anymore.
The agent repeats the cycle for you.
A prompt gives the agent instructions.
A loop gives the agent a job.
PART 2: WHAT LOOP ENGINEERING ACTUALLY IS
Loop Engineering is the practice of designing repeatable feedback 
cycles that guide AI agents from attempt to verified outcome — 
without constant human intervention.
Looping is a setup you build.
Almost any agent harness can run it.
It just depends on how you wire it up.
At its simplest, one agent works on itself:
→ Researches
→ Drafts
→ Checks the draft against a goal
→ Fixes what is weak
→ Runs that cycle again until the work clears the requirements
Every loop — no matter how simple or complex — moves through 
the same 5 stages:
DISCOVER → PLAN → EXECUTE → VERIFY → ITERATE
Pass verification → ship.
Fail verification → loop again.
That is the whole idea.
Everything else in this article is just how you build that cycle properly.
PART 3: ONE AGENT VS A FLEET
There are two scales of looping:
SINGLE-AGENT LOOP
One agent runs the whole cycle on its own.
Think of it like a person redoing their own draft.
It discovers what is needed, plans the work, executes, verifies quality, and iterates if something is wrong.
Good for: 
→ Focused tasks 
→ Simple goals 
→ Limited scope
One brain. One loop. Self-improving.
━━━
FLEET LOOP
The bigger version is a fleet looping.
You give an orchestrator agent a goal.
It breaks the goal into pieces.
Hands each piece to a specialist agent.
Those specialists hand smaller jobs to their own subagents.
The whole tree keeps looping through discovery, planning, execution, and verification — until the goal is met.
Think of it like a whole team running a project end-to-end.
The structure:
→ Orchestrator owns the goal 
→ Specialists own the steps 
→ Subagents do the narrow work 
→ Eval gates make sure it is not slop
Example: "Build a productivity app"
Orchestrator (owns the mission)
    ↓                             ↓                      ↓
Research       Engineering           QA
Specialist        Specialist         Specialist
  ↓                                ↓                       ↓
Web                  Code Writer      Test Writer
Researcher   + Debugger    + Bug Tracker
Every agent in the tree runs the same 5-stage loop.
Discover → Plan → Execute → Verify → Iterate.
The important thing:
A single-agent loop is like a person redoing their own draft.
A fleet loop is a whole team running a project end-to-end.
PART 4: OPEN LOOPS VS CLOSED LOOPS
This is the most important practical distinction in 2026:
Not all loops are equal.
There are two types.
OPEN LOOPING
Exploratory. Wide space to move in.
You give the agent a goal and let it roam.
It can try different paths, discover things, build something you did not fully spec out.
This is the exciting end. It is what Peter Steinberger and others are doing at OpenAI.
The catch?
It burns an insane amount of tokens.
For the 90% of people without unlimited API budgets, open looping is not practical yet.
Pointed at projects with loose standards, it turns into a slop machine.
Fast. Messy. Expensive.
CLOSED LOOPING
Bounded. A human designs the end-to-end path first.
→ Clear goal 
→ Defined steps 
→ An evaluation at each step 
→ A point where it stops or hands back to you
The agents still loop — but inside a framework you built.
It gets better every run because each pass feeds the next.
It runs on a normal budget because the path is tight.
The standard keeps it honest.
Without a quality gate: AI drifts.
With a quality gate: AI improves.
For most real work today, closed looping is the one that pays off.
Which one should you use?
Start with closed loops.
Build a tight system that works reliably.
Then open it up once you have the quality gates.
PART 5: THE 6 BUILDING BLOCKS OF EVERY GOOD LOOP
Every loop that holds together has these 6 things:
Now the practical part.
A loop has 5 stages conceptually.
But what do you actually build to make it run?
6 things. Both Claude Code and Codex ship all of them now.
Here they are — and what each one is really doing inside the loop.
1. AUTOMATIONS
This is what triggers DISCOVER and kicks the loop into motion.
The heartbeat of the loop.
An automation is what makes a loop an actual loop — and not just one run you did once.
You define a prompt, a cadence, and a goal.
The loop runs on schedule. Findings come to you. You are not the one going around checking.
→ /loop re-runs on a cadence
→ /goal keeps going until a condition you wrote is actually true
Give it: "all tests in test/auth pass and lint is clean."
Walk away.
2. WORKTREES
This is what lets multiple EXECUTE stages run in parallel without breaking each other.
Parallel agents without chaos.
The second you run more than one agent, files start colliding.
Two agents writing the same file is the same problem as two engineers committing to the same lines without talking.
A git worktree gives each agent its own isolated working directory on its own branch — same repo history, zero collisions.
One agent's edits literally cannot touch the other's checkout.
3. SKILLS
This is what makes DISCOVER faster — the agent already knows your project before it starts.
Stop explaining your project from zero every run.
A skill is a folder with a SKILL.md inside — project conventions, build steps, the "we don't do it this way because of that incident."
Written once. Read every loop.
Without skills: the loop re-derives your whole project from zero every cycle.
With skills: it compounds. The agent knows your project before it starts.
→ VISION.md — what success looks like
→ ARCHITECTURE.md — the tech stack and folder structure
→ RULES.md — what the agent is never allowed to do
4. PLUGINS AND CONNECTORS
This is what makes EXECUTE real — the loop acts in your actual environment, not just your filesystem.
A loop that can only see the filesystem is a tiny loop.
Connectors (built on MCP) let the agent read your issue tracker, query a database, hit a staging API, drop a message in Slack.
This is the difference between an agent that says "here is the fix" and a loop that opens the PR, links the Linear ticket, and pings the channel once CI is green — by itself.
5. SUBAGENTS
This is what makes VERIFY honest — the checker is never the same agent as the maker.
Keep the maker away from the checker.
The model that wrote the code is too nice grading its own homework.
A second agent with different instructions — sometimes a different model — catches the stuff the first one talked itself into.
The split that works:
→ One agent explores
→ One agent implements
→ One agent verifies against the spec
This is also what /goal does under the hood.
A fresh model decides if the loop is done — not the one that did the work.
6. MEMORY
This is what makes the loop persistent — DISCOVER on run 47 knows everything runs 1 through 46 already tried.
The spine of the whole loop.
A markdown file. A Linear board. Anything that lives outside the single conversation.
The model forgets everything between runs.
The repo does not.
The memory file holds: what got tried, what passed, what is still open.
Tomorrow morning the loop picks up where today stopped.
It sounds too simple to matter.
Every long-running loop depends on it.
PART 6: REAL LOOP EXAMPLES
What loops look like in practice:
The Coding Loop
plaintext
Read VISION.md + ARCHITECTURE.md
↓
Plan the next change
↓
Edit the code
↓
Run tests automatically
↓
If tests fail → read error → fix → retest
↓
If tests pass → summarize changes
↓
Stop
No human in the middle.
The agent writes, tests, fixes, and verifies on its own.
━━━
The Research Loop
plaintext
Define research question
↓
Search for sources
↓
Summarize findings
↓
Verify claims against sources
↓
Compare conflicting information
↓
Synthesize final answer
↓
Stop when confidence threshold met
━━━
The Content Loop
plaintext
Topic + audience + goal defined
↓
Draft created
↓
Critique agent reviews draft
↓
Rewrite based on critique
↓
Score against success criteria
↓
If score passes → publish
↓
If score fails → rewrite again
━━━
The Sales Outreach Loop
plaintext
ICP (Ideal Customer Profile) defined
↓
Find leads matching profile
↓
Enrich with company data
↓
Qualify against criteria
↓
Personalize message
↓
Quality review
↓
Send or escalate to human
Every loop has the same skeleton:
Goal → Action → Check → Fix → Repeat until done.
PART 7: PROMPT ENGINEER VS LOOP ENGINEER
The skill gap opening up in 2026:
Prompt Engineer
→ Craft better instructions 
→ Linguistic skill 
→ Better prompt 
→ better single output 
→ Still reviews output manually after every run 
→ You are the feedback loop
Loop Engineer
→ Design better feedback cycles 
→ Software engineering skill 
→ Better loop 
→ reliable verified outcomes 
→ System runs, checks, and self-corrects 
→ The system is the feedback loop
Prompt Engineer ->  "Write me a function" 
Loop Engineer -> "Write → test → fix until green"   
Writes better prompts Writes VISION.md   Reviews output manually Tests review automatically   Runs agent once Builds repeating system   Pays per single output Pays for verified outcome
The tools are the same.
The mindset is completely different.
Prompt engineers ask AI for output.
Loop engineers design systems that produce verified outcomes.
The highest-paid AI engineers in 2026 are not writing better English sentences.
They are writing the logic that governs how agents discover, plan, check their own work, and know when they are done.
CLOSING
That is Loop Engineering.
Let me recap everything:
The shift:
→ For two years we prompted agents one task at a time → Now we design loops that run the whole cycle
The 6 things you actually build:
→ Automations — the heartbeat, triggers discovery
→ Worktrees — parallel agents without collisions
→ Skills — project knowledge that compounds every run
→ Plugins and connectors — loop acts in your real tools
→ Subagents — maker and checker are never the same agent
→ Memory — loop never forgets between runs
Two scales:
→ Single agent: one brain, self-improving 
→ Fleet: orchestrator + specialists + subagents — every agent runs the same loop
Two types:
→ Open loop: exploratory, powerful, expensive, needs unlimited budget 
→ Closed loop: bounded, reliable, affordable, the one that pays off today
The 5 parts of every good loop:
→ Goal — define what done means precisely 
→ Context — VISION.md, ARCHITECTURE.md, RULES.md 
→ Action — only what the agent actually needs 
→ Feedback — tests, type checks, linters, structured errors 
→ Stop condition — when the loop knows it's finished
The cost problem:
→ Loops burn tokens fast 
→ $20 on DeepSeek goes dramatically further than most frontier models
→ That removes the last real blocker
The big shift:
→ Prompt engineers ask AI for output 
→ Loop engineers design systems that produce verified outcomes
Peter Steinberger said it right:
Stop prompting your agents.
Start designing loops.
Because one reliable loop is worth a thousand perfect prompts.
One more thing nobody says out loud.
Two people can build the exact same loop and get completely opposite results.
One uses it to move faster on work they understand deeply.
The other uses it to avoid understanding the work at all.
The loop does not know the difference.
You do.
That is what makes loop design harder than prompt engineering — not easier.
Boris Cherny's point is not that the work got easier.
It is that the leverage point moved.
Build the loop.
But build it like someone who intends to stay the engineer — not just the person who presses go.
Because one reliable loop is worth a thousand perfect prompts.
And with 1.7 billion tokens for $20, you can finally afford to build one.
If this helped:
