# Groq failover: a model that exists, and a 404 that says why

## 1. What we built in this branch

Branch `fix/groq-model`. Failover to Groq was broken: Groq answered every request with
HTTP 404 because our configured model, `llama-3.1-8b-instant`, is no longer offered to
our key. So when Gemini timed out, the turn ended with no reply. Now `config.toml` names
`qwen/qwen3.8-27b`, picked by **measured** first-token time. A Groq 404 now says the
configured model may have been retired and names it. `measure_llm.py` can race several
Groq models against Gemini and keeps a run file. Two cleanups: `measure_tts.py` writes
WAVs only with `--wavs`, and `CLAUDE.md` lost two lines that duplicated `STANDARD.md`.

## 2. What we used to build it

- **Groq `GET /openai/v1/models`.** *What:* an endpoint that lists the models a key can
  call. *Here:* run once (key in the `Authorization` header only) to see what exists.
  *Why:* model IDs must come from the vendor's list, not memory. Memory is how we
  ended up with a retired model.
- **`reasoning_effort` / `include_reasoning`.** *What:* Groq request fields. The first
  sets how much hidden "thinking" a reasoning model does before answering. The second
  says whether that thinking is sent back. *Here:* `none` and `false` in config.
  *Why:* thinking happens before the first token, so it is pure delay for voice.
- **`httpx.MockTransport`.** *What:* an httpx transport that hands each request to a
  Python function instead of the network. *Here:* the new failover test gives Gemini
  a function that raises a timeout and Groq one that returns a canned stream.
- **`RunLog`** (`scripts/run_log.py`). *What:* prints a line and appends it to a
  timestamped file with the commit and Windows power scheme. *Here:* `measure_llm.py`
  now uses it, so every number in the findings points at a file.
- **Pydantic `model_copy(update=...)`.** *What:* a copy of a settings object with some
  fields changed; the original is untouched. *Here:* builds one settings object per
  contestant (Gemini alone, each Groq model alone).

## 3. Alternatives we rejected

| Decision | What we chose | Alternatives | Why not them | What we gave up |
|---|---|---|---|---|
| Groq model | `qwen/qwen3.8-27b`, `reasoning_effort = "none"` | `openai/gpt-oss-20b` at `low`; `allam-2-7b` | gpt-oss p50 788 ms vs qwen 454 ms. allam is Arabic-focused with a 4k context | gpt-oss had the better tail (p95 1632 vs 1835 ms) |
| How to choose | Measure both, same prompts | Pick from model cards | A card is not our prompt, our network or our key | 33 paid requests |
| Reasoning level | The lowest each model accepts | Same level for both | gpt-oss has no `none`; "lowest accepted" matches Gemini's `minimal` rule | Not a like-for-like setting |
| 404 handling | Keep `ProviderFailedError` (no failover), clearer message | Treat 404 as "their side", fail over | A retired model is a config error; failing over would hide it | A dead fallback still shows only when it is needed |
| Failover test | Real providers + `build_chain` on fake HTTP | The existing stub test only | Stubs prove the chain's decision, not that config reaches the request body | ~30 lines of test |
| Comparing models | `--groq-model ID:EFFORT` flag | Run `measure_llm.py` once per model | Gemini would be measured twice (more requests), in different minutes | A slightly busier script |

## 4. Where things live

| What | File | Function or class |
|---|---|---|
| Groq model and reasoning settings | `backend/config.toml` | `[llm.groq]` |
| Config read | `backend/vaani/config.py` | `GroqSettings` (unchanged) |
| Body built (model, reasoning fields) | `backend/vaani/providers/groq.py` | `_request_body` (unchanged) |
| 404 message raised | `backend/vaani/providers/groq.py` | `GroqProvider._error_for` |
| Failover decision | `backend/vaani/providers/chain.py` | `ProviderChain.stream` (unchanged) |
| Failover test, fake HTTP | `backend/tests/test_chain.py` | `test_gemini_timeout_fails_over_to_groq_with_configured_model` |
| 404 test | `backend/tests/test_groq.py` | `test_404_names_the_configured_model_as_maybe_retired` |
| Latency race | `backend/scripts/measure_llm.py` | `alone`, `main` |
| Run files | `docs/findings/llm-latency/`, `docs/findings/groq-failover/` | |
| Database, state | None: this change has neither | |

## 5. How it works

**The failover rule did not change.** `ProviderChain` tries Gemini; on a timeout, 429
or 5xx **before the first chunk** it moves to Groq. After a chunk it never restarts,
because the user may already be hearing the answer (`06-cancel-failover.md`). The bug was
only that Groq, once reached, asked for a model that no longer exists.

