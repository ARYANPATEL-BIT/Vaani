# Learning Document Standard

Every pull request ships with a learning document in `docs/learning/`,
numbered in the order the work happened (`01-repo-setup.md`,
`02-ws-gateway.md`, …).

## Who the reader is

The reader is Aryan, who did not write this code. He is about to be
questioned on it by his mentor, who asks hard questions like "where is
the code that does this", "what happens when this fails", and "why not
do it the other way".

Assume the reader knows **nothing** about any term, library, protocol
or technique used. If a word would need to be looked up, it must be
explained in this document the first time it appears.

The goal is not a summary. The goal is that after reading this once,
the reader can explain every line, defend every decision, and answer
questions about it without the document open.

## Writing rules

1. **Never assume knowledge.** Define every term on first use. If a
   concept needs another concept to make sense, explain that one first.
2. **Why before how.** For every piece, say what problem it solves
   before describing how it works.
3. **Only real code.** Every snippet is copied from the actual code in
   this pull request, with its file path and line numbers. Never write
   illustrative code that does not exist in the repo.
4. **No invented facts.** Anything about a library's behaviour, a
   licence, a limit, or a version must be true for the version pinned
   in `docs/versions.md`. If unsure, say so plainly rather than guess.
5. **Be honest about weaknesses.** Every design has costs. State them.
   A document that only praises its own code is useless for a viva.
6. **Plain language.** Short sentences. Analogies where they genuinely
   help. No filler.
7. **Scale to the change.** A small change gets a shorter document.
   Every section below must appear, but a section with nothing to say
   says so in one line rather than being padded.
8. **Diagrams where flow matters.** Use a Mermaid block for any
   sequence of steps, message exchange, or state change.

## Required sections, in this order

### 1. In one minute
Five to eight lines. What this change does, where it lives, why it
exists, and what the reader can now demonstrate because of it.

### 2. Where it sits in the system
- Which part of Vaani this belongs to (conversation loop, enrolment,
  studio, infrastructure).
- What calls this code, and what this code calls.
- A Mermaid diagram showing it in the pipeline.
- What would break, or not exist, without it.

### 3. File map
Every file added or changed, one line each: path, and what it is for.

### 4. Concepts you need first
For every concept, technique, protocol or term used — each one gets:
- **What it is**, from scratch.
- **Why it exists** — the problem it solves in general.
- **An analogy**, if one genuinely helps.
- **How it is used here**, specifically.
- **A common misconception** about it, if there is one.

Nothing is too basic to include if it appears in the code. Examples of
the level expected: what a WebSocket is and how it differs from HTTP;
what async means in Python; what a lockfile is; what a sample rate is.

### 5. Walkthrough of the main path
Follow one real request or event from start to finish through the
code. For each step:
- The real snippet, with file path and line numbers.
- What it does, line by line for anything non-obvious.
- Why it is written this way.

After the main path, cover any secondary paths (errors, retries,
cancellation) the same way.

### 6. Every technology used
One entry per library, tool, service or standard introduced or used
in a new way. Each entry has:
- What it is and what it does.
- Why it was chosen for this project specifically.
- A comparison table of the realistic alternatives:

| Alternative | What it is | Why we did not use it | What we would gain by switching |
|---|---|---|---|

- What we give up by choosing it.
- Licence, and whether it matters for this project.
- The version pinned, from `docs/versions.md`.

### 7. Design of the interface
For every function, class, endpoint, message or config key a caller
would use:
- Its exact shape: name, inputs, outputs, errors.
- **Why it has this shape.** What the caller needs, and what this
  shape makes easy or hard.
- **Other shapes that were possible**, and why each was rejected.
  (For example: one endpoint or several; push or pull; return a value
  or raise; sync or async; one message type with a field, or several
  message types.)
- What is deliberately hidden from the caller, and why.
- How the interface could change later without breaking callers.

### 8. State and data
- What state exists, where it is held (memory, database, file), and
  who owns it.
- Its lifecycle: created when, changed when, destroyed when.
- What happens to it if the process crashes midway.

### 9. What happens when things fail
A table covering every realistic failure:

| What fails | How the code detects it | What the code does | What the user sees | Where in the code |
|---|---|---|---|---|

Include: bad input, network loss, a slow or missing dependency, a
crash midway, running twice, running at the same time as itself.

### 10. Performance and latency
- Does this code sit on the path the user is waiting on?
- What it costs in time, memory or network, and how that was judged
  acceptable.
- Anything that would get slower as usage grows.

### 11. Security and privacy
- What input is untrusted, and how it is handled.
- Any secret, personal data, voice or likeness involved, and how it
  is protected.
- What an attacker could try, and what stops them.
- If nothing applies, say so and why.

### 12. Testing
- What the tests check, and how to run them.
- What is **not** tested, and why.
- How to verify it works by hand.

### 13. How to change it
The two or three most likely future changes, and exactly where in the
code each would be made.

### 14. Known limitations
Every weakness, shortcut and unhandled case, stated plainly, with
whether it is intended to be fixed and when.

### 15. Questions you could be asked
At least fifteen, with short, direct answers. Cover all of these kinds:
- **Where** — "Where is the code that does X?" (answer with file and
  function)
- **Trace** — "Walk me through what happens when Y."
- **Failure** — "What happens if Z fails at this point?"
- **Why not** — "Why didn't you use A instead?"
- **Concept** — "Explain B in your own words."
- **Trade-off** — "What did you give up by doing it this way?"
- **Change** — "How would you add C?"
- **Weakness** — "What is the weakest part of this?"

Include the hardest questions, not only comfortable ones.

### 16. Glossary
Every term used in the document, one line each, alphabetical.

### 17. Check yourself
Five questions to answer out loud **without the document open**. For
each, name the section to reread if the answer does not come easily.

## Before finishing a learning document, confirm
- Every snippet exists in the code at the path and lines given.
- Every term is defined before or where it is first used.
- Every alternative has a reason for rejection.
- Every failure in section 9 is handled in code, or listed in
  section 14 as a known limitation.
- Nothing claims more certainty than the code or its dependencies
  support.