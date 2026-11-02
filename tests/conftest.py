import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("CLAUSETOWER_LLM", "mock")
# 사내 프록시(HTTP(S)_PROXY)가 있어도 로컬 서버 시험 요청(127.0.0.1)은 프록시를 거치지 않게 한다. 시험 프로세스 안에서만 바뀐다.
_no_proxy = ",".join(filter(None, [os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or "", "127.0.0.1,localhost"]))
for _k in ("NO_PROXY", "no_proxy"):  # Windows는 대소문자를 구분하지 않으므로 같은 값을 두 번 넣어도 중복되지 않는다
    os.environ[_k] = _no_proxy

from clausetower.schemas import Citation, ForceMajeure, ForceMajeureJudgment, PenaltyTerms  # noqa: E402

MON = datetime(2026, 11, 2, 6, 0)   # 월요일 06:00
FRI = datetime(2026, 11, 6, 6, 0)   # 금요일 06:00


def cite(clause="제1조", quote="원문"):
    return Citation(clause=clause, quote=quote)


@pytest.fixture
def daily_terms():
    return PenaltyTerms(customer_id="X", basis="per_calendar_day", rate_pct=0.1, grace_hours=24, cap_pct=10,
                        citations={"rate": cite("제12조 제1항", "1,000분의 1"), "grace": cite("제12조 제2항", "24시간"),
                                   "cap": cite("제12조 제3항", "100분의 10")},
                        force_majeure=ForceMajeure(covered_events=["태풍"], notice_hours=24, citation=cite("제15조", "태풍")))


def judgment(applies: bool, has_clause: bool = True, reasoning="근거"):
    return ForceMajeureJudgment(customer_id="X", has_clause=has_clause, event_covered=applies, notice_ok=True,
                                applies=applies, reasoning=reasoning, citation=cite("제15조", "태풍"))