**The config** (`backend/config.toml`):

```toml
model = "qwen/qwen3.8-27b"
reasoning_effort = "none"
include_reasoning = false
```

`_request_body` already copies these into the JSON body when they are set, so no
provider code changed for the switch.

**The 404 message** (`backend/vaani/providers/groq.py`, `_error_for`):

```python
if status == 404:
    return ProviderFailedError(
        f"groq: configured model {self._settings.model!r} not found "
        f"(HTTP 404); it may have been retired. List the models the key "
        ...
```

The model ID and URL come from config; `detail` is Groq's own message after `_redact`
has removed the key. It stays `ProviderFailedError`, which the chain never fails over on.

**The test** (`backend/tests/test_chain.py`) builds the real chain from the real config:

```python
def gemini(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("no headers", request=request)
...
chain = build_chain(settings, RequestCap(5), clients)
assert collect(chain) == ["groq answers"]
body = json.loads(groq_requests[0].content)
assert body["model"] == groq_cfg.model
```

`ReadTimeout` becomes `ProviderTimeoutError` in `streaming.py`, the chain fails over,
and the test checks that the body Groq received carries config's model and reasoning
fields, and that the key is in the header, not the URL.

**The race** (`backend/scripts/measure_llm.py`): each `--groq-model` becomes its own
one-provider chain via `alone(...)`, and the round order rotates (`names[shift:] +
names[:shift]`), so no contestant is always measured right after another.

## 6. When things go wrong

| What fails | What the code does | What the user sees |
|---|---|---|
| Gemini times out, Groq fine | Waits `timeout_s` (10 s), fails over, Groq answers | **10 s of silence**, then a reply. Known issue, not fixed here |
| Groq retires qwen too | 404 -> `ProviderFailedError` naming the model | No reply that turn; the log says what to change |
| Gemini fails mid-answer | Raised, not restarted on Groq | The reply stops part-way |
| Groq free-tier 429 | `RateLimitedError`; if Groq was last, `ProvidersExhaustedError` | No reply that turn |

**Known issues.** (1) Only 10 requests per model, laptop on the Silent power scheme; p95
is one request. (2) Persona checks passed but were 2 questions per persona. Default and
support answered "what will you do today?" with only their role, and tutor mixed आप and
तुम. (3) Gemini p50 was 1702 ms, against 898 ms on day 11; cause unknown.

## 7. New terms

- **Model retirement.** A vendor stops serving a model ID. Requests then fail (Groq:
  404). Why pinned IDs need a periodic check against `/models`.
- **p50 / p95.** The middle value, and the value 95% of requests beat. With 10 values,
  p95 is simply the largest.
- **Reasoning model.** A model that writes hidden "thinking" tokens before its answer.
  More thinking, later first token.
- **Time to first token.** Request sent -> first piece of reply text. The LLM's share
  of our 1,000 ms budget.

## 8. Questions you could be asked

1. **Where is the code that picks Groq after Gemini fails?** `ProviderChain.stream` in
   `backend/vaani/providers/chain.py`; the order is `[llm] provider_order` in config.
2. **What happens if Groq's model is retired again?** A 404 becomes `ProviderFailedError`
   whose message names the model and says it may be retired. No further failover.
3. **Why not fail over on a 404?** It is our config that is wrong. Hiding it behind
   another provider means nobody notices until that one fails too.
4. **Why qwen over gpt-oss?** Lower p50 on the same 10 prompts (454 vs 788 ms), and it
   kept the script, gender and no-name rules. Its p95 was worse.
5. **What does `reasoning_effort = "none"` do?** Tells qwen to skip thinking, so no
   hidden tokens delay the first word.
6. **Why does the test use the real providers, not stubs?** Stubs cannot show the config
   value reaching the HTTP body; the old bug lived exactly there.
7. **Does this make turns faster?** No: Gemini is still first. It makes the fallback work.
8. **Hardest: what would a 2.5 s first-token deadline cost?** Gemini answers that are
   just slow (about 1 in 20 at our p95) would go to Groq, which doubles requests on those
   turns and spends the shared cap faster.

## 9. Check yourself

1. Which file would you change if Groq retires `qwen/qwen3.8-27b`, and how do you find
   the replacement?
2. Why does a failure after the first chunk not fail over?
3. Why is "measured on 10 requests, Silent power scheme" a weak basis for a deadline?
