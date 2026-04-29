---
name: ask-llm
description: codex CLI(GPT) / gemini CLI에 프롬프트를 보낼 때 빈 응답·타임아웃·rate-limit·인증 만료 등으로 실패하는 경우를 막기 위한 retry+fallback wrapper. 답을 얻을 때까지 자동 재시도하고, 한 provider가 죽으면 다른 provider로 자동 전환한다. 대상은 codex/gemini CLI 두 개뿐 — MCP나 Ollama는 다루지 않는다. 사용자가 "GPT/Gemini로 물어봐줘", "안정적으로 LLM 호출", "한 줄 LLM 답변 받아줘", "/ask-llm" 류 요청 시 트리거.
---

# ask-llm

`codex exec` / `gemini -p` 두 CLI를 안정적으로 호출하기 위한 retry+fallback 래퍼.
**답을 얻으면 끝**이라는 단순 목표로 설계됨. 추가 provider 확장 금지.

## 언제 사용하는가

- 사용자가 `/ask-llm "프롬프트"` 형태로 직접 호출
- 사용자가 "GPT한테 물어봐", "Gemini로 요약 받아줘" 같은 요청을 했는데 단일 호출이 종종 실패하는 환경
- 다른 스킬/에이전트가 외부 LLM에 한 줄 질의를 보내야 할 때 (codex/gemini만)

**사용하지 않는 경우**:
- MCP 도구 호출 (Claude 자체 mcp__* 도구는 그대로 사용)
- 로컬 Ollama 호출
- 스트리밍/대화 컨텍스트 유지 필요한 경우 (one-shot 전용)

## 호출 방법

설치 위치에 따라 둘 중 한 가지 경로로 호출한다.

```bash
# user-level skill (권장 — 한 번 clone 으로 모든 프로젝트에서 사용)
python3 ~/.claude/skills/ask-llm/ask_llm.py "한 줄 요약을 작성해줘"

# 프로젝트 단위 설치 시
python3 .claude/skills/ask-llm/ask_llm.py "..."

# pipx/pip 설치 시 (PATH 노출)
ask-llm "..."
```

옵션은 호출 형태와 무관하게 동일하다.

```bash
# 특정 provider 강제
ask-llm --provider gemini "..."
ask-llm --provider codex  "..."

# stdin 으로 긴 프롬프트
cat long_prompt.txt | ask-llm -

# 타임아웃 / 재시도 횟수 조정
ask-llm --timeout 60 --retries 5 "..."

# JSON 출력 (provider 정보 포함)
ask-llm --json "..."
# → {"provider": "codex", "output": "..."}
```

종료 코드:
- `0`: 성공 (stdout = LLM 답변)
- `1`: 모든 provider 실패 (stderr = 마지막 에러)
- `2`: 빈 프롬프트 등 사용자 입력 오류

## 동작 원리

1. **Provider chain** — `auto`(기본)는 `[codex, gemini]` 순서. `--provider`로 단일 지정 가능.
2. **Per-provider retry** — 기본 3회. `2^n + jitter` 지수 백오프(최대 30초).
3. **실패 판정** (재시도 트리거):
   - non-zero exit code
   - timeout (기본 120초)
   - stdout이 공백/빈 문자열
   - stderr에 `429` / `rate limit` 포함
4. **빠른 fallback** — stderr에 `401`/`403`/`unauthorized`/`invalid api key`/`expired` 포함 시 같은 provider 재시도 스킵하고 즉시 다음 provider로.
5. **로깅** — 기본 `~/.cache/ask-llm/log.jsonl` 에 매 시도 기록 (provider, exit, elapsed, stderr 앞 300자, stdout 길이). `ASK_LLM_LOG` 환경변수로 변경 가능.

## 토큰/쿼터 고갈 처리 (호출자 가이드)

`ask-llm` 자체는 transient rate limit 과 영구 quota 고갈을 강하게 구분하지 않고, 양쪽 모두 retry → fallback 순으로 처리한다. 다만 **호출자(에이전트)** 가 영구 고갈을 감지하고 별도 분기로 가야 할 때가 있다.

호출자가 **"토큰 고갈 = 영구 실패"** 로 해석해야 하는 신호:
- stderr 에 다음 키워드 중 1개 이상이 보이고, 동시에 `--retries 3` 모두 실패한 경우:
  - codex: `insufficient_quota`, `exceeded your current quota`, `out of credits`, `billing`, `payment required`, `usage limit reached`
  - gemini: `RESOURCE_EXHAUSTED`, `quota exceeded`, `free tier limit`, `daily limit`
  - 공통: 한국어로 "토큰 없", "잔여 없", "한도 초과"
- ask-llm 종료 코드가 1 이고 위 패턴이 stderr 에 포함됨

이런 경우 호출자는:
1. 다른 provider 로 한 번 더 시도(이미 ask-llm 가 시도했지만 명시 호출 1회 추가).
2. 그래도 실패면 호출자(에이전트) 본인의 추론으로 답을 메우되, **외부 LLM 응답이 아니라 self-fallback 임을 산출물에 명시** 한다.
3. 절대 "외부 LLM 의견인 척" 위장 금지.

`ask-llm` 코드는 이 분기를 자동화하지 않는다 — provider 한정 신호이고 호출자별로 처리 정책이 다르기 때문. 위 키워드 리스트만 표준 규약으로 사용.

## 환경 의존성

- `codex` CLI 설치 + `OPENAI_API_KEY` 인증
  - `~/.codex/.env` 또는 `./.env` 의 `OPENAI_API_KEY` 자동 로드
  - `ASK_LLM_CODEX_ENV_FILE` 환경변수로 .env 위치 명시 가능
  - 또는 셸 환경변수에 직접 export
- `gemini` CLI 설치 + 자체 인증 완료 (`gemini auth login`)

둘 중 하나만 살아있어도 동작 (auto 모드는 살아있는 쪽으로 fallback).

## 실패 패턴 분석

로그가 쌓이면 다음 명령으로 통계 확인 가능:

```bash
# 최근 50건 요약
tail -50 ~/.cache/ask-llm/log.jsonl | jq -r '[.provider, .ok, .exit, .elapsed_s] | @tsv'

# provider 별 성공률
jq -s 'group_by(.provider) | map({provider: .[0].provider, total: length, ok: map(select(.ok)) | length})' ~/.cache/ask-llm/log.jsonl
```

실패 패턴이 특정 provider 에 몰린다면 인증 갱신 / CLI 업그레이드 등 외부 조치 필요.

## 확장 금지 원칙

이 스킬의 scope:
- ✅ codex CLI (`codex exec`)
- ✅ gemini CLI (`gemini -p`)
- ❌ MCP 도구
- ❌ Ollama / 로컬 LLM
- ❌ 스트리밍
- ❌ 대화 컨텍스트 유지

추가 provider 가 필요해 보이면 새 스킬을 만들 것. 이 스킬을 부풀리지 말 것.
