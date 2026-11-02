"""계약서, 정답지(golden), 시나리오 파일 로더.

데이터(contracts/, scenarios/, prompts/)는 패키지 밖 저장소 루트에 있다. 그래서 편집 설치(pip install -e .)나
PYTHONPATH=src 실행을 전제로 한다. 다른 방식으로 설치했다면 CLAUSETOWER_ROOT에 저장소 루트를 지정한다.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .schemas import Customer, ForceMajeureJudgment, PenaltyTerms, Scenario

ROOT = Path(os.environ.get("CLAUSETOWER_ROOT") or Path(__file__).resolve().parents[2])
CONTRACT_DIR = ROOT / "contracts"
GOLDEN_DIR = CONTRACT_DIR / "golden"
SCENARIO_DIR = ROOT / "scenarios"


def require_repo_dir(name: str) -> Path:
    """저장소 루트의 데이터 폴더. 없으면 무엇을 해야 하는지 알려 주는 오류를 낸다."""
    d = ROOT / name
    if not d.is_dir():
        raise FileNotFoundError(
            f"ClauseTower 데이터 폴더 '{name}/'를 찾지 못했다(찾은 위치: {d}). "
            "저장소 루트에서 pip install -e . 로 설치하거나, 환경 변수 CLAUSETOWER_ROOT에 저장소 루트(contracts/·scenarios/·prompts/가 있는 폴더)를 지정하라.")
    return d


def load_customers() -> list[Customer]:
    raw = yaml.safe_load((require_repo_dir("contracts") / "customers.yaml").read_text(encoding="utf-8"))
    return [Customer(**{k: v for k, v in c.items() if k != "contract_file"}) for c in raw["customers"]]


def contract_file(customer_id: str) -> Path:
    raw = yaml.safe_load((CONTRACT_DIR / "customers.yaml").read_text(encoding="utf-8"))
    for c in raw["customers"]:
        if c["id"] == customer_id:
            return CONTRACT_DIR / c["contract_file"]
    raise KeyError(customer_id)


def load_contract_text(customer_id: str) -> str:
    return contract_file(customer_id).read_text(encoding="utf-8")


def load_golden_terms(customer_id: str) -> PenaltyTerms:
    raw = yaml.safe_load((GOLDEN_DIR / f"{customer_id}.yaml").read_text(encoding="utf-8"))
    return PenaltyTerms(**raw["terms"])


def load_golden_judgment(customer_id: str, scenario_id: str) -> ForceMajeureJudgment:
    raw = yaml.safe_load((GOLDEN_DIR / f"{customer_id}.yaml").read_text(encoding="utf-8"))
    j = dict(raw["judgments"][scenario_id])
    terms = raw["terms"]
    cite = (terms.get("force_majeure") or {}).get("citation")
    if j.get("has_clause") and cite and "citation" not in j:
        j["citation"] = cite
    j.setdefault("conditions_met", {})
    return ForceMajeureJudgment(customer_id=customer_id, **j)


def list_scenarios() -> list[str]:
    return sorted(p.stem for p in require_repo_dir("scenarios").glob("*.yaml"))


def load_scenario(scenario_id: str) -> Scenario:
    raw = yaml.safe_load((SCENARIO_DIR / f"{scenario_id}.yaml").read_text(encoding="utf-8"))
    return Scenario(**raw)
