# Learning Document Standard

Every pull request ships with a learning document in `docs/learning/`,
numbered in order (`01-repo-setup.md`, `02-ws-gateway.md`, …).

## Purpose

The reader is Aryan, who did not write this code and will be questioned
on it by his mentor. After one read he should be able to say what was
built, what it was built with, why those choices and not others, where
every piece lives, and what happens when it fails.

## Length

- Target: 150–300 lines. Hard ceiling: 350 lines.
- Short beats complete. If something is unlikely to be asked about,
  leave it out.
- No padding. A section with nothing to say gets one line.

## Rules

1. Define every term the first time it appears. Two or three sentences,
   not an essay.
2. Every code snippet is copied from the real code, with its file path.
   Only the lines that matter.
3. Never invent behaviour, limits, versions or facts. If unsure, say so.
4. State weaknesses honestly.
5. Plain language, short sentences.

## Sections, in this order

### 1. What we built in this branch
Branch name, and 4–6 lines: what this adds to the project, and what
can be done now that could not be done before.

### 2. What we used to build it
Every library, tool, service or technique used in this change.
One short entry each:

- **What it is** — one or two lines.
- **What it does for us here** — the specific job it does in this code.
- **Why we used it** — the reason it was picked.

Include things that are easy to take for granted: a validation
library, a test runner, a clock function, a data structure chosen for
a reason. If it appears in the code and someone could ask "what is
that", it belongs here.

### 3. Alternatives we rejected
One table covering every real choice made in this change — libraries,
approaches, orderings, data structures, API shapes.

| Decision | What we chose | Alternatives | Why not them | What we gave up |
|---|---|---|---|---|

Every row needs a real reason. "It is the standard" is not a reason;
say what it gives us that the alternative does not.

### 4. Where things live
A map of this change, so any "where is the code that does X" question
has a direct answer.

| What | File | Function or class |
|---|---|---|

Cover the layers a question could land on: where config is read, where
data is validated, where state is held, where the database layer is
and which queries it runs, where errors are raised, where things are
logged. If a layer does not exist yet in this change, say so in one
line rather than leaving it out.

### 5. How it works
Walk through the main path with the key snippets. Explain the lines
that are not obvious, and why they are written that way. Add a small
Mermaid diagram if the flow has more than three steps.

### 6. When things go wrong
A short table of the realistic failures and what the code does.

| What fails | What the code does | What the user sees |
|---|---|---|

Skip only if this change genuinely has no failure paths.

### 7. New terms
Every term, acronym or concept introduced in this change, alphabetical.
Two or three lines each: what it means, and why it appears in our code.

Examples of the level expected: Pydantic, monotonic clock, percentile,
coroutine, WebSocket frame, migration, index. If the reader would have
to look it up, it goes here — even if it was already mentioned in an
earlier section.

### 8. Questions you could be asked
8–12 questions with short answers. Include at least one of each:
"where is the code that…", "what happens if…", "why not…",
"what does <term> mean", and the hardest question about this change.

### 9. Check yourself
3 questions to answer out loud without the document open.