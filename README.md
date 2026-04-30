# ask-llm

![hero](docs/hero.png)

**Claude 한 세션 안에서 [`codex`](https://github.com/openai/codex)(GPT) 와 [`gemini`](https://github.com/google-gemini/gemini-cli) 를 에이전트처럼 부르는 작은 래퍼.**
평소엔 Claude 가 직접 답하고, 자기가 못 하는 일이 있을 때만 다른 친구한테 부탁합니다.
부수효과로 자동 재시도 + 폴백까지 같이 따라옵니다.

[English README →](README.en.md)

설계는 일부러 좁게 잡았어요:

- 두 친구만 — `codex`(OpenAI) / `gemini`(Google).
- MCP·Ollama·스트리밍·대화 컨텍스트 안 건드림. one-shot 전용.
- Python 표준 라이브러리만. 외부 의존성 0개.
- 코드는 단일 파일 `ask_llm.py`.

## 누구에게 부탁할까

평소엔 Claude 가 직접 답해요. **Claude 가 자기 능력으로 못 하는 일** 일 때만 친구를 부르죠.

| 일 | 부르는 친구 | 이유 |
| --- | --- | --- |
| 그림 그려줘 (PNG 출력) | **codex** | OpenAI Images API 로 픽셀 합성 가능 |
| 이 영상 / 음성 분석해줘 | **gemini** | Gemini 의 native 동영상·오디오 입력 |
| 1M 토큰짜리 문서 요약 | **gemini** | Gemini 1.5 Pro 의 1M ctx |
| 이 코드 직접 돌려서 결과 보여줘 | **codex** / **gemini** | 둘 다 sandbox-write 보유 |

추론·코드 작성·요약·번역·도메인 분석 같은 영역은 호출하지 않아요. Claude 가
자기 컨텍스트로 직접 답하는 게 더 빠르고 일관됩니다.

## 그냥 말로 시키면 돼요

Claude Code 안에서 자연어로 부르면 자동 트리거:

- "이미지 만들어줘" → **codex**
- "GPT 한테 그려달라고 해" → **codex**
- "이 영상 분석해줘" → **gemini**
- "긴 문서 요약 시켜" → **gemini**

직접 부르고 싶으면:

```bash
ask-llm --provider codex  "..."
ask-llm --provider gemini "..."

# 자동 라우팅 (codex 시도 → 실패 시 gemini 폴백)
ask-llm "..."
```

## 가끔 친구가 답을 안 줘요

`codex exec` 와 `gemini -p` 는 평소엔 잘 도는데, 가끔 이렇게 깨져요:

- 빈 답이 옴 (네트워크 흔들)
- 너무 많이 물어서 거부 (429 rate-limit)
- 로그인 풀려서 거부 (401)
- 답이 너무 늦어 timeout

## 한 명이 안 되면 다른 친구에게

```
                 ┌───── codex ─────┐
prompt ─► auto ──┤                 ├──► 먼저 비어있지 않은 답이 나오는 쪽 채택
                 └───── gemini ────┘

provider 단위:  시도 1 ─► 시도 2 ─► 시도 3
                  └─ stderr 에 401/403/expired/"please login" 보이면 즉시 포기
                  └─ 429/rate limit/quota 신호면 백오프를 더 길게
                  └─ stdout 비어있음 / non-zero exit / timeout 은 재시도
```

- 한 친구한테 3번까지 다시 물어보고
- 로그인 만료면 바로 다른 친구로
- 너무 바쁜 친구면 잠깐 기다렸다가
- 둘 다 안 되면 솔직히 실패 알림 (exit 1)

`ask-llm` 은 jitter 들어간 지수 백오프로 다시 물어보고, 영구 인증 오류면
미련 없이 접고 바로 다음 친구한테 넘어갑니다. 한 번의 글리치 때문에 호출자
스크립트가 통째로 멈추지 않게 하는 게 전부예요.

## 설치

Python 3.9+ 필요. 외부 Python 의존성은 없어요.

이 레포는 두 가지 사용처를 동시에 지원해요.

- **Claude Code 스킬로 쓰기** — `SKILL.md` + `ask_llm.py` 두 파일이 핵심. `~/.claude/skills/ask-llm/` 에 떨어뜨리기만 하면 됨.
- **시스템 CLI로 쓰기** — 같은 `ask_llm.py` 가 `pipx`/`pip` 로도 깔립니다 (`ask-llm` 명령 노출).

### 방법 1 — Claude Code Skill 로 설치 (가장 빠름)

레포 자체를 그대로 `~/.claude/skills/ask-llm/` 으로 clone 하면 끝.
`SKILL.md` 와 `ask_llm.py` 가 그 폴더에 같이 자리잡고, Claude Code 가 알아서 인식해요.

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

또는 위에서 본 것처럼 Claude Code 안에서 그냥 말로 시켜도 자동 트리거.

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

`ask-llm` 쓰기 전에 두 CLI 가 단독으로 잘 도는지 한 번 확인해 보세요:

```bash
codex exec  "say hi"
gemini -p   "say hi"
```

## 옵션 정리

```bash
# 자동 폴백 (codex → gemini)
ask-llm "한 줄 요약 부탁: ..."

# provider 강제 지정
ask-llm --provider gemini "..."
ask-llm --provider codex  "..."

# stdin 으로 긴 프롬프트 입력
cat long_prompt.txt | ask-llm -

# 재시도 / 타임아웃 조정
ask-llm --timeout 60 --retries 5 "..."

# JSON 으로 받기 (어느 친구가 답했는지 알 수 있게)
ask-llm --json "..."
# {"provider": "codex", "output": "..."}
```

종료 코드:

| code | 의미 |
| ---- | ---- |
| `0`  | 성공 — `stdout` 이 LLM 답변 |
| `1`  | 모든 provider 실패 — `stderr` 에 마지막 에러 |
| `2`  | 빈 프롬프트 등 사용자 입력 오류 |

## 환경변수

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

- **추론·요약·번역·코드 작성을 외부 LLM 에 떠넘기기.** 그건 Claude 가 직접 답해요. 외부 호출은 Claude 가 못 하는 능력일 때만.
- **스트리밍 출력.** 답은 한 번에 한 덩어리로 옴.
- **대화 history / 멀티턴.** one-shot 만 — 컨텍스트 관리는 호출자(Claude) 책임.
- **provider 추가.** `codex` + `gemini` 만 유지하는 게 핵심. Anthropic / Mistral 필요하면 자매 스크립트로 따로 만들 것.
- **MCP 서버, 로컬 Ollama, llama.cpp.** 의도적 비대상.

## 라이선스

[MIT](LICENSE) © 2026 ErikKim
