#!/usr/bin/env python3
"""ClauseTower 품질 게이트 실행기.

저장소의 검증 명령(pytest, mock 데모, 사이트 조립, JS≡Python 엔진 대조, 다중 시드 견고성, 실제 모델 보고서 채점,
브라우저 스모크)을 같은 환경 보정 아래 한 번에 돌리고, 결과와 '문서에 쓸 수 있는 측정값'을 JSON 하나로 남긴다.

  python .claude/skills/ct-quality-gates/scripts/run_gates.py --out _workspace/01_qa_gates.json
  python .claude/skills/ct-quality-gates/scripts/run_gates.py --only pytest verify_engine --out _workspace/04_qa_gates_r1.json

환경 보정(심사위원 PC·사내망에서 실제로 걸리는 문제를 피하고, 그 사실을 env 진단에 따로 기록한다):
  PYTHONPATH=src(설치하지 않아도 실행), PYTHONUTF8=1(cp949 콘솔), NO_PROXY에 127.0.0.1·localhost 추가(사내 프록시),
  CLAUSETOWER_LLM=mock(네트워크·과금 없음).
추적 중인 파일은 고치지 않는다. 견고성 평가는 --out 옆 폴더에 쓰고, 실행 전후 git status를 비교해 변경이 생기면 실패로 표시한다.
표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

GATES = ["pytest", "demo", "build_site", "verify_engine", "robustness", "extraction", "smoke_web"]
DEPS = {"verify_engine": ["demo", "build_site"], "smoke_web": ["build_site"]}
SCENARIO_ORDER = ["typhoon", "port_congestion", "wms_outage"]


def find_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "pyproject.toml").is_file() and (p / "src" / "clausetower").is_dir():
            return p
    raise SystemExit("ClauseTower 저장소 루트(pyproject.toml + src/clausetower)를 찾지 못했다. --root로 지정하라.")


def normalized_env(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    src = str(root / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["CLAUSETOWER_LLM"] = "mock"
    keys = ["NO_PROXY"] if os.name == "nt" else ["NO_PROXY", "no_proxy"]
    for k in keys:
        cur = [x for x in (env.get(k) or "").split(",") if x]
        for host in ("127.0.0.1", "localhost"):
            if host not in cur:
                cur.append(host)
        env[k] = ",".join(cur)
    return env


def run(cmd: list[str], cwd: Path, env: dict[str, str], timeout: int = 900) -> dict:
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, timeout=timeout)
        out = (p.stdout or b"").decode("utf-8", "replace") + (p.stderr or b"").decode("utf-8", "replace")
        code = p.returncode
    except FileNotFoundError as e:
        return {"ok": False, "code": None, "seconds": 0.0, "output": f"실행 파일 없음: {e}", "cmd": " ".join(cmd)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": None, "seconds": round(time.time() - t0, 1), "output": f"{timeout}초 시간 초과", "cmd": " ".join(cmd)}
    return {"ok": code == 0, "code": code, "seconds": round(time.time() - t0, 1), "output": out, "cmd": " ".join(cmd)}


def tail(text: str, n: int = 30) -> str:
    return "\n".join(text.strip().splitlines()[-n:])


def first_json(text: str):
    i = text.find("{")
    if i < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[i:])
        return obj
    except ValueError:
        return None


def git_status(root: Path) -> list[str] | None:
    if not shutil.which("git"):
        return None
    p = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root, capture_output=True)
    if p.returncode != 0:
        return None
    return sorted(line for line in p.stdout.decode("utf-8", "replace").splitlines() if line.strip())


def diagnose_env(root: Path, py: str) -> dict:
    """보정하지 않은 원래 환경에서 심사위원이 겪을 문제를 기록한다."""
    raw = dict(os.environ)
    d: dict = {"platform": sys.platform, "python": sys.version.split()[0]}
    try:
        import tomllib

        req = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"].get("requires-python")
    except Exception:  # noqa: BLE001
        req = None
    d["requires_python"] = req
    m = re.match(r">=\s*(\d+)\.(\d+)", req or "")
    d["python_ok"] = (sys.version_info[:2] >= (int(m.group(1)), int(m.group(2)))) if m else None
    p = run([py, "-c", "import clausetower, sys; print(clausetower.__file__)"], root, {k: v for k, v in raw.items() if k != "PYTHONPATH"}, 60)
    d["package_installed"] = p["ok"]
    d["package_location"] = p["output"].strip().splitlines()[-1] if p["ok"] else None
    p = run([py, "-c", "import sys, locale; print(sys.stdout.encoding, locale.getpreferredencoding(False))"], root, raw, 60)
    d["raw_stdout_encoding"] = p["output"].strip()
    proxy = raw.get("HTTP_PROXY") or raw.get("http_proxy") or raw.get("HTTPS_PROXY") or raw.get("https_proxy")
    no_proxy = [x.strip() for x in (raw.get("NO_PROXY") or raw.get("no_proxy") or "").split(",")]
    d["proxy_set"] = bool(proxy)
    d["no_proxy_covers_loopback"] = "127.0.0.1" in no_proxy
    d["loopback_through_proxy_risk"] = bool(proxy) and "127.0.0.1" not in no_proxy
    d["node"] = run(["node", "--version"], root, raw, 30)["output"].strip() if shutil.which("node") else None
    d["playwright"] = bool(d["node"]) and run(["node", "-e", "require.resolve('playwright')"], root, raw, 30)["ok"]
    d["claude_cli"] = shutil.which("claude")
    d["git"] = bool(shutil.which("git"))
    return d


def scenario_facts(report_dir: Path) -> dict:
    facts: dict = {}
    for p in sorted(report_dir.glob("report_*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        sid = r["scenario"]["id"]
        facts[sid] = {
            "title": r["scenario"].get("title"),
            "llm_mode": r.get("llm_mode"),
            "llm_calls": r.get("llm_calls"),
            "savings_vs_deadline_krw": r.get("savings_vs_deadline_krw"),
            "savings_vs_deadline_pct": r.get("savings_vs_deadline_pct"),
            "ranking_at_h": r.get("ranking_at_h"),
            "ranking_rows": len(r.get("ranking") or []),
            "rank_moves_ge3": sum(1 for x in r.get("ranking") or [] if abs(x["deadline_rank"] - x["exposure_rank"]) >= 3),
            "policies": {k: {"label": v.get("label"), "total_penalty_krw": v.get("total_penalty_krw"), "late_count": v.get("late_count")}
                         for k, v in (r.get("policies") or {}).items()},
            "per_customer_krw": {k: (r["policies"].get(k) or {}).get("per_customer_krw") for k in ("deadline_first", "exposure_first")},
            "judgments_applies": {cid: j.get("applies") for cid, j in (r.get("judgments") or {}).items()},
        }
    return dict(sorted(facts.items(), key=lambda kv: SCENARIO_ORDER.index(kv[0]) if kv[0] in SCENARIO_ORDER else 99))


def repo_counts(root: Path) -> dict:
    return {
        "contracts": len(list((root / "contracts").glob("*.md"))),
        "golden": len(list((root / "contracts" / "golden").glob("*.yaml"))),
        "scenarios": sorted(p.stem for p in (root / "scenarios").glob("*.yaml")),
        "prompts": sorted(p.name for p in (root / "prompts").glob("*.md")),
        "docs": sorted(p.name for p in (root / "docs").glob("*.md")),
        "screenshots": len(list((root / "docs" / "screenshots").rglob("*.png"))),
        "test_functions": sum(len(re.findall(r"^def test_", p.read_text(encoding="utf-8"), re.M)) for p in (root / "tests").glob("test_*.py")),
        "real_reports": sorted(p.name for p in (root / "eval" / "results" / "real").glob("report_*.json")),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="ClauseTower 품질 게이트")
    ap.add_argument("--root", default=None)
    ap.add_argument("--out", default="_workspace/gates.json")
    ap.add_argument("--only", nargs="*", choices=GATES, default=None, help="지정한 게이트만(의존 게이트는 자동 포함)")
    ap.add_argument("--skip", nargs="*", choices=GATES, default=[])
    ap.add_argument("--seeds", type=int, default=30)
    a = ap.parse_args()

    root = Path(a.root).resolve() if a.root else find_root(Path(__file__).resolve())
    out = Path(a.out)
    out = out if out.is_absolute() else root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    work = out.with_suffix("")
    work.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    env = normalized_env(root)

    selected = list(a.only) if a.only else list(GATES)
    for g in list(selected):
        for dep in DEPS.get(g, []):
            if dep not in selected:
                selected.append(dep)
    selected = [g for g in GATES if g in selected and g not in a.skip]

    result: dict = {"root": str(root), "env": diagnose_env(root, py), "env_fixes_applied": ["PYTHONPATH=src", "PYTHONUTF8=1", "NO_PROXY+=127.0.0.1,localhost", "CLAUSETOWER_LLM=mock"],
                    "gates": {}, "facts": {"counts": repo_counts(root)}}
    before = git_status(root)
    node = shutil.which("node")

    for g in selected:
        if g == "pytest":
            r = run([py, "-m", "pytest", "-q"], root, env)
            counts = {k: int(n) for n, k in re.findall(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed)", tail(r["output"], 3))}
            counts = {("errors" if k == "error" else k): v for k, v in counts.items()}
            failing = re.findall(r"^(?:FAILED|ERROR) (\S+)", r["output"], re.M)
            result["gates"][g] = {"ok": r["ok"], "seconds": r["seconds"], "counts": counts, "failing": failing, "tail": tail(r["output"], 15 if r["ok"] else 40)}
            result["facts"]["tests_passed"] = counts.get("passed")
        elif g == "demo":
            r = run([py, "-m", "clausetower", "demo", "--llm", "mock", "--out", "out/demo"], root, env)
            result["gates"][g] = {"ok": r["ok"], "seconds": r["seconds"], "tail": tail(r["output"], 12 if r["ok"] else 40)}
            if r["ok"]:
                result["facts"]["scenarios_mock"] = scenario_facts(root / "out" / "demo")
        elif g == "build_site":
            r = run([py, "scripts/build_site.py"], root, env)
            data_js = root / "site" / "data.js"
            result["gates"][g] = {"ok": r["ok"] and data_js.is_file(), "seconds": r["seconds"], "tail": tail(r["output"], 8 if r["ok"] else 40)}
            if data_js.is_file():
                result["facts"]["site"] = {"data_js_kb": data_js.stat().st_size // 1024, "files": sorted(p.name for p in (root / "site").iterdir())}
        elif g == "verify_engine":
            if not node:
                result["gates"][g] = {"ok": None, "skipped": "node 없음"}
                continue
            r = run(["node", "scripts/verify_engine.js"], root, env)
            m = re.search(r"(\d+)/(\d+) checks passed", r["output"])
            diffs = [ln for ln in r["output"].splitlines() if ln.startswith("DIFF")]
            result["gates"][g] = {"ok": r["ok"], "seconds": r["seconds"], "passed": int(m.group(1)) if m else None, "total": int(m.group(2)) if m else None,
                                  "diffs": diffs[:20], "tail": tail(r["output"], 5 if r["ok"] else 40)}
            if m:
                result["facts"]["engine_parity"] = f"{m.group(1)}/{m.group(2)}"
        elif g == "robustness":
            rob_dir = work / "robustness"
            r = run([py, "eval/run_eval.py", "robustness", "--seeds", str(a.seeds), "--out", str(rob_dir)], root, env)
            gate = {"ok": r["ok"], "seconds": r["seconds"], "seeds": a.seeds, "tail": "" if r["ok"] else tail(r["output"], 40)}
            new_p, old_p = rob_dir / "robustness.json", root / "eval" / "results" / "robustness.json"
            if new_p.is_file():
                new = json.loads(new_p.read_text(encoding="utf-8"))
                summ = {sid: {k: s.get(k) for k in ("win_rate", "ties", "saving_pct_mean", "saving_pct_min", "saving_pct_max")} for sid, s in new["scenarios"].items()}
                result["facts"]["robustness"] = {"seeds": new.get("seeds"), "scenarios": summ}
                if old_p.is_file() and a.seeds == 30:
                    old = json.loads(old_p.read_text(encoding="utf-8"))
                    gate["matches_tracked_results"] = old.get("scenarios") == new.get("scenarios")
                    if not gate["matches_tracked_results"]:
                        gate["drift_note"] = "eval/results/robustness.json과 다시 잰 값이 다르다. 문서 숫자를 어느 쪽으로 맞출지 확인하라."
            result["gates"][g] = gate
        elif g == "extraction":
            reports = sorted((root / "eval" / "results" / "real").glob("report_*.json"))
            per: dict = {}
            ok = True
            for rp in reports:
                r = run([py, "eval/run_eval.py", "extraction", str(rp.relative_to(root))], root, env)
                obj = first_json(r["output"]) if r["ok"] else None
                ok = ok and r["ok"] and obj is not None
                sid = rp.stem.replace("report_", "")
                per[sid] = ({k: obj.get(k) for k in ("llm_mode", "term_field_accuracy", "term_fields", "judgment_accuracy", "judgment_fields", "applies_accuracy", "citations_verbatim_rate")}
                            if obj else {"error": tail(r["output"], 10)})
            result["gates"][g] = {"ok": ok if reports else None, "reports": len(reports), **({} if reports else {"skipped": "eval/results/real/에 보고서 없음"})}
            result["facts"]["real_model_scores"] = per
        elif g == "smoke_web":
            if not (node and result["env"].get("playwright")):
                result["gates"][g] = {"ok": None, "skipped": "playwright 미설치(npm i -D playwright && npx playwright install chromium)"}
                continue
            r = run(["node", "scripts/smoke_web.js", "site/index.html", str(work / "smoke_shots")], root, env)
            result["gates"][g] = {"ok": r["ok"], "seconds": r["seconds"], "tail": tail(r["output"], 15 if r["ok"] else 40)}

    after = git_status(root)
    if before is not None and after is not None:
        changed = sorted(set(after) - set(before))
        result["tracked_files_changed_by_gates"] = changed
        if changed:
            result["gates"]["no_tracked_changes"] = {"ok": False, "changed": changed}

    ran = {k: v for k, v in result["gates"].items() if v.get("ok") is not None}
    result["summary"] = {"ok": all(v["ok"] for v in ran.values()), "passed": [k for k, v in ran.items() if v["ok"]],
                         "failed": [k for k, v in ran.items() if not v["ok"]],
                         "skipped": {k: v.get("skipped") for k, v in result["gates"].items() if v.get("ok") is None}}
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    s = result["summary"]
    print(f"게이트: {'통과' if s['ok'] else '실패'}  통과 {s['passed']}  실패 {s['failed']}  건너뜀 {list(s['skipped'])}")
    e = result["env"]
    warn = []
    if not e.get("package_installed"):
        warn.append("패키지 미설치(pip install -e .[dev] 필요)")
    if e.get("loopback_through_proxy_risk"):
        warn.append("프록시가 설정됐는데 NO_PROXY에 127.0.0.1이 없음(로컬 도우미·서버 테스트가 프록시로 샘)")
    if "utf" not in (e.get("raw_stdout_encoding") or "").lower():
        warn.append(f"콘솔 인코딩 {e.get('raw_stdout_encoding')}")
    if warn:
        print("원래 환경 경고: " + " / ".join(warn))
    print(f"결과: {out}")
    return 0 if s["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
