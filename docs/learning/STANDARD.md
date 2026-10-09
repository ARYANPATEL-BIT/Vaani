# Learning Document Standard

Every pull request ships one learning document. It says what the PR changed and why,
in plain words, for a reader who did not write the code and will be asked about it by
the mentor.

## Two kinds of document

- **The per-PR document** (this standard): one per PR, numbered in order, in
  `docs/learning/backend-learning/` or `docs/learning/frontend-learning/`.
- **`docs/learning/PROJECT.md`**: the whole system as it is on `dev` now. A PR that
  changes the flow, the stack or the database updates PROJECT.md in the same PR.
  The per-PR document says what changed. PROJECT.md says how everything works now.

## History

Documents `01` to `15b` in both folders were written to the old nine-section
standard. They stay as they are, as a record of each step. Do not edit or reformat
them. If one of them disagrees with the code, the code wins, and PROJECT.md describes
the code. `backend-learning/16-english-voice.md` is the first document in this format.

## Length

60 to 120 lines per document.

## Sections, in this order

### 1. What
One short paragraph: what this PR adds or changes. Branch name at the top.

### 2. Why
The problem it solves. Give the measured number when there is one, with the run file
it came from (`docs/findings/...`). If nothing was measured, say so.

### 3. How
The flow in plain words, step by step, naming the files that take part. No code, no
snippets, no line-by-line walkthrough. A reader should be able to say where each part
lives and what it does.

### 4. When
When this runs or triggers: at startup, at session start, on every frame, at the end
of a turn, during a barge-in, and so on.

### 5. Alternatives
One table. One row for every library, model or approach this PR chose, with **exactly
one** alternative and why it was not picked.

| Chosen | The alternative | Why not the alternative |
|---|---|---|

The alternative must have been a real option. The reason must say what we would
have lost or risked. "It is the standard" is not a reason.

### 6. Known issues
3 to 5 short lines: what is still wrong, what was not measured, what broke in a live
run. Honest, with the number or run file when there is one.

## Writing rules

1. Plain language, short sentences. When you first use a term the reader may not
   know, explain it in a few words.
2. No code snippets and no code walkthroughs. Name the file and say what it does.
3. Never invent a behaviour, a limit, a version or a number. Every number cites the
   run file or document it came from. If something was not measured, say "not
   measured".
4. Do not copy from `docs/contracts.md` (the protocol) or
   `docs/findings/perf-1-latency-budget.md` (the latency numbers). Link to them.
5. Files are UTF-8 without BOM.

## Checklist before the PR is ready

- [ ] The document has all six sections, in order, and is 60 to 120 lines long.
- [ ] Every alternative row has exactly one alternative and a real reason.
- [ ] Every number has a source, or is marked as not measured.
- [ ] If the flow, the stack or the database changed, PROJECT.md is updated in the
      same PR.
