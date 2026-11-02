"""LLM 호출의 단일 출입구.

모드(CLAUSETOWER_LLM): claude-code(CLI, 구독) | anthropic(SDK, ANTHROPIC_BASE_URL로 사내 호환 게이트웨이 가능) |
openai(OpenAI 호환 chat/completions + tools, 사내 LLM용: CLAUSETOWER_OPENAI_BASE_URL, CLAUSETOWER_OPENAI_API_KEY) | mock(결정적) |
auto(API 키 → 사내 엔드포인트(CLAUSETOWER_OPENAI_BASE_URL) → claude CLI → mock).
구조화 출력은 pydantic 스키마로 검증한다. 실패하면 1회 재시도하고, 그래도 안 되면 mock 함수로 대체하고 로그에 남긴다.
경고 로그에는 모델 출력·계약 본문을 싣지 않는다(오류 종류·필드 위치·길이·종료 코드만). 원문 일부는 DEBUG 수준에서만 남긴다.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

log = logging.getLogger("clausetower.llm")
T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = os.environ.get("CLAUSETOWER_MODEL", "claude-opus-5-5")
CLAUDE_BIN = os.environ.get("CLAUSETOWER_CLAUDE_BIN", "claude")
CLAUDE_TIMEOUT = int(os.environ.get("CLAUSETOWER_CLAUDE_TIMEOUT", "600"))
CLAUDE_DISALLOWED_TOOLS = "Bash,Read,Edit,Write,MultiEdit,Glob,Grep,WebSearch,WebFetch,Agent,Task,NotebookEdit,TodoWrite,Skill"


def _err_summary(e: BaseException) -> str:
    """로그·오류 메시지용 요약. 검증 오류는 입력값(모델 출력)을 빼고 필드 위치만 남긴다."""
    if isinstance(e, ValidationError):
        locs = ", ".join(".".join(str(p) for p in err.get("loc", ())) or "(root)" for err in e.errors()[:5])
        return f"ValidationError({e.error_count()}건: {locs})"
    if isinstance(e, json.JSONDecodeError):
        return f"JSONDecodeError(줄 {e.lineno}, 열 {e.colno}, 길이 {len(e.doc or '')})"
    return f"{type(e).__name__}: {str(e)[:200]}"


def resolve_mode(mode: str | None) -> str:
    m = (mode or os.environ.get("CLAUSETOWER_LLM") or "auto").lower()
    if m != "auto":
        return m
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "anthropic"
    if os.environ.get("CLAUSETOWER_OPENAI_BASE_URL"):
        return "openai"
    if shutil.which(CLAUDE_BIN):
        return "claude-code"
    return "mock"


def load_prompt(name: str) -> str:
    from .contracts import require_repo_dir

    return (require_repo_dir("prompts") / f"{name}.md").read_text(encoding="utf-8")


def claude_command(model: str, system: str, schema: type[BaseModel]) -> list[str]:
    """claude -p 호출 인자. 내장 도구를 모두 끄고(--tools "") --mcp-config 밖의 MCP 서버를 싣지 않는다(--strict-mcp-config).
    거부 목록(--disallowedTools)은 이중 안전장치로 남긴다. 계약서 본문에 심은 지시가 도구를 부를 여지를 없앤다."""
    return [CLAUDE_BIN, "-p", "--output-format", "json", "--model", model, "--system-prompt", system,
            "--json-schema", json.dumps(schema.model_json_schema(), ensure_ascii=False),
            "--no-session-persistence", "--tools", "", "--strict-mcp-config", "--disallowedTools", CLAUDE_DISALLOWED_TOOLS]


@dataclass
class Usage:
    calls: int = 0
    fallbacks: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    cost_usd: float = 0.0
    by_stage: dict[str, int] = field(default_factory=dict)


class LLM:
    def __init__(self, mode: str | None = None, model: str = DEFAULT_MODEL):
        self.mode = resolve_mode(mode)
        self.model = model
        self.usage = Usage()
        self._client = None
        self.concurrency = 1 if self.mode == "mock" else int(os.environ.get("CLAUSETOWER_CONCURRENCY", "4"))
        if self.mode == "claude-code" and not shutil.which(CLAUDE_BIN):
            log.warning("claude CLI를 찾지 못해 mock으로 전환한다.")
            self.mode = "mock"
        if self.mode == "anthropic":
            try:
                import anthropic

                self._client = anthropic.Anthropic()
            except Exception as e:  # noqa: BLE001
                log.warning("anthropic 클라이언트 생성 실패(%s). mock으로 전환한다.", e)
                self.mode = "mock"

    def parse(self, *, stage: str, system: str, user: str, schema: type[T], mock_fn: Callable[[], T],
              max_tokens: int = 8000) -> T:
        if self.mode == "mock":
            return mock_fn()
        if self.mode == "claude-code":
            return self._parse_claude_code(stage=stage, system=system, user=user, schema=schema, mock_fn=mock_fn)
        if self.mode == "openai":
            return self._parse_openai(stage=stage, system=system, user=user, schema=schema, mock_fn=mock_fn, max_tokens=max_tokens)
        t0 = time.time()
        last: Exception | None = None
        for attempt in range(2):
            try:
                resp = self._client.messages.parse(model=self.model, max_tokens=max_tokens, system=system,
                                                   messages=[{"role": "user", "content": user}], output_format=schema)
                self._count(stage, time.time() - t0, getattr(resp.usage, "input_tokens", 0), getattr(resp.usage, "output_tokens", 0))
                if resp.parsed_output is None:
                    raise ValueError("parsed_output 비어 있음")
                return resp.parsed_output
            except ValidationError as e:
                last = e
                log.warning("[%s] 구조화 출력 검증 실패(시도 %d): %s", stage, attempt + 1, _err_summary(e))
            except Exception as e:  # noqa: BLE001
                last = e
                log.error("[%s] anthropic 호출 실패: %s", stage, _err_summary(e))
                break
        self.usage.fallbacks += 1
        log.error("[%s] mock으로 대체한다: %s", stage, _err_summary(last) if last else "?")
        return mock_fn()

    def _count(self, stage: str, seconds: float, inp: int, out: int, cost: float = 0.0) -> None:
        self.usage.calls += 1
        self.usage.seconds += seconds
        self.usage.input_tokens += int(inp or 0)
        self.usage.output_tokens += int(out or 0)
        self.usage.cost_usd += float(cost or 0)
        self.usage.by_stage[stage] = self.usage.by_stage.get(stage, 0) + 1

    def _parse_claude_code(self, *, stage, system, user, schema, mock_fn):
        cmd = claude_command(self.model, system, schema)
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
        last: Exception | None = None
        for attempt in range(2):
            t0 = time.time()
            try:
                with tempfile.TemporaryDirectory() as cwd:
                    # Claude Code CLI는 UTF-8로 읽고 쓴다. 로캘 인코딩(한국어 Windows는 cp949)에 맡기면 한글이 깨지거나 디코드가 실패한다.
                    proc = subprocess.run(cmd, input=user, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                          timeout=CLAUDE_TIMEOUT, cwd=cwd, env=env)
                if proc.returncode != 0:
                    log.debug("[%s] claude stderr: %s", stage, (proc.stderr or "").strip()[:500])
                    raise RuntimeError(f"claude 종료 코드 {proc.returncode} (stderr {len(proc.stderr or '')}자, stdout {len(proc.stdout or '')}자)")
                if not proc.stdout:
                    raise ValueError("claude 출력이 비어 있음")
                data = json.loads(proc.stdout)
                u = data.get("usage") or {}
                self._count(stage, time.time() - t0,
                            int(u.get("input_tokens", 0) or 0) + int(u.get("cache_creation_input_tokens", 0) or 0) + int(u.get("cache_read_input_tokens", 0) or 0),
                            int(u.get("output_tokens", 0) or 0), float(data.get("total_cost_usd", 0) or 0))
                if data.get("is_error"):
                    log.debug("[%s] claude 오류 결과: %s", stage, str(data.get("result"))[:500])
                    raise RuntimeError(f"claude 오류 응답(subtype {data.get('subtype')}, 결과 {len(str(data.get('result') or ''))}자)")
                payload = data.get("structured_output")
                if payload is None:
                    payload = json.loads(data.get("result") or "null")
                if payload is None:
                    raise ValueError("structured_output 비어 있음")
                return schema.model_validate(payload)
            except subprocess.TimeoutExpired as e:
                last = e
                log.warning("[%s] claude 시간 초과(시도 %d)", stage, attempt + 1)
            except (ValidationError, ValueError, RuntimeError, TypeError, AttributeError, OSError) as e:
                # 어떤 응답 처리 실패도 밖으로 내보내지 않고 정답지(또는 자리표시자) 대체로 떨어지게 한다
                last = e
                log.warning("[%s] claude-code 응답 처리 실패(시도 %d): %s", stage, attempt + 1, _err_summary(e))
        self.usage.fallbacks += 1
        log.error("[%s] claude-code 실패, mock으로 대체한다: %s", stage, _err_summary(last) if last else "?")
        return mock_fn()

    def _parse_openai(self, *, stage, system, user, schema, mock_fn, max_tokens):
        """OpenAI 호환 엔드포인트. 도구 호출을 강제해 구조화 출력을 받고, 도구 호출이 없으면 본문을 JSON으로 해석한다."""
        base = os.environ.get("CLAUSETOWER_OPENAI_BASE_URL", "").rstrip("/")
        key = os.environ.get("CLAUSETOWER_OPENAI_API_KEY", "")
        if not base:
            self.usage.fallbacks += 1
            log.error("[%s] CLAUSETOWER_OPENAI_BASE_URL이 없어 mock으로 대체한다.", stage)
            return mock_fn()
        tool = {"type": "function", "function": {"name": "submit", "description": "결과를 이 스키마로 돌려준다.", "parameters": schema.model_json_schema()}}
        body = {"model": self.model, "max_tokens": max_tokens, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "tools": [tool], "tool_choice": {"type": "function", "function": {"name": "submit"}}}
        headers = {"content-type": "application/json"}
        if key:
            headers["authorization"] = f"Bearer {key}"
        last: Exception | None = None
        for attempt in range(2):
            t0 = time.time()
            try:
                req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=CLAUDE_TIMEOUT) as r:
                    data = json.loads(r.read().decode("utf-8"))
                u = data.get("usage") or {}
                self._count(stage, time.time() - t0, u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
                msg = (data.get("choices") or [{}])[0].get("message") or {}
                calls = msg.get("tool_calls") or []
                payload = json.loads(calls[0]["function"]["arguments"]) if calls else json.loads(msg.get("content") or "null")
                if payload is None:
                    raise ValueError("응답에 구조화 출력이 없다")
                return schema.model_validate(payload)
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")
                log.debug("[%s] openai 호환 오류 본문: %s", stage, body[:500])
                last = RuntimeError(f"HTTP {e.code} (본문 {len(body)}자)")
                log.warning("[%s] openai 호환 호출 실패(시도 %d): %s", stage, attempt + 1, last)
            except (ValidationError, ValueError, KeyError, OSError) as e:
                last = e
                log.warning("[%s] openai 호환 응답 처리 실패(시도 %d): %s", stage, attempt + 1, _err_summary(e))
        self.usage.fallbacks += 1
        log.error("[%s] openai 호환 실패, mock으로 대체한다: %s", stage, _err_summary(last) if last else "?")
        return mock_fn()

    def map(self, fn: Callable, items: list) -> list:
        if self.concurrency <= 1 or len(items) <= 1:
            return [fn(x) for x in items]
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=self.concurrency) as ex:
            return list(ex.map(fn, items))
