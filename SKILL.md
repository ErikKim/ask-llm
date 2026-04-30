---
name: ask-llm
description: codex CLI(GPT) / gemini CLI에 프롬프트를 보낼 때 빈 응답·타임아웃·rate-limit·인증 만료 등으로 실패하는 경우를 막기 위한 retry+fallback wrapper. 자율 모드는 Claude가 직접 처리하고, Claude가 완전히 할 수 없는 능력(이미지 생성·동영상 분석·1M 컨텍스트 등) 또는 사용자가 명시적으로 외부 LLM을 지시했을 때만 이 스킬을 쓴다. 대상은 codex/gemini CLI 두 개뿐 — MCP나 Ollama는 다루지 않는다. 사용자가 "GPT/Gemini로 물어봐줘", "이미지 생성해줘", "/ask-llm" 류 요청 시 트리거.
---

# ask-llm

`codex exec` / `gemini -p` 두 CLI를 안정적으로 호출하기 위한 retry+fallback 래퍼.
**답을 얻으면 끝**이라는 단순 목표로 설계됨. 추가 provider 확장 금지.

## 사용 정책 — 자율은 Claude, 외부는 능력 또는 명시 지시일 때만

자율 모드의 기본은 **Claude self-answer** 다. 다음 두 경우에만 ask-llm 으로 외부 LLM에 위임한다.

1. **사용자가 명시적으로 지시** — `/ask-llm "..."`, "GPT한테 물어봐", "Gemini 의견도 받아줘", "이 부분은 코덱스로" 류.
2. **Claude가 완전히 할 수 없는 능력이 필요한 경우** — 아래 매핑 표 참조. 이 영역은 Claude 자율로 답할 수 없으므로 codex/gemini 가 대체.

그 외에는 외부 호출하지 않는다. 모든 외부 호출에는 비용/지연이 있고, 일반 추론·코드·요약·계획 같은 영역은 Claude 가 자기 컨텍스트로 직접 답하는 게 빠르고 일관적이다.

## Claude가 완전히 할 수 없는 능력 → 대체 LLM

> ⚠️ 아래 표는 Claude/GPT/Gemini 셋이 토의해 도출한 결과로, [`ask-llm/docs/triage.md`](docs/triage.md) 에 토의 원본·각자 self-report·합의 근거가 보존되어 있다. 환경/모델이 바뀌면 `docs/triage.md` 의 절차를 따라 재토의 후 갱신.

| 능력 | Claude가 못 하는 이유 | 대체 LLM | 호출 예 |
| --- | --- | --- | --- |
| **이미지 생성 (PNG 출력)** | Claude는 텍스트만 출력. 픽셀 합성 불가. | **codex** — `codex exec` sandbox 안에서 OpenAI Images API(gpt-image-2)를 호출해 PNG 파일을 떨어뜨릴 수 있음. | `ask-llm --provider codex "1024x1024 이미지 1장: ... 저장 경로: ..."` |
| **동영상 프레임 시퀀스 분석** | Claude vision 은 still image only. 시간축 추적 불가. | **gemini** — Gemini Video Pro는 mp4 입력 + 프레임 sequence reasoning 지원. | `ask-llm --provider gemini "이 mp4의 0:00~0:05 프레임 sequence ..."` |
| **오디오 byte 직해석** (음성 톤·화자·환경음) | Claude는 텍스트만 처리. WAV/MP3 직접 reasoning 불가. | **gemini** — Gemini Native Multimodal Audio. | `ask-llm --provider gemini "이 wav 의 화자 sentiment + 환경음 분류 ..."` |
| **1M 토큰 단일 컨텍스트** | Claude 200k 한계. 그 이상은 압축 손실. | **gemini** — Gemini 1.5 Pro 1M 컨텍스트로 단일 입력 처리. | `cat huge.txt \| ask-llm --provider gemini -` |
| **자기 sandbox 안에서 임의 코드 실행** | Claude 본 세션은 sandbox 직접 호출 불가 (도구 경계). | **codex 또는 gemini** — 둘 다 자기 sandbox-write 보유. 본 레포는 자산/코드 생성에 codex 가 더 자주 쓰임. | `ask-llm --provider codex "이 스크립트 실행하고 결과 stdout: ..."` |

이 매핑은 능력 부재 영역만 다룬다. **추론·코드 작성·요약·계획·번역·도메인 분석** 같은 영역은 Claude 자율로 처리하고 외부 호출하지 않는다 — `WebFetch`/`WebSearch` 같은 도구로 보완 가능한 실시간 grounding 도 포함.

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

## 둘 다 실패했을 때 (exit 1) 처리

ask-llm 이 1순위·폴백 모두 소진해 종료 코드 1을 반환하면 호출자가 어떻게 처리할지는 **그 영역이 자율 가능한가** 에 따라 다르다.

**A. Claude 자율로 답할 수 있는 영역인데 사용자가 외부 LLM 을 명시 지시했던 경우**
1. 호출자(Claude) 본인의 추론으로 답을 메운다.
2. 산출물에 `* ask-llm fallback to Claude self-answer (외부 LLM 모두 실패)` 명시.
3. 절대 "외부 LLM 의견인 척" 위장 금지.

**B. Claude 가 완전히 할 수 없는 능력 영역 (이미지 생성, 동영상 분석, 1M ctx 등)**
1. 자율 fallback 불가 — 능력 자체가 없음.
2. 실패 처리하고 사용자에게 보고: "{능력} 호출이 둘 다 실패했습니다. 토큰 고갈 / 인증 만료 / 모델 가용성 등을 확인해 주세요."
3. **거짓으로 만들어내지 않는다** — 이미지 못 만든 채로 "만들었습니다" 라고 위장 금지.

### 영구 고갈 신호 (참고용 키워드)

stderr 에 다음 키워드 중 1개 이상이 보이고 `--retries 3` 모두 실패한 경우, transient 가 아니라 영구 quota/auth 고갈로 본다:
- codex: `insufficient_quota`, `exceeded your current quota`, `out of credits`, `billing`, `payment required`, `usage limit reached`
- gemini: `RESOURCE_EXHAUSTED`, `quota exceeded`, `free tier limit`, `daily limit`
- 공통: "토큰 없", "잔여 없", "한도 초과"

`ask-llm` 코드는 이 분기를 자동화하지 않는다 — 호출자별로 처리 정책(A vs B)이 다르기 때문.

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
