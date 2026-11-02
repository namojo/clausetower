import json
import shutil
import subprocess
from pathlib import Path

import pytest

from clausetower.agent import resimulate, run
from clausetower.cli import main
from clausetower.dashboard import build_dashboard
from clausetower.llm import LLM
from clausetower.schemas import Report


@pytest.fixture(scope="module")
def report():
    return run("typhoon", llm=LLM("mock"), with_search=False)


def test_dashboard_is_self_contained_and_embeds_data(tmp_path, report):
    out = build_dashboard([report], tmp_path / "d.html")
    html = out.read_text(encoding="utf-8")
    assert "<script src=" not in html and "<link " not in html, "외부 자원 없이 열려야 한다(오프라인 데모)"
    assert report.scenario.title in html and "workbench" not in html
    for row in report.ranking[:3]:
        assert row.shipment_id in html
    if shutil.which("node"):
        js = html.split("<script>")[1].split("</script>")[0]
        p = subprocess.run(["node", "-e", "new Function(require('fs').readFileSync(0,'utf8'))"], input=js.encode(), capture_output=True)
        assert p.returncode == 0, p.stderr.decode()[:300]


def test_resimulate_keeps_llm_results_and_recomputes_policies(report):
    r2 = resimulate(report, with_search=False)
    assert r2.terms == report.terms and r2.judgments == report.judgments
    assert r2.policies["exposure_first"].total_penalty_krw == report.policies["exposure_first"].total_penalty_krw
    assert any("재실행" in l for l in r2.agent_log)


def test_cli_run_and_demo_from_reports(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUSETOWER_LLM", "mock")
    assert main(["run", "wms_outage", "--out", str(tmp_path), "--no-search"]) == 0
    rep = tmp_path / "wms_outage" / "report.json"
    assert rep.is_file() and (tmp_path / "wms_outage" / "dashboard.html").is_file()
    r = Report.model_validate_json(rep.read_text(encoding="utf-8"))
    assert r.savings_vs_deadline_pct > 0
    assert main(["demo", "--from-reports", str(tmp_path), "--out", str(tmp_path / "d2")]) == 0
    assert (tmp_path / "d2" / "dashboard.html").is_file()


def test_eval_extraction_scores_a_mock_report_perfectly(tmp_path, report):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from eval.run_eval import extraction

    p = tmp_path / "report.json"
    p.write_text(report.model_dump_json(), encoding="utf-8")
    s = extraction(p)
    assert s["term_field_accuracy"] == 1.0 and s["judgment_accuracy"] == 1.0 and s["citations_verbatim_rate"] == 1.0


def test_real_run_artifacts_are_recorded():
    """실제 모델 실행 결과를 저장소에 남겨 둔다(재현 불가 시에도 근거가 남도록)."""
    base = Path(__file__).resolve().parents[1] / "eval" / "results"
    for name in ("extraction_typhoon.json", "extraction_port_congestion.json", "robustness.json"):
        assert (base / name).is_file(), name
    ex = json.loads((base / "extraction_typhoon.json").read_text(encoding="utf-8"))
    assert ex["llm_mode"] in ("claude-code", "anthropic") and ex["term_fields"] > 0


ROOT = Path(__file__).resolve().parents[1]


def _env(**kw):
    import os
    env = {k: v for k, v in os.environ.items() if k != "CLAUSETOWER_ROOT"}
    env.update(PYTHONUTF8="1", CLAUSETOWER_LLM="mock", **kw)
    return env


def test_auto_mode_warns_before_real_llm_calls(monkeypatch, capsys):
    """--llm을 생략해 auto가 실제 LLM을 고르면 과금 호출 사실을 시작할 때 알린다. mock이면 조용하다."""
    import clausetower.cli as cli

    monkeypatch.delenv("CLAUSETOWER_LLM", raising=False)
    monkeypatch.setattr(cli, "LLM", lambda mode=None: type("L", (), {"mode": "claude-code"})())
    cli._make_llm(None)
    assert "--llm mock" in capsys.readouterr().err
    cli._make_llm("claude-code")  # 명시하면 경고하지 않는다
    monkeypatch.setattr(cli, "LLM", lambda mode=None: type("L", (), {"mode": "mock"})())
    cli._make_llm(None)
    assert capsys.readouterr().err == ""


def test_cli_help_lists_every_llm_mode(capsys):
    with pytest.raises(SystemExit):
        main(["run", "--help"])
    out = capsys.readouterr().out
    assert "openai" in out and "codex" in out


def test_eval_subcommand_works_outside_repo_root(tmp_path):
    """콘솔 스크립트·다른 작업 폴더에서도 eval 하위 명령이 eval/run_eval.py를 찾는다(python -P는 작업 폴더를 sys.path에 넣지 않는다)."""
    import sys
    out = tmp_path / "ev"
    p = subprocess.run([sys.executable, "-P", "-m", "clausetower", "eval", "--seeds", "1", "--out", str(out)], cwd=tmp_path,
                       env=_env(PYTHONPATH=str(ROOT / "src")), capture_output=True, timeout=300)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")[-800:]
    assert (out / "robustness.json").is_file()


def test_eval_default_out_does_not_touch_tracked_results():
    import clausetower.cli as cli
    import inspect
    assert '"out/eval"' in inspect.getsource(cli.main), "기본 출력이 추적 중인 eval/results를 덮어쓰면 안 된다"


def test_non_editable_install_gives_actionable_error(tmp_path):
    """site-packages에 복사된 패키지는 저장소 루트를 못 찾는다. 빈 목록 대신 해결 방법을 알려 주고, CLAUSETOWER_ROOT로 풀린다."""
    import sys
    site = tmp_path / "site-packages"
    shutil.copytree(ROOT / "src" / "clausetower", site / "clausetower", ignore=shutil.ignore_patterns("__pycache__"))
    code = "from clausetower.contracts import list_scenarios; print(list_scenarios())"
    p = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=_env(PYTHONPATH=str(site)), capture_output=True, timeout=120)
    err = p.stderr.decode("utf-8", "replace")
    assert p.returncode != 0 and "CLAUSETOWER_ROOT" in err and "pip install -e" in err
    p = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=_env(PYTHONPATH=str(site), CLAUSETOWER_ROOT=str(ROOT)), capture_output=True, timeout=120)
    assert p.returncode == 0 and "typhoon" in p.stdout.decode()


def test_quote_check_rejects_tampered_tail_but_allows_line_breaks():
    import sys
    sys.path.insert(0, str(ROOT))
    from eval.run_eval import quote_is_verbatim

    text = "## 제12조\n① 태풍, 지진 등 천재지변으로 지체한 경우\n책임을 면한다. ② 다만 12시간 이내에 통지한다."
    assert quote_is_verbatim("① 태풍, 지진 등 천재지변으로 지체한 경우 책임을 면한다.", text), "줄바꿈 차이는 무시한다"
    assert quote_is_verbatim("① 태풍, 지진 등 … ② 다만 12시간 이내에 통지한다.", text)
    assert not quote_is_verbatim("① 태풍, 지진 등 천재지변으로 지체한 경우 책임을 모두 면하고 배상금은 0원이다.", text), "앞부분만 맞춘 인용은 통과하면 안 된다"
    assert not quote_is_verbatim("", text)


def test_report_records_llm_fallbacks(report):
    assert report.llm_fallbacks == 0
    old = json.loads(report.model_dump_json())
    old.pop("llm_fallbacks")
    assert Report.model_validate(old).llm_fallbacks == 0, "필드가 없는 예전 보고서(eval/results/real)도 읽혀야 한다"
