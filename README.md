# ask-llm

![hero](docs/hero.png)

A small, dependency-free retry + fallback wrapper around the
[`codex`](https://github.com/openai/codex) and [`gemini`](https://github.com/google-gemini/gemini-cli)
command-line tools. **Get an answer, even when a single call fails.**

`ask-llm` is intentionally narrow:

- Two providers only — `codex` (OpenAI) and `gemini` (Google).
- No MCP, no Ollama, no streaming, no chat history.
- Pure Python standard library. No `pip install` of network deps required.
- One file: `ask_llm.py`.

## Why

`codex exec` and `gemini -p` work great until they don't:

- Empty stdout on a flaky network.
- 429 rate-limit on a noisy minute.
- A single auth glitch right after a token refresh.
- A 2-minute timeout because the model wandered off.

`ask-llm` retries with jittered exponential backoff, fails fast on permanent
auth errors, and falls back to the other provider so a single transient hiccup
doesn't crash your script.

## Install

```bash
git clone https://github.com/<your-user>/ask-llm.git
cd ask-llm
pip install -e .          # exposes the `ask-llm` command
```

Or use the script directly without installing — it has no third-party deps:

```bash
python3 ask_llm.py "hello"
```

You'll also need at least one of the upstream CLIs on your `PATH`:

- `codex` — install via the [Codex CLI README](https://github.com/openai/codex)
- `gemini` — install via the [Gemini CLI README](https://github.com/google-gemini/gemini-cli)

## Usage

```bash
# Auto: try codex first, fall back to gemini.
ask-llm "Summarize this in one sentence: ..."

# Pick one explicitly.
ask-llm --provider gemini "..."
ask-llm --provider codex  "..."

# Long prompt from stdin.
cat long_prompt.txt | ask-llm -

# Tune retry / timeout.
ask-llm --timeout 60 --retries 5 "..."

# Get JSON back so a calling script can see which provider answered.
ask-llm --json "..."
# {"provider": "codex", "output": "..."}
```

Exit codes:

| code | meaning |
| ---- | ------- |
| `0`  | success — `stdout` is the LLM answer |
| `1`  | every provider failed — last error on `stderr` |
| `2`  | empty prompt or other usage error |

## How it routes

```
                 ┌───── codex ─────┐
prompt ─► auto ──┤                 ├──► first non-empty answer wins
                 └───── gemini ────┘

per provider:  attempt 1 ─► attempt 2 ─► attempt 3
                  └─ fail fast on 401/403/expired/"please login"
                  └─ longer backoff when stderr looks like 429/rate limit/quota
                  └─ retry on empty stdout / non-zero exit / timeout
```

## Configuration (env)

All optional.

| variable                  | default                          | purpose |
| ------------------------- | -------------------------------- | ------- |
| `ASK_LLM_LOG`             | `~/.cache/ask-llm/log.jsonl`     | per-attempt JSONL log path |
| `ASK_LLM_CODEX_ENV_FILE`  | `~/.codex/.env`, then `./.env`   | extra `.env` file scanned for `OPENAI_API_KEY` before invoking `codex` |

If `XDG_CACHE_HOME` is set, the default log path becomes
`$XDG_CACHE_HOME/ask-llm/log.jsonl`.

## Logging

Every attempt is appended to a JSONL file as a single line:

```json
{"provider":"codex","attempt":1,"ok":false,"exit":1,"elapsed_s":7.42,"stderr_head":"...","stdout_len":0,"ts":"2026-04-29T08:00:00+00:00"}
```

Useful for spotting failure patterns over weeks of dogfood:

```bash
jq -r 'select(.ok==false) | "\(.provider) \(.stderr_head)"' ~/.cache/ask-llm/log.jsonl | sort | uniq -c | sort -rn
```

## What it deliberately does NOT do

- Streaming output. Answer comes back in one chunk.
- Chat history / multi-turn. One-shot only — your caller threads context.
- New providers. Stay focused on `codex` + `gemini`. Need Anthropic / Mistral?
  Wrap them in a sister script.
- MCP servers, local Ollama, llama.cpp. Out of scope by design.

## License

[MIT](LICENSE) © 2026 ErikKim
