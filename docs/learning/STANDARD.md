# Learning Document Standard

Every pull request ships with a learning document in `docs/learning/`,
numbered in order (`01-repo-setup.md`, `02-ws-gateway.md`, …).

## Purpose

The reader is Aryan, who did not write this code and will be questioned
on it by his mentor. After one read he should be able to explain what
the code does, where it lives, why it was built this way, and what
happens when it fails.

## Length

- Target: 100–250 lines. Hard ceiling: 300 lines.
- Short beats complete. If something is not likely to be asked about,
  leave it out.
- No padding. A section with nothing to say gets one line.

## Rules

1. Define every term the first time it appears, in one or two
   sentences. Do not assume knowledge, but do not write essays either.
2. Every code snippet is copied from the real code, with its file path.
   Snippets are short — only the lines that matter.
3. Never invent behaviour, limits or facts. If unsure, say so.
4. State weaknesses honestly.
5. Plain language, short sentences.

## Sections, in this order

### 1. In one minute
3–5 lines: what this change does, where it lives, why it exists.

### 2. Files
Each file added or changed, one line each.

### 3. How it works
Walk through the main path with the key snippets. Explain the lines
that are not obvious, and why they are written that way. Include a
small Mermaid diagram only if the flow has more than three steps.

### 4. New concepts
Only concepts that appear in this change and are likely to be new.
Each: what it is, and why it is used here. Two to four lines each.

### 5. Why this and not that
One table covering the real choices made in this change:

| Choice | Picked | Alternatives | Why not them |
|---|---|---|---|

### 6. When things go wrong
One short table of the realistic failures and what the code does.
Skip if the change has no meaningful failure paths.

### 7. Questions you could be asked
8–12 questions with short answers. Include at least one "where is
the code that…", one "what happens if…", one "why not…", and the
hardest question about this change.

### 8. Check yourself
3 questions to answer out loud without the document open.