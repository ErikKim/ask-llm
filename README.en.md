# ask-llm

![hero](docs/hero.png)

**A small wrapper that lets Claude call [`codex`](https://github.com/openai/codex) (GPT) and [`gemini`](https://github.com/google-gemini/gemini-cli) like agents inside one session.**
Claude answers most things directly. Friends are only called when there's something Claude can't do.
Auto-retry and fallback come along for free.

Design is intentionally narrow:

- Two friends only — `codex` (OpenAI) / `gemini` (Google).
- No MCP, no Ollama, no streaming, no conversation context. One-shot only.
- Python stdlib only. Zero external dependencies.
- The code is one file: `ask_llm.py`.

[한국어 README →](README.md)

## Who do I ask?

Claude answers most things directly. Friends are called **only for what Claude can't do**.

| Task | Friend | Why |
| --- | --- | --- |
| Draw me an image (PNG out) | **codex** | Can hit OpenAI Images API for pixel synthesis |
| Analyze this video / audio | **gemini** | Native video & audio input |
| Summarize a 1M-token doc | **gemini** | Gemini 1.5 Pro 1M ctx |
| Actually run this code | **codex** / **gemini** | Both have sandbox-write |

Reasoning, code authoring, summarization, translation, domain analysis — none of
those go out. Claude answers them in-context, faster and more consistently.

## Just ask in plain words

In Claude Code, plain-language requests trigger automatically:

- "make me an image" → **codex**
- "have GPT draw it" → **codex**
- "analyze this video" → **gemini**
- "summarize this long doc" → **gemini**

Or call directly:

```bash
ask-llm --provider codex  "..."
ask-llm --provider gemini "..."

# auto routing (try codex → fall back to gemini)
ask-llm "..."
```

## Sometimes a friend just won't answer

`codex exec` and `gemini -p` usually work, but occasionally:

- blank answer (flaky network)
- too many calls, gets refused (429 rate-limit)
- login expired, gets refused (401)
- too slow, times out

## One friend down → ask the other

```
                 ┌───── codex ─────┐
prompt ─► auto ──┤                 ├──► first non-empty answer wins
                 └───── gemini ────┘

per provider:    try 1 ─► try 2 ─► try 3
                  └─ stderr shows 401/403/expired/"please login" → give up immediately
                  └─ 429/rate limit/quota → longer backoff
                  └─ empty stdout / non-zero exit / timeout → retry
```

- Try the same friend up to 3 times
- Login expired? Switch to the other friend immediately
- Friend too busy? Wait a bit, try again
- Both down? Fail loud — no faking (exit 1)

`ask-llm` retries with jittered exponential backoff and bails fast on permanent
auth errors so it can move to the next friend. The whole point: one transient
glitch shouldn't take down the caller's script.

## Install

Python 3.9+. No external Python deps.

This repo serves two consumers at once:

- **As a Claude Code skill** — `SKILL.md` + `ask_llm.py` are the two files that matter. Drop into `~/.claude/skills/ask-llm/` and you're done.
- **As a system CLI** — same `ask_llm.py` installs via `pipx`/`pip` (exposes `ask-llm`).

### Option 1 — Claude Code Skill (fastest)

Just clone the repo into `~/.claude/skills/ask-llm/`. `SKILL.md` and `ask_llm.py`
land in that folder, and Claude Code picks them up automatically.

```bash
# user-level (shared across all projects)
git clone https://github.com/ErikKim/ask-llm.git ~/.claude/skills/ask-llm

# or per-project
cd <your-project>
git clone https://github.com/ErikKim/ask-llm.git .claude/skills/ask-llm
```

Update:

```bash
cd ~/.claude/skills/ask-llm && git pull
```

Call as documented in SKILL.md:

```bash
python3 ~/.claude/skills/ask-llm/ask_llm.py "give me a one-liner: ..."
```

Or — as shown above — just ask in plain words inside Claude Code and it auto-triggers.

### Option 2 — `pipx` (isolated system CLI)

```bash
pipx install git+https://github.com/ErikKim/ask-llm.git
ask-llm --version
```

### Option 3 — `pip` (editable / dev)

```bash
git clone https://github.com/ErikKim/ask-llm.git
cd ask-llm
pip install -e .          # `ask-llm` lands on PATH
ask-llm --version
```

### Option 4 — run the script directly (no install)

```bash
git clone https://github.com/ErikKim/ask-llm.git
python3 ask-llm/ask_llm.py "hello"
```

### Upstream CLIs

You need at least one of these on `PATH`, signed in:

| provider | install | sign-in |
| -------- | ------- | ------- |
| `codex`  | [Codex CLI README](https://github.com/openai/codex) | `codex login` (or `OPENAI_API_KEY` env var) |
| `gemini` | [Gemini CLI README](https://github.com/google-gemini/gemini-cli) | `gemini auth login` |

Sanity-check that each CLI works on its own before reaching for `ask-llm`:

```bash
codex exec  "say hi"
gemini -p   "say hi"
```

## Options

```bash
# auto fallback (codex → gemini)
ask-llm "give me a one-liner: ..."

# force a provider
ask-llm --provider gemini "..."
ask-llm --provider codex  "..."

# stdin for long prompts
cat long_prompt.txt | ask-llm -

# tune retry / timeout
ask-llm --timeout 60 --retries 5 "..."

# JSON output (so the caller knows which friend answered)
ask-llm --json "..."
# {"provider": "codex", "output": "..."}
```

Exit codes:

| code | meaning |
| ---- | ------- |
| `0`  | success — `stdout` is the LLM answer |
| `1`  | all providers failed — `stderr` has the last error |
| `2`  | bad input (empty prompt, etc.) |

## Environment variables

All optional.

| Variable                   | Default                             | Purpose |
| -------------------------- | ----------------------------------- | ------- |
| `ASK_LLM_LOG`              | `~/.cache/ask-llm/log.jsonl`        | Per-attempt JSONL log path |
| `ASK_LLM_CODEX_ENV_FILE`   | `~/.codex/.env`, then `./.env`      | Extra `.env` to source before calling `codex` (e.g. `OPENAI_API_KEY`) |

If `XDG_CACHE_HOME` is set, the default log path becomes
`$XDG_CACHE_HOME/ask-llm/log.jsonl`.

## Logs

Each attempt is one JSONL line:

```json
{"provider":"codex","attempt":1,"ok":false,"exit":1,"elapsed_s":7.42,"stderr_head":"...","stdout_len":0,"ts":"2026-04-29T08:00:00+00:00"}
```

After a few days of dogfooding, this is a handy aggregation:

```bash
jq -r 'select(.ok==false) | "\(.provider) \(.stderr_head)"' \
  ~/.cache/ask-llm/log.jsonl | sort | uniq -c | sort -rn
```

## What this intentionally won't do

- **Hand off reasoning, summarization, translation, or coding to an external LLM.** Claude answers those in-context. External calls are reserved for capabilities Claude doesn't have.
- **Streaming output.** The answer arrives in one chunk.
- **Conversation history / multi-turn.** One-shot only — context is the caller's (Claude's) responsibility.
- **More providers.** Keeping it `codex` + `gemini` is the point. Need Anthropic / Mistral? Write a sister script.
- **MCP servers, local Ollama, llama.cpp.** Out of scope on purpose.

## License

[MIT](LICENSE) © 2026 ErikKim
