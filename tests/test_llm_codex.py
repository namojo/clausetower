"""codex 모드(Codex CLI `codex exec`)의 스키마 변환과 하위 프로세스 호출. 실제 CLI 대신 가짜 CLI로 시험한다(과금 없음)."""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from pydantic import BaseModel

import clausetower.llm as llm_mod
from clausetower.contracts import load_golden_judgment, load_golden_terms
from clausetower.llm import LLM, _resolve, codex_command, codex_schema
from clausetower.schemas import ExtractionResult, ForceMajeureJudgment

SRC = Path(__file__).resolve().parents[1] / "src"
KOREAN = "제7조 지연된 매 1시간마다 해당 주문 상품가액의 0.08%를 배상한다 — 불가항력(태풍·지진)"


class Q(BaseModel):
    quote: str


def _walk(node, defs):
    node = _resolve(node, defs) if "$ref" in node else node
    yield node
    for b in node.get("anyOf", []):
        yield from _walk(b, defs)
    for v in (node.get("properties") or {}).values():
        yield from _walk(v, defs)
    if isinstance(node.get("items"), dict):
        yield from _walk(node["items"], defs)


def test_codex_schema_follows_openai_strict_rules():
    """Codex는 출력 스키마를 OpenAI 엄격 모드로 보낸다. 객체마다 additionalProperties=false, 모든 속성 required, default 없음이어야 400이 나지 않는다."""
    for model in (ExtractionResult, ForceMajeureJudgment):
        s = codex_schema(model)
        defs = s.get("$defs", {})
        nodes = list(_walk(s, defs)) + [n for d in defs.values() for n in _walk(d, defs)]
        objs = [n for n in nodes if n.get("type") == "object"]
        assert objs
        for n in objs:
            assert n.get("additionalProperties") is False, n
            assert sorted(n["required"]) == sorted(n["properties"]), n
        assert all("default" not in n for n in nodes)


def _to_codex_shape(data, node, defs):
    """원래 모양의 값을 codex_schema 모양으로 바꾼다(사전 → [{key, value}], 빠진 선택 필드 → null). 시험용 역변환."""
    node = _resolve(node, defs)
    if data is None:
        return None
    if "anyOf" in node:
        b = [x for x in node["anyOf"] if _resolve(x, defs).get("type") != "null"][0]
        return _to_codex_shape(data, b, defs)
    if node.get("type") == "object":
        if node.get("properties") is not None:
            return {k: _to_codex_shape(data.get(k), v, defs) for k, v in node["properties"].items()}
        ap = node.get("additionalProperties")
        if isinstance(ap, dict):
            return [{"key": k, "value": _to_codex_shape(v, ap, defs)} for k, v in data.items()]
    if node.get("type") == "array":
        return [_to_codex_shape(x, node["items"], defs) for x in data]
    return data


def test_codex_output_restores_to_pydantic_models():
    """정답지 조건·판단을 Codex 출력 모양으로 바꿨다가 되돌리면 원래 값과 같아야 한다(사전 필드·선택 필드 포함)."""
    for cid in "ABCDEFGH":
        golden = ExtractionResult(terms=load_golden_terms(cid), ambiguities=["예시"], confidence=0.9)
        src = ExtractionResult.model_json_schema()
        shaped = _to_codex_shape(json.loads(golden.model_dump_json()), src, src.get("$defs", {}))
        assert ExtractionResult.model_validate(llm_mod._restore(shaped, src, src.get("$defs", {}))) == golden
        j = load_golden_judgment(cid, "typhoon")
        js = ForceMajeureJudgment.model_json_schema()
        shaped = _to_codex_shape(json.loads(j.model_dump_json()), js, js.get("$defs", {}))
        assert ForceMajeureJudgment.model_validate(llm_mod._restore(shaped, js, js.get("$defs", {}))) == j


def test_codex_command_runs_read_only_without_tools():
    cmd = codex_command("gpt-x", "s.json", "o.json")
    assert cmd[1] == "exec" and cmd[-1] == "-"
    for flag in ("--ephemeral", "--skip-git-repo-check", "--json"):
        assert flag in cmd
    assert cmd[cmd.index("--sandbox") + 1] == "read-only"
    disabled = {cmd[i + 1] for i, a in enumerate(cmd) if a == "--disable"}
    assert {"shell_tool", "apps", "plugins"} <= disabled
    assert 'web_search="disabled"' in cmd
    assert cmd[cmd.index("--output-schema") + 1] == "s.json" and cmd[cmd.index("-o") + 1] == "o.json"
    assert cmd[cmd.index("-m") + 1] == "gpt-x"
    assert "-m" not in codex_command(llm_mod.CODEX_DEFAULT_LABEL, "s.json", "o.json")


