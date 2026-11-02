"""claude-code 모드(구독 CLI)의 하위 프로세스 호출. 실제 CLI 대신 가짜 CLI로 시험한다(과금 없음)."""
import json
import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from pydantic import BaseModel

import clausetower.llm as llm_mod
from clausetower.llm import LLM, claude_command

SRC = Path(__file__).resolve().parents[1] / "src"
KOREAN = "제7조 지연된 매 1시간마다 해당 주문 상품가액의 0.08%를 배상한다 — 불가항력(태풍·지진)"


class Q(BaseModel):
    quote: str


def _fake_cli(tmp_path: Path) -> str:
    """stdin(UTF-8)을 structured_output.quote로 그대로 돌려주는 가짜 claude CLI. Node 기반 CLI처럼 UTF-8로 읽고 쓴다."""
    script = tmp_path / "fake_claude.py"
    script.write_text(textwrap.dedent("""
        import json, sys
        data = sys.stdin.buffer.read().decode("utf-8")
        out = {"is_error": False, "usage": {}, "total_cost_usd": 0, "structured_output": {"quote": data}}
        sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
    """), encoding="utf-8")
    if os.name == "nt":
        wrapper = tmp_path / "fake_claude.cmd"
        wrapper.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        wrapper = tmp_path / "fake_claude"
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        wrapper.chmod(0o755)
    return str(wrapper)


def test_claude_code_roundtrips_korean_without_utf8_mode(tmp_path):
    """한국어 Windows(cp949, UTF-8 모드 꺼짐)에서도 계약서 한글이 CLI와 깨지지 않고 오가야 한다.
    UTF-8 모드를 끈 별도 프로세스에서 실행해, 로캘 인코딩에 기대는 회귀를 잡는다."""
    probe = tmp_path / "probe.py"
    probe.write_text(textwrap.dedent(f"""
        import json, sys
        from pydantic import BaseModel
        from clausetower.llm import LLM
        class Q(BaseModel):
            quote: str
        src = {KOREAN!r}
        llm = LLM("claude-code")
        res = {{"mode": llm.mode}}
        try:
            q = llm.parse(stage="extract", system="s", user=src, schema=Q, mock_fn=lambda: Q(quote="MOCK"))
            res.update(result="returned", equal=q.quote == src, fallbacks=llm.usage.fallbacks)
        except Exception as e:
            res.update(result="raised", exc=type(e).__name__)
        open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(res))
    """), encoding="utf-8")
    out = tmp_path / "out.json"
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env.update(PYTHONPATH=str(SRC), CLAUSETOWER_CLAUDE_BIN=_fake_cli(tmp_path), PYTHONUTF8="0")
    p = subprocess.run([sys.executable, "-X", "utf8=0", str(probe), str(out)], env=env, capture_output=True, timeout=120)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")[-800:]
    res = json.loads(out.read_text(encoding="utf-8"))
    assert res == {"mode": "claude-code", "result": "returned", "equal": True, "fallbacks": 0}, res


def _completed(stdout, returncode=0, stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _claude_llm(monkeypatch, run):
    monkeypatch.setattr(llm_mod.subprocess, "run", run)
    llm = LLM("mock")
    llm.mode = "claude-code"  # CLI 설치 여부와 무관하게 claude-code 경로를 시험한다
    return llm


def test_claude_code_decode_failure_falls_back_instead_of_raising(monkeypatch):
    """출력 디코드가 실패해 stdout이 None이어도(예전 TypeError) 예외 없이 정답지 대체로 떨어진다."""
    seen = {}

    def run(cmd, **kw):
        seen.update(kw)
        return _completed(None)

    llm = _claude_llm(monkeypatch, run)
    q = llm.parse(stage="extract", system="s", user=KOREAN, schema=Q, mock_fn=lambda: Q(quote="MOCK"))
    assert q.quote == "MOCK" and llm.usage.fallbacks == 1
    assert seen["encoding"] == "utf-8" and seen["errors"] == "replace", "CLI 입출력은 로캘이 아니라 UTF-8로 다룬다"


def test_claude_command_disables_tools_and_user_mcp():
    """계약서 본문의 지시가 도구·MCP를 부르지 못하게, 내장 도구를 모두 끄고 사용자 MCP 설정을 싣지 않는다."""
    cmd = claude_command("m", "sys", Q)
    i = cmd.index("--tools")
    assert cmd[i + 1] == "", "--tools '' 는 내장 도구를 모두 끈다"
    assert "--strict-mcp-config" in cmd and "--disallowedTools" in cmd and "--no-session-persistence" in cmd
    assert cmd[cmd.index("--json-schema") + 1] == json.dumps(Q.model_json_schema(), ensure_ascii=False)


def test_claude_code_warning_logs_do_not_contain_model_output(monkeypatch, caplog):
    """검증 실패·오류 응답을 경고 로그에 남길 때 모델 출력(계약 문구가 섞일 수 있다)을 싣지 않는다."""
    secret = "비밀계약문구-XYZ"
    outputs = iter([
        _completed(json.dumps({"is_error": False, "structured_output": {"quote": 123, "extra": secret}}, ensure_ascii=False)),
        _completed(json.dumps({"is_error": True, "subtype": "error", "result": secret}, ensure_ascii=False)),
    ])
    llm = _claude_llm(monkeypatch, lambda cmd, **kw: next(outputs))
    with caplog.at_level(logging.WARNING, logger="clausetower.llm"):
        q = llm.parse(stage="extract", system="s", user="x", schema=Q, mock_fn=lambda: Q(quote="MOCK"))
    assert q.quote == "MOCK" and llm.usage.fallbacks == 1
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert secret not in messages and "input_value" not in messages
    assert "ValidationError" in messages and "quote" in messages


def test_claude_code_nonzero_exit_hides_stdout(monkeypatch, caplog):
    secret = "모델이 인용한 계약 문구"
    llm = _claude_llm(monkeypatch, lambda cmd, **kw: _completed(secret, returncode=1, stderr="not logged in"))
    with caplog.at_level(logging.WARNING, logger="clausetower.llm"):
        llm.parse(stage="judge", system="s", user="x", schema=Q, mock_fn=lambda: Q(quote="MOCK"))
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert secret not in messages and "종료 코드 1" in messages
