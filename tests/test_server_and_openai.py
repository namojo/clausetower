"""로컬 도우미 서버와 OpenAI 호환 모드."""
import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from clausetower.contracts import load_contract_text, load_golden_terms, load_scenario
from clausetower.llm import LLM
from clausetower.schemas import ExtractionResult, ForceMajeureJudgment
from clausetower.server import bind_warning, make_handler, origin_allowed

# 로컬 서버에 붙는 요청은 환경 프록시를 거치지 않는다(사내 프록시가 127.0.0.1 요청을 가로채 502를 돌려주는 것을 막는다)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
GOOD = "https://namojo.github.io"
EVIL = "https://evil.example"


def start(handler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


@pytest.fixture
def helper():
    srv, url = start(make_handler(LLM("mock")))
    yield url
    srv.shutdown()


def request(url, method="GET", obj=None, origin=GOOD, ctype="application/json", timeout=30):
    data = json.dumps(obj, ensure_ascii=False).encode() if obj is not None else None
    headers = {"content-type": ctype} if data is not None else {}
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with OPENER.open(req, timeout=timeout) as r:
            body = r.read().decode()
            return r.status, dict(r.headers), json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return e.code, dict(e.headers), json.loads(body) if body else None


def post(url, obj, origin=GOOD):
    return request(url, "POST", obj, origin=origin)


def test_health_and_cors(helper):
    status, h, body = request(helper + "/health", origin=None)
    assert status == 200 and body["ok"] and body["mode"] == "mock"
    assert "Access-Control-Allow-Origin" not in h, "Origin이 없는 요청(브라우저 밖)에는 CORS 헤더가 필요 없다"
    status, h, _ = request(helper + "/health", origin=GOOD)
    assert status == 200 and h["Access-Control-Allow-Origin"] == GOOD and h["Access-Control-Allow-Private-Network"] == "true"
    status, h, _ = request(helper + "/extract", "OPTIONS", origin=GOOD)
    assert status == 204 and h["Access-Control-Allow-Origin"] == GOOD


def test_cors_rejects_unlisted_origin(helper):
    """허용 목록 밖 출처는 사전 요청·본 요청 모두 403이고 CORS·PNA 허용 헤더가 없다(출처 반사 금지)."""
    for method, obj in (("OPTIONS", None), ("POST", {"customer_id": "Z", "text": "x" * 100}), ("GET", None)):
        status, h, _ = request(helper + ("/health" if method == "GET" else "/extract"), method, obj, origin=EVIL)
        assert status == 403, method
        assert "Access-Control-Allow-Origin" not in h and "Access-Control-Allow-Private-Network" not in h, method


def test_cors_allowlist_matching_and_extra_origins(monkeypatch):
    allowed = ["https://namojo.github.io", "http://localhost", "http://127.0.0.1"]
    assert origin_allowed("http://localhost:5500", allowed) and origin_allowed("http://127.0.0.1:8000", allowed)
    assert origin_allowed("https://namojo.github.io", allowed)
    assert not origin_allowed("https://namojo.github.io.evil.example", allowed)
    assert not origin_allowed("http://namojo.github.io", allowed), "스킴이 다르면 다른 출처다"
    assert not origin_allowed("null", allowed), "file:// 등 null 출처는 명시했을 때만 허용"
    monkeypatch.setenv("CLAUSETOWER_ALLOWED_ORIGINS", "https://intra.example.com")
    srv, url = start(make_handler(LLM("mock"), allowed_origins=["https://demo.example.org:8443"]))
    try:
        for o in ("https://intra.example.com", "https://demo.example.org:8443"):
            status, h, _ = request(url + "/health", origin=o)
            assert status == 200 and h["Access-Control-Allow-Origin"] == o
        assert request(url + "/health", origin="https://demo.example.org:9999")[0] == 403
    finally:
        srv.shutdown()


def test_post_requires_json_content_type(helper):
    """text/plain 단순 요청(no-cors)은 처리하지 않는다."""
    status, _, body = request(helper + "/extract", "POST", {"customer_id": "Z", "text": "x" * 100}, ctype="text/plain")
    assert status == 415 and "application/json" in body["error"]


def test_extract_and_judge_roundtrip(helper):
    text = load_contract_text("A")
    status, headers, body = post(helper + "/extract", {"customer_id": "Z", "text": text})
    assert status == 200 and headers["Access-Control-Allow-Origin"] == GOOD
    assert "fallback" not in body, "mock 모드의 자리표시자는 대체(fallback)로 표시하지 않는다"
    ex = ExtractionResult.model_validate(body)
    assert ex.terms.customer_id == "Z" and ex.confidence == 0.0 and "mock" in ex.ambiguities[0]  # 임의 본문은 자리표시자
    ev = load_scenario("typhoon").event
    status, _, body = post(helper + "/judge", {"customer_id": "Z", "terms": json.loads(load_golden_terms("A").model_dump_json()),
                                                "event": json.loads(ev.model_dump_json()), "text": text})
    j = ForceMajeureJudgment.model_validate(body)
    assert status == 200 and j.has_clause and j.applies is False


def test_bad_requests(helper):
    assert post(helper + "/extract", {"customer_id": "Z", "text": "짧다"})[0] == 400
    assert post(helper + "/nope", {})[0] == 404


def test_error_response_does_not_echo_input(helper):
    """500 응답에는 예외 종류와 필드 위치만 싣는다(입력값·모델 출력 원문을 되돌려 주지 않는다)."""
    terms = json.loads(load_golden_terms("A").model_dump_json())
    terms["basis"] = "<img src=x onerror=alert(1)>"
    status, _, body = post(helper + "/judge", {"customer_id": "Z", "terms": terms, "event": json.loads(load_scenario("typhoon").event.model_dump_json()), "text": "x"})
    assert status == 500 and body["error"] == "ValidationError" and "basis" in body["fields"]
    assert "<img" not in json.dumps(body, ensure_ascii=False)


def test_helper_marks_fallback_when_real_model_fails(monkeypatch):
    """실제 모드에서 LLM이 실패해 자리표시자가 돌아오면 응답에 fallback: true를 붙인다(웹은 그 결과를 쓰지 않는다)."""
    monkeypatch.setenv("CLAUSETOWER_OPENAI_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setattr("clausetower.llm.CLAUDE_TIMEOUT", 2)
    llm = LLM("openai")
    srv, url = start(make_handler(llm))
    try:
        status, _, body = post(url + "/extract", {"customer_id": "Z", "text": load_contract_text("A")})
        assert status == 200 and body.get("fallback") is True and llm.usage.fallbacks == 1
    finally:
        srv.shutdown()


def test_concurrent_llm_requests_are_limited(monkeypatch):
    """동시 LLM 요청이 상한을 넘으면 기다리지 않고 429를 돌려준다."""
    gate, entered = threading.Event(), threading.Event()
    import clausetower.server as server

    def slow_extract(llm, cid, text, mock_fn=None):
        entered.set()
        gate.wait(10)
        return server._mock_terms_for_text(cid)

    monkeypatch.setattr(server, "extract_terms_from_text", slow_extract)
    srv, url = start(make_handler(LLM("mock"), max_inflight=1))
    try:
        first: dict = {}
        t = threading.Thread(target=lambda: first.update(r=post(url + "/extract", {"customer_id": "Z", "text": "x" * 100})))
        t.start()
        assert entered.wait(10), "첫 요청이 처리에 들어가지 않았다"
        status, _, body = post(url + "/extract", {"customer_id": "Y", "text": "x" * 100})
        assert status == 429 and "동시 요청" in body["error"]
        gate.set()
        t.join(10)
        assert first["r"][0] == 200
    finally:
        gate.set()
        srv.shutdown()


def test_bind_warning_only_for_non_loopback():
    assert bind_warning("127.0.0.1") is None and bind_warning("localhost") is None and bind_warning("::1") is None
    assert "누구나" in bind_warning("0.0.0.0") and "누구나" in bind_warning("192.168.0.10")


class FakeOpenAI(BaseHTTPRequestHandler):
    """OpenAI 호환 chat/completions 흉내. 도구 호출로 정답지 조건을 돌려준다."""
    seen: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode())
        FakeOpenAI.seen.append((self.path, self.headers.get("authorization"), body["tool_choice"]))
        args = {"terms": json.loads(load_golden_terms("B").model_dump_json()), "confidence": 0.8, "ambiguities": []}
        resp = {"choices": [{"message": {"tool_calls": [{"function": {"name": "submit", "arguments": json.dumps(args, ensure_ascii=False)}}]}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        out = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def test_openai_compatible_mode(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAI)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("CLAUSETOWER_OPENAI_BASE_URL", f"http://127.0.0.1:{srv.server_address[1]}/v1")
        monkeypatch.setenv("CLAUSETOWER_OPENAI_API_KEY", "inhouse-token")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        llm = LLM("auto")
        assert llm.mode == "openai", "BASE_URL이 있으면 auto는 openai를 고른다(키 없을 때)"
        from clausetower.extract import extract_terms_from_text
        r = extract_terms_from_text(llm, "B", load_contract_text("B"))
        assert r.terms.basis == "per_hour" and r.confidence == 0.8 and llm.usage.calls == 1 and llm.usage.fallbacks == 0
        path, auth, choice = FakeOpenAI.seen[-1]
        assert path == "/v1/chat/completions" and auth == "Bearer inhouse-token" and choice["function"]["name"] == "submit"
    finally:
        srv.shutdown()


def test_openai_mode_falls_back_when_unreachable(monkeypatch):
    monkeypatch.setenv("CLAUSETOWER_OPENAI_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("CLAUSETOWER_CLAUDE_TIMEOUT", "2")
    llm = LLM("openai")
    from clausetower.extract import extract_terms_from_text
    r = extract_terms_from_text(llm, "Q", "x" * 100)
    assert llm.usage.fallbacks == 1 and r.confidence == 0.0
