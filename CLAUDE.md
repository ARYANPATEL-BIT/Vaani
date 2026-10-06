Project

Vaani — a real-time, interruptible voice agent with a studio that turns written context into a lip-synced video in the operator's cloned voice. Ten weeks, two contributors (Aryan, Samyak), mentor Narvin. Full specification is in docs/.

Stack: FastAPI gateway with WebSockets, React frontend, PostgreSQL, Silero VAD, faster-whisper, Piper, hosted LLM providers behind an adapter, ElevenLabs and XTTS for cloning, HeyGen and fal for avatar video, ffmpeg for assembly.

Non-negotiable constraints
CPU by default. The committed config runs everything on CPU: ASR is cpu / int8 / small. GPU runs (e.g. cuda / float16 / large-v3) come only from local overrides in the gitignored backend/.env, never from committed config. VAD always stays on CPU.
No vendor SDK is imported outside providers/, voice/synth/, or render/avatar/. Vendors are configuration values, never code dependencies.
Latency is the primary quality bar. Any change to the conversation path carries a measured before/after. Target: P50 under 1,000 ms, mic-stop to first audible sample.
Cancellation is first-class. Every provider call, tool call, and long-running operation takes a cancellation token and aborts the underlying HTTP stream cleanly.
Nothing that makes a network call goes in the endpointing hot path.
Secrets come from the environment. Never in source, committed config, logs, or client-delivered code.
Config over constants. No hardcoded model IDs, thresholds, endpoints, or paths.
Spend caps are checked before any paid call is dispatched.
The learning document requirement

Every piece of work produces or updates a learning document, written by you, not by me. Code without one is not complete.

Every pull request ships a learning document in docs/learning/ that meets docs/learning/STANDARD.md. A PR without one is not ready to merge.

The purpose is teaching. I am learning this stack while building it, so the document is written for someone who did not write the code and does not already know the techniques involved. Explain the concepts, not just the decisions. If the code uses a WebSocket, a cancellation token, a state machine, or an async generator, explain what that is and why it is the right tool here — briefly, in plain language, before explaining what our code does with it.

Assume I am smart but new to this area. Never assume I already know a term you are about to use.

Write to docs/learning/<module-or-feature>.md. Use this exact structure:

markdown
# <Module or Feature>

## In one paragraph
What this does and why the system would break without it. No jargon.

## Concepts you need first
Explain every technique or term used here that I might not know.
"A cancellation token is an object passed into a long-running operation.
The caller can flip it, and the operation checks it and stops early.
We need one because a user can interrupt mid-response, and without it
the LLM would keep streaming tokens nobody will hear."
Two to five of these. Skip anything already explained in an earlier doc,
and link to that doc instead.

## Where the code lives
| File | Responsibility |
|---|---|
| `src/turn/state_machine.py` | Legal states and transitions |

## Walk through the code
Take the main path and narrate it in call order, with real snippets.
Show the actual lines, then explain what each is doing and why it is
written that way. This is the section I will reread most.

## Who calls this, and what it calls
Inbound: which modules invoke it and from where.
Outbound: which modules or services it depends on.

## Why it is built this way
The reasoning, at a level someone learning can follow.
Not "we used X" but "we used X because Y mattered more than Z."

## Alternatives considered
| Alternative | What it would have looked like | Why rejected |
|---|---|---|
| Fixed 700 ms silence timer | One constant, no adaptation | Cuts users off mid-thought |
Explain each alternative well enough that I understand what we passed up.

## Trade-offs accepted
What is worse because of this choice. Every decision costs something.

## API / interface design
If this exposes an interface: why these methods, why these parameters,
why this return shape. Why not fewer methods, or more. What a caller
can and cannot do with it.

## Pros and cons
**Pros:** ...
**Cons:** ...

## What would make us change this
The condition under which this decision should be revisited.

## Questions a reviewer could ask, with answers
Six to eight. Include at least two "where is X implemented", two
"what happens when Y fails", and two conceptual ones about the
techniques used.

Rules for the learning document:

You write it, in the same session as the code. It is not my homework and not a retrofit.
Teach, do not summarise. A sentence I cannot follow is a failed sentence.
Real code snippets in the walkthrough, not pseudocode.
Alternatives must be real options that were genuinely available, explained well enough that I understand what we gave up.
The trade-offs section must not be empty. If a decision has no downside, it was not a decision.
Never assume the reader wrote the code.
How to work with me

Before writing code, tell me:

What you are about to build and which files it will touch.
What alternatives exist and which you would pick.
What could go wrong.

Wait for confirmation on anything touching the conversation hot path, the provider layer, cancellation, or money.

While writing code:

Explain non-obvious lines inline as comments, especially concurrency and cancellation.
Prefer clear over clever. This code gets read aloud in a viva.
No file over ~300 lines. If it grows past that, the module boundary is wrong.

After writing code:

Write or update the learning document, teaching-first as described above.
Tell me what you did not do and why.
Tell me what you are least confident about.
Name any assumption you made that I did not confirm.

Never:

Generate code I have not asked about first.
Silently pick a library. Name it and say why.
Write a wrapper, abstraction, or pattern without a concrete need for it.
Claim something is tested when it is not.
Definition of done

A task is complete when all of these are true:

Implemented and running.
Instrumented — emits a timing span if it is on a measured path.
Benchmarked — no latency regression on the conversation path.
Configuration-driven — no hardcoded values.
Adapter-backed if it touches a vendor.
Cancellation-safe.
Error paths handled and surfaced audibly or in job state.
Learning document written or updated, and readable by someone who did not write the code.
I could explain this to my mentor after reading the learning document once.

Point 9 is the real gate. If the document leaves me unable to say where a function lives, what it does, or why it beat the alternative, the document has failed and needs rewriting — not me.

Weekly routine

At the end of each week, generate docs/learning/week-N-review.md containing:

What was built, with file paths.
Every decision made, with the rejected alternative.
Measured numbers: latency, cost, error rates.
What broke and what fixed it.
Ten questions a mentor could ask about this week's code, with answers.
Any concept introduced this week, explained from scratch.
What we are least confident about going into next week.
Reality check

The learning document is how I learn this project. My mentor will ask "where is the code that does this", "what happens if this fails", and "why not the other way" — so those answers must be in the document, in language I can absorb, before he asks.

If I read a learning document and still cannot answer those three questions about the module, the document was not good enough. Tell me what you were unsure how to explain, and we will fix it together rather than leaving a gap.

Write the simplest code that does the job. No abstraction until there is a second case that needs it. No options nothing uses. No defensive handling for cases that cannot occur. If a reader has to jump between three files to follow one request, the design is wrong.