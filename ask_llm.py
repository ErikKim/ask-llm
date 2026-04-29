#!/usr/bin/env python3
"""ask-llm: codex / gemini CLI retry+fallback wrapper.

Goal: get an answer reliably, even when a single CLI invocation fails
(empty stdout, timeout, rate limit, transient auth glitch).

Scope is intentionally narrow: codex and gemini only. No MCP, no Ollama.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

__version__ = "0.1.0"


def _log_file() -> Path:
    """Resolve the JSONL log path.

    Order:
      1. $ASK_LLM_LOG (file path)
      2. $XDG_CACHE_HOME/ask-llm/log.jsonl
      3. ~/.cache/ask-llm/log.jsonl
    """
    env = os.environ.get("ASK_LLM_LOG")
    if env:
        return Path(env).expanduser()
    base = os.environ.get("XDG_CACHE_HOME")
    if base:
        return Path(base).expanduser() / "ask-llm" / "log.jsonl"
    return Path.home() / ".cache" / "ask-llm" / "log.jsonl"


def _codex_env_candidates() -> list[Path]:
    """Optional .env files that may hold OPENAI_API_KEY for the codex CLI.

    Order:
      1. $ASK_LLM_CODEX_ENV_FILE
      2. ~/.codex/.env
      3. ./.env (current working directory)
    The first existing file wins; missing files are silently skipped.
    """
    out: list[Path] = []
    explicit = os.environ.get("ASK_LLM_CODEX_ENV_FILE")
    if explicit:
        out.append(Path(explicit).expanduser())
    out.append(Path.home() / ".codex" / ".env")
    out.append(Path.cwd() / ".env")
    return out


def load_env_with_codex_key() -> dict:
    env = os.environ.copy()
    for path in _codex_env_candidates():
        if not path.exists():
            continue
        try:
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                env.setdefault(k, v)
            break
        except OSError:
            continue
    return env


def log_attempt(record: dict) -> None:
    log_file = _log_file()
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        record["ts"] = datetime.now(timezone.utc).isoformat()
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def is_auth_error(stderr: str) -> bool:
    s = (stderr or "").lower()
    needles = (
        "401",
        "403",
        "unauthorized",
        "invalid api key",
        "invalid_api_key",
        "authentication",
        "expired",
        "not logged in",
        "please login",
    )
    return any(n in s for n in needles)


def is_rate_limit(stderr: str) -> bool:
    s = (stderr or "").lower()
    return "429" in s or "rate limit" in s or "quota" in s


def call_codex(prompt: str, timeout: int) -> Tuple[bool, str, str, int]:
    env = load_env_with_codex_key()
    try:
        r = subprocess.run(
            ["codex", "exec", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        ok = r.returncode == 0 and r.stdout.strip() != ""
        return ok, r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return False, "", f"timeout after {timeout}s", -1
    except FileNotFoundError:
        return False, "", "codex CLI not found in PATH", -2


def call_gemini(prompt: str, timeout: int) -> Tuple[bool, str, str, int]:
    try:
        r = subprocess.run(
            ["gemini", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        ok = r.returncode == 0 and r.stdout.strip() != ""
        return ok, r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return False, "", f"timeout after {timeout}s", -1
    except FileNotFoundError:
        return False, "", "gemini CLI not found in PATH", -2


PROVIDERS = {
    "codex": call_codex,
    "gemini": call_gemini,
}


def try_provider(name: str, prompt: str, max_retries: int, timeout: int) -> Tuple[bool, str, str]:
    """Attempt one provider with retries.

    Returns (ok, output_or_lasterror, reason_tag).
    reason_tag is one of: "ok", "auth", "exhausted".
    """
    last_err = ""
    for attempt in range(1, max_retries + 1):
        t0 = time.time()
        ok, out, err, code = PROVIDERS[name](prompt, timeout)
        elapsed = time.time() - t0

        log_attempt(
            {
                "provider": name,
                "attempt": attempt,
                "ok": ok,
                "exit": code,
                "elapsed_s": round(elapsed, 2),
                "stderr_head": (err or "")[:300],
                "stdout_len": len(out or ""),
            }
        )

        if ok:
            return True, out, "ok"

        last_err = err.strip() if err else f"empty stdout (exit={code})"

        if is_auth_error(err):
            return False, f"auth: {last_err}", "auth"

        if attempt < max_retries:
            base = 2 ** attempt
            if is_rate_limit(err):
                base = min(60, base * 4)
            backoff = min(30, base + random.uniform(0, 1))
            time.sleep(backoff)

    return False, last_err, "exhausted"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="LLM CLI retry+fallback wrapper (codex, gemini only)",
    )
    ap.add_argument(
        "prompt",
        nargs="?",
        help="prompt text. Use '-' or omit to read from stdin.",
    )
    ap.add_argument(
        "--provider",
        choices=["auto", "codex", "gemini"],
        default="auto",
        help="auto = try codex then gemini (default)",
    )
    ap.add_argument(
        "--retries",
        type=int,
        default=3,
        help="retries per provider (default: 3)",
    )
    ap.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="per-call timeout in seconds (default: 120)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="emit JSON {provider, output} on success",
    )
    ap.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    args = ap.parse_args()

    if not args.prompt or args.prompt == "-":
        prompt = sys.stdin.read()
    else:
        prompt = args.prompt

    if not prompt or not prompt.strip():
        print("ERROR: empty prompt", file=sys.stderr)
        return 2

    chain = ["codex", "gemini"] if args.provider == "auto" else [args.provider]

    errors = []
    for name in chain:
        ok, out, _reason = try_provider(name, prompt, args.retries, args.timeout)
        if ok:
            if args.json:
                print(json.dumps({"provider": name, "output": out}, ensure_ascii=False))
            else:
                sys.stdout.write(out)
                if not out.endswith("\n"):
                    sys.stdout.write("\n")
            return 0
        errors.append(f"[{name}] {out}")

    print("ERROR: all providers failed.", file=sys.stderr)
    for e in errors:
        print(f"  {e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
