# ask-llm

![hero](docs/hero.png)

[`codex`](https://github.com/openai/codex)(GPT) 와 [`gemini`](https://github.com/google-gemini/gemini-cli) CLI를
**자동 재시도 + 한쪽 죽으면 다른 쪽으로 폴백** 시켜 주는 작은 래퍼입니다.
**한 번은 실패해도, 답은 받고 끝낸다** 가 유일한 목표.

설계 원칙은 의도적으로 좁게:

- 두 provider만 지원 — `codex`(OpenAI) / `gemini`(Google).
- MCP·Ollama·스트리밍·대화 컨텍스트 안 건드림. one-shot 전용.
- Python 표준 라이브러리만. 외부 의존성 0개.
- 코드는 단일 파일 `ask_llm.py`.

## 왜 필요한가

`codex exec` 와 `gemini -p` 는 평소엔 잘 동작하지만, 가끔 이렇게 죽습니다:

- 네트워크 흔들려서 stdout이 그냥 빈 문자열로 옴
- 1분 동안 호출이 몰려 429 rate-limit
- 토큰 갱신 직후 한 번만 401 떠서 스크립트가 통째로 멈춤
- 모델이 길을 잃고 timeout

`ask-llm` 은 jitter가 들어간 지수 백오프로 재시도하고, 영구 인증 오류는
바로 포기해 빠르게 다음 provider로 넘어갑니다. 일시적인 한 번의 글리치 때문에
사용 측 스크립트가 멈추지 않게 하는 게 전부입니다.

## 설치

Python 3.9+ 필요. 외부 Python 의존성은 없습니다.

이 레포는 두 가지 사용처를 동시에 지원합니다.

- **Claude Code 스킬로 사용** — `SKILL.md` + `ask_llm.py` 두 파일이 핵심. 사용자가 `~/.claude/skills/ask-llm/` 에 떨어지기만 하면 됨.
- **시스템 CLI로 사용** — 같은 `ask_llm.py` 가 `pipx`/`pip` 로도 설치 가능 (`ask-llm` 명령 노출).

### 방법 1 — Claude Code Skill 로 설치 (가장 빠름)

레포 자체를 그대로 `~/.claude/skills/ask-llm/` 으로 clone 하면 끝납니다.
`SKILL.md` 와 `ask_llm.py` 가 그 폴더에 함께 자리잡고, Claude Code 가 자동 인식합니다.

```bash
# user-level (모든 프로젝트에서 공통 사용)
git clone https://github.com/ErikKim/ask-llm.git ~/.claude/skills/ask-llm

# 또는 특정 프로젝트 단위
cd <your-project>
git clone https://github.com/ErikKim/ask-llm.git .claude/skills/ask-llm
```

업데이트:

```bash
cd ~/.claude/skills/ask-llm && git pull
```

호출은 SKILL.md 안내대로:

```bash
python3 ~/.claude/skills/ask-llm/ask_llm.py "한 줄 요약 부탁: ..."
```

또는 Claude Code 안에서 `/ask-llm` / "GPT한테 물어봐" 류 자연어 요청 시 자동 트리거.

### 방법 2 — `pipx` (시스템 CLI 로 격리 설치)

```bash
pipx install git+https://github.com/ErikKim/ask-llm.git
ask-llm --version
```

### 방법 3 — `pip` (수정 / 개발용)

```bash
git clone https://github.com/ErikKim/ask-llm.git
cd ask-llm
pip install -e .          # `ask-llm` 명령이 PATH 에 노출됨
ask-llm --version
```

### 방법 4 — 스크립트 직접 실행 (설치 없이)

```bash
git clone https://github.com/ErikKim/ask-llm.git
python3 ask-llm/ask_llm.py "hello"
```

### upstream CLI 준비

`PATH` 에 아래 둘 중 하나는 있어야 하고 로그인되어 있어야 합니다.

| provider | 설치 | 로그인 |
| -------- | ---- | ------ |
| `codex`  | [Codex CLI README](https://github.com/openai/codex) | `codex login` (또는 `OPENAI_API_KEY` 환경변수) |
| `gemini` | [Gemini CLI README](https://github.com/google-gemini/gemini-cli) | `gemini auth login` |

`ask-llm` 을 쓰기 전에 두 CLI가 단독으로 잘 동작하는지 먼저 확인하세요:

```bash
codex exec  "say hi"
gemini -p   "say hi"
```

## 사용법

```bash
# 기본 — 자동 폴백 (codex 시도 후 실패 시 gemini)
ask-llm "한 줄 요약 부탁: ..."

# provider 강제 지정
ask-llm --provider gemini "..."
ask-llm --provider codex  "..."

# stdin 으로 긴 프롬프트 입력
cat long_prompt.txt | ask-llm -

# 재시도 / 타임아웃 조정
ask-llm --timeout 60 --retries 5 "..."

# JSON 으로 받기 (어느 provider가 답했는지 호출자가 알 수 있게)
ask-llm --json "..."
# {"provider": "codex", "output": "..."}
```

종료 코드:

| code | 의미 |
| ---- | ---- |
| `0`  | 성공 — `stdout` 이 LLM 답변 |
| `1`  | 모든 provider 실패 — `stderr` 에 마지막 에러 |
| `2`  | 빈 프롬프트 등 사용자 입력 오류 |

## 라우팅 동작

```
                 ┌───── codex ─────┐
prompt ─► auto ──┤                 ├──► 먼저 비어있지 않은 답이 나오는 쪽 채택
                 └───── gemini ────┘

provider 단위:  시도 1 ─► 시도 2 ─► 시도 3
                  └─ stderr 에 401/403/expired/"please login" 보이면 즉시 포기
                  └─ 429/rate limit/quota 신호면 백오프를 더 길게
                  └─ stdout 비어있음 / non-zero exit / timeout 은 재시도
```

## 환경변수 설정

전부 선택사항입니다.

| 변수                       | 기본값                              | 용도 |
| -------------------------- | ----------------------------------- | ---- |
| `ASK_LLM_LOG`              | `~/.cache/ask-llm/log.jsonl`        | 시도별 JSONL 로그 경로 |
| `ASK_LLM_CODEX_ENV_FILE`   | `~/.codex/.env`, 그 다음 `./.env`   | `codex` 호출 전 `OPENAI_API_KEY` 등을 읽어올 추가 `.env` 파일 |

`XDG_CACHE_HOME` 이 설정돼 있으면 기본 로그 경로는
`$XDG_CACHE_HOME/ask-llm/log.jsonl` 이 됩니다.

## 로그

매 시도가 한 줄 JSONL 로 누적됩니다:

```json
{"provider":"codex","attempt":1,"ok":false,"exit":1,"elapsed_s":7.42,"stderr_head":"...","stdout_len":0,"ts":"2026-04-29T08:00:00+00:00"}
```

며칠 dogfood 한 뒤 실패 패턴을 보고 싶을 때 이렇게 집계하면 편합니다:

```bash
jq -r 'select(.ok==false) | "\(.provider) \(.stderr_head)"' \
  ~/.cache/ask-llm/log.jsonl | sort | uniq -c | sort -rn
```

## 의도적으로 안 하는 것

- 스트리밍 출력. 답은 한 번에 한 덩어리로 옴.
- 대화 history / 멀티턴. one-shot 만 — 컨텍스트 관리는 호출자 책임.
- provider 추가. `codex` + `gemini` 만 유지하는 게 핵심. Anthropic / Mistral
  필요하면 자매 스크립트로 따로 만들 것.
- MCP 서버, 로컬 Ollama, llama.cpp. 의도적 비대상.

## 라이선스

[MIT](LICENSE) © 2026 ErikKim
