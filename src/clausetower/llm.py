"""LLM 호출의 단일 출입구.

모드(CLAUSETOWER_LLM): codex(Codex CLI `codex exec`, 기본 연결) | claude-code(CLI, 구독) |
anthropic(SDK, ANTHROPIC_BASE_URL로 사내 호환 게이트웨이 가능) |
openai(OpenAI 호환 chat/completions + tools, 사내 LLM용: CLAUSETOWER_OPENAI_BASE_URL, CLAUSETOWER_OPENAI_API_KEY) | mock(결정적) |
auto(Codex CLI → API 키 → 사내 엔드포인트(CLAUSETOWER_OPENAI_BASE_URL) → claude CLI → mock).
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
CODEX_BIN = os.environ.get("CLAUSETOWER_CODEX_BIN", "codex")
CODEX_TIMEOUT = int(os.environ.get("CLAUSETOWER_CODEX_TIMEOUT", "600"))
# 비워 두면 ~/.codex/config.toml의 model을 쓴다. 그 모델을 계정이 지원하지 않으면 여기에 지정한다.
CODEX_MODEL = os.environ.get("CLAUSETOWER_CODEX_MODEL", "")
CODEX_DEFAULT_LABEL = "codex 기본 모델"


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
    if shutil.which(CODEX_BIN):
        return "codex"
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


def _resolve(node: dict, defs: dict) -> dict:
    while isinstance(node, dict) and "$ref" in node:
        node = defs[node["$ref"].split("/")[-1]]
    return node


def _nullable(node: dict, defs: dict) -> bool:
    node = _resolve(node, defs)
    if node.get("type") == "null":
        return True
    return any(_nullable(x, defs) for x in node.get("anyOf", []))


def _strict_node(node: dict, defs: dict) -> dict:
    """pydantic JSON 스키마 한 노드를 OpenAI 엄격 구조화 출력 규칙에 맞게 바꾼다.
    객체는 모든 속성을 required로, additionalProperties는 false로 둔다. 키가 정해지지 않은 사전은 [{key, value}] 배열로 바꾼다."""
    if "$ref" in node:
        return {"$ref": node["$ref"]}
    out: dict = {}
    if node.get("description"):
        out["description"] = node["description"]
    if "anyOf" in node:
        out["anyOf"] = [_strict_node(x, defs) for x in node["anyOf"]]
        return out
    t = node.get("type")
    if t == "object":
        props = node.get("properties")
        if props is not None:
            req = set(node.get("required", []))
            sp = {}
            for k, v in props.items():
                s = _strict_node(v, defs)
                if k not in req and not _nullable(v, defs):
                    s = {"anyOf": [s, {"type": "null"}]}  # 선택 필드: null이면 되돌릴 때 키를 빼서 pydantic 기본값을 쓴다
                sp[k] = s
            out.update({"type": "object", "properties": sp, "required": list(sp), "additionalProperties": False})
            return out
        ap = node.get("additionalProperties")
        if isinstance(ap, dict):
            out.update({"type": "array", "items": {"type": "object", "properties": {"key": {"type": "string"}, "value": _strict_node(ap, defs)},
                                                   "required": ["key", "value"], "additionalProperties": False}})
            out["description"] = (out.get("description", "") + " (키-값 쌍의 배열로 적는다)").strip()
            return out
        out.update({"type": "object", "properties": {}, "required": [], "additionalProperties": False})
        return out
    if t == "array":
        out.update({"type": "array", "items": _strict_node(node.get("items", {}), defs)})
        return out
    for k in ("type", "enum", "const"):
        if k in node:
            out[k] = node[k]
    return out


def codex_schema(schema: type[BaseModel]) -> dict:
    """Codex `--output-schema`용 엄격 스키마. Codex는 OpenAI 엄격 모드로 보내므로 pydantic 스키마를 그대로 쓰면 400이 난다."""
    src = schema.model_json_schema()
    defs = src.get("$defs", {})
    out = _strict_node({k: v for k, v in src.items() if k != "$defs"}, defs)
    if defs:
        out["$defs"] = {name: _strict_node(d, defs) for name, d in defs.items()}
    return out


def _restore(data, node: dict, defs: dict):
    """codex_schema로 받은 출력을 원래 pydantic 스키마 모양으로 되돌린다([{key, value}] → 사전, 비선택 필드의 null 제거)."""
    node = _resolve(node, defs)
    if data is None:
        return None
    if "anyOf" in node:
        branches = [b for b in node["anyOf"] if _resolve(b, defs).get("type") != "null"]
        return _restore(data, branches[0], defs) if branches else data
    t = node.get("type")
    if t == "object":
        props = node.get("properties")
        if props is not None and isinstance(data, dict):
            out = {}
            for k, v in data.items():
                sub = props.get(k)
                if sub is None:
                    continue
                if v is None and not _nullable(sub, defs):
                    continue
                out[k] = _restore(v, sub, defs)
            return out
        ap = node.get("additionalProperties")
        if isinstance(ap, dict) and isinstance(data, list):
            return {str(e.get("key")): _restore(e.get("value"), ap, defs) for e in data if isinstance(e, dict)}
        return data
    if t == "array" and isinstance(data, list):
        return [_restore(x, node.get("items", {}), defs) for x in data]
    return data


def codex_command(model: str, schema_path: str, out_path: str) -> list[str]:
    """codex exec 호출 인자. 읽기 전용 샌드박스, 셸·앱·플러그인·웹 검색 끔, 세션 기록 안 남김.
    작업 폴더는 빈 임시 폴더라 계약서 본문에 심은 지시가 저장소 파일을 읽을 여지가 없다. 프롬프트는 표준 입력으로 보낸다."""
    cmd = [shutil.which(CODEX_BIN) or CODEX_BIN, "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only", "--color", "never",
           "--disable", "shell_tool", "--disable", "apps", "--disable", "plugins", "-c", 'web_search="disabled"',
           "--output-schema", schema_path, "-o", out_path, "--json"]
    if model and model != CODEX_DEFAULT_LABEL:
        cmd += ["-m", model]
    return cmd + ["-"]


def codex_prompt(system: str, user: str) -> str:
    """codex exec에는 시스템 프롬프트 인자가 없어 지침과 입력을 한 프롬프트로 묶는다."""
    return f"{system.strip()}\n\n아래 입력을 처리해 지정된 JSON 스키마로만 답하라. 파일을 읽거나 명령을 실행하지 마라.\n\n{user}"


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
        if self.mode == "codex":
            if not shutil.which(CODEX_BIN):
                log.warning("codex CLI를 찾지 못해 mock으로 전환한다.")
                self.mode = "mock"
            elif CODEX_MODEL:
                self.model = CODEX_MODEL
            elif model.startswith("claude"):
                self.model = CODEX_DEFAULT_LABEL
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
        if self.mode == "codex":
            return self._parse_codex(stage=stage, system=system, user=user, schema=schema, mock_fn=mock_fn)
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

    def _parse_codex(self, *, stage, system, user, schema, mock_fn):
        prompt = codex_prompt(system, user)
        src = schema.model_json_schema()
        defs = src.get("$defs", {})
        last: Exception | None = None
        for attempt in range(2):
            t0 = time.time()
            try:
                with tempfile.TemporaryDirectory() as cwd:
                    schema_path = os.path.join(cwd, "schema.json")
                    out_path = os.path.join(cwd, "last.json")
                    with open(schema_path, "w", encoding="utf-8") as f:
                        json.dump(codex_schema(schema), f, ensure_ascii=False)
                    # Codex CLI는 UTF-8로 읽고 쓴다. 한국어 Windows 로캘(cp949)에 맡기지 않는다.
                    proc = subprocess.run(codex_command(self.model, schema_path, out_path), input=prompt, capture_output=True, text=True,
                                          encoding="utf-8", errors="replace", timeout=CODEX_TIMEOUT, cwd=cwd)
                    inp = out = 0
                    err_msg = None
                    for line in (proc.stdout or "").splitlines():
                        try:
                            ev = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if ev.get("type") == "turn.completed":
                            u = ev.get("usage") or {}
                            inp += int(u.get("input_tokens", 0) or 0)
                            out += int(u.get("output_tokens", 0) or 0)
                        elif ev.get("type") in ("turn.failed", "error"):
                            err_msg = str((ev.get("error") or {}).get("message") or ev.get("message") or "")
                    final = open(out_path, encoding="utf-8").read() if os.path.exists(out_path) else ""
                self._count(stage, time.time() - t0, inp, out)
                if proc.returncode != 0 or not final.strip():
                    log.debug("[%s] codex 오류: %s / stderr: %s", stage, (err_msg or "")[:500], (proc.stderr or "").strip()[:500])
                    code = ""
                    if err_msg:
                        try:
                            code = (json.loads(err_msg).get("error") or {}).get("code") or ""
                        except (json.JSONDecodeError, AttributeError):
                            code = ""
                    raise RuntimeError(f"codex 종료 코드 {proc.returncode}{' (' + code + ')' if code else ''}, 최종 응답 {len(final)}자")
                payload = _restore(json.loads(final), src, defs)
                return schema.model_validate(payload)
            except subprocess.TimeoutExpired as e:
                last = e
                log.warning("[%s] codex 시간 초과(시도 %d)", stage, attempt + 1)
            except (ValidationError, ValueError, RuntimeError, TypeError, AttributeError, KeyError, OSError) as e:
                # 어떤 응답 처리 실패도 밖으로 내보내지 않고 정답지(또는 자리표시자) 대체로 떨어지게 한다
                last = e
                log.warning("[%s] codex 응답 처리 실패(시도 %d): %s", stage, attempt + 1, _err_summary(e))
        self.usage.fallbacks += 1
        log.error("[%s] codex 실패, mock으로 대체한다: %s", stage, _err_summary(last) if last else "?")
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