def test_auto_prefers_codex_cli(monkeypatch):
    monkeypatch.delenv("CLAUSETOWER_LLM", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(llm_mod.shutil, "which", lambda name: "/bin/codex" if name == llm_mod.CODEX_BIN else None)
    assert llm_mod.resolve_mode(None) == "codex"
    monkeypatch.setattr(llm_mod.shutil, "which", lambda name: None)
    assert llm_mod.resolve_mode(None) == "anthropic"


def _fake_codex(tmp_path: Path, fail: bool = False) -> str:
    """stdin(UTF-8) 전체를 quote로 -o 파일에 쓰고 JSONL 이벤트를 내는 가짜 codex CLI."""
    script = tmp_path / "fake_codex.py"
    script.write_text(textwrap.dedent(f"""
        import json, sys
        args = sys.argv[1:]
        data = sys.stdin.buffer.read().decode("utf-8")
        assert args[0] == "exec" and args[-1] == "-"
        json.load(open(args[args.index("--output-schema") + 1], encoding="utf-8"))
        if {fail!r}:
            err = json.dumps({{"error": {{"code": "model_not_found"}}}})
            sys.stdout.write(json.dumps({{"type": "turn.failed", "error": {{"message": err}}}}) + "\\n")
            sys.exit(1)
        open(args[args.index("-o") + 1], "w", encoding="utf-8").write(json.dumps({{"quote": data}}, ensure_ascii=False))
        sys.stdout.write(json.dumps({{"type": "turn.completed", "usage": {{"input_tokens": 12, "output_tokens": 3}}}}) + "\\n")
    """), encoding="utf-8")
    if os.name == "nt":
        wrapper = tmp_path / "fake_codex.cmd"
        wrapper.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        wrapper = tmp_path / "fake_codex"
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        wrapper.chmod(0o755)
    return str(wrapper)


def _run_probe(tmp_path: Path, fail: bool) -> dict:
    probe = tmp_path / "probe.py"
    probe.write_text(textwrap.dedent(f"""
        import json, sys
        from pydantic import BaseModel
        from clausetower.llm import LLM
        class Q(BaseModel):
            quote: str
        src = {KOREAN!r}
        llm = LLM("codex")
        res = {{"mode": llm.mode}}
        try:
            q = llm.parse(stage="extract", system="지침", user=src, schema=Q, mock_fn=lambda: Q(quote="MOCK"))
            res.update(result="returned", contains=src in q.quote, mock=q.quote == "MOCK", fallbacks=llm.usage.fallbacks,
                       tokens=[llm.usage.input_tokens, llm.usage.output_tokens])
        except Exception as e:
            res.update(result="raised", exc=type(e).__name__)
        open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(res))
    """), encoding="utf-8")
    out = tmp_path / "out.json"
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING", "CLAUSETOWER_CODEX_MODEL")}
    env.update(PYTHONPATH=str(SRC), CLAUSETOWER_CODEX_BIN=_fake_codex(tmp_path, fail), PYTHONUTF8="0")
    p = subprocess.run([sys.executable, "-X", "utf8=0", str(probe), str(out)], env=env, capture_output=True, timeout=120)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")[-800:]
    return json.loads(out.read_text(encoding="utf-8"))


def test_codex_roundtrips_korean_without_utf8_mode(tmp_path):
    """한국어 Windows(cp949, UTF-8 모드 꺼짐)에서도 계약서 한글이 Codex CLI와 깨지지 않고 오가야 한다."""
    res = _run_probe(tmp_path, fail=False)
    assert res == {"mode": "codex", "result": "returned", "contains": True, "mock": False, "fallbacks": 0, "tokens": [12, 3]}, res


def test_codex_failure_falls_back_instead_of_raising(tmp_path):
    """Codex가 실패하면(예: 계정이 지원하지 않는 모델) 예외 대신 정답지(자리표시자) 대체로 떨어지고 대체 횟수를 센다."""
    res = _run_probe(tmp_path, fail=True)
    assert res["result"] == "returned" and res["mock"] is True and res["fallbacks"] == 1, res
