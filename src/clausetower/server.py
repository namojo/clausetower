"""로컬 도우미 서버. 웹 데모(GitHub Pages)가 이 PC의 LLM 연결로 계약을 읽게 해 준다.

  python -m clausetower serve --port 8787 --llm claude-code     # Claude 구독(CLI)
  CLAUSETOWER_OPENAI_BASE_URL=https://사내게이트웨이/v1 python -m clausetower serve --llm openai   # 사내 LLM

엔드포인트(모두 JSON):
  GET  /health                  {ok, mode, model, calls, fallbacks}
  POST /extract {customer_id, text}                      → ExtractionResult (+ fallback: true면 실제 모델 실패로 자리표시자)
  POST /judge   {customer_id, terms, event, text}        → ForceMajeureJudgment (+ fallback: true면 자리표시자)
CORS는 허용 출처 목록으로만 연다. 기본은 배포 출처 https://namojo.github.io 와 로컬 개발 출처 http://localhost·127.0.0.1(포트 무관)이고,
serve --allow-origin 이나 환경 변수 CLAUSETOWER_ALLOWED_ORIGINS(쉼표 구분)로 더한다. 목록 밖 출처의 요청은 403으로 거절하고
CORS·Private Network 허용 헤더를 붙이지 않는다. POST는 Content-Type: application/json만 받는다(단순 요청 차단).
Origin 헤더가 없는 요청(curl·시험)은 브라우저가 아니므로 허용한다.
계약서 본문은 메모리에서만 다루고 디스크에 쓰지 않는다. 요청 로그에는 메서드와 경로만 남긴다.
오류 응답에는 예외 종류(검증 오류면 필드 위치)만 싣고, 자세한 내용은 이 PC의 로그(stderr)에만 남긴다.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from pydantic import ValidationError

from .extract import _mock_judgment_for_text, _mock_terms_for_text, extract_terms_from_text, judge_from_text
from .llm import LLM
from .schemas import EventContext, PenaltyTerms

log = logging.getLogger("clausetower.server")
MAX_BODY = 2 * 1024 * 1024
DEFAULT_ALLOWED_ORIGINS = ("https://namojo.github.io", "http://localhost", "http://127.0.0.1", "http://[::1]")
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def _parse_origin(origin: str) -> tuple[str, str, int | None] | None:
    try:
        u = urlsplit(origin.strip())
        return (u.scheme.lower(), (u.hostname or "").lower(), u.port) if u.scheme and u.hostname else None
    except ValueError:
        return None


def allowed_origin_list(extra: list[str] | None = None) -> list[str]:
    env = [x.strip() for x in os.environ.get("CLAUSETOWER_ALLOWED_ORIGINS", "").split(",") if x.strip()]
    out: list[str] = []
    for o in [*DEFAULT_ALLOWED_ORIGINS, *env, *(extra or [])]:
        o = o.strip().rstrip("/")
        if o and o not in out:
            out.append(o)
    return out


def origin_allowed(origin: str, allowed: list[str]) -> bool:
    """출처가 허용 목록에 있는가. 목록 항목에 포트가 없으면 포트와 무관하게 비교한다. 'null'은 목록에 명시했을 때만 허용."""
    if origin == "null":
        return "null" in allowed
    got = _parse_origin(origin)
    if not got:
        return False
    for a in allowed:
        want = _parse_origin(a)
        if want and want[0] == got[0] and want[1] == got[1] and (want[2] is None or want[2] == got[2]):
            return True
    return False


def bind_warning(host: str) -> str | None:
    if host.strip().lower() in LOOPBACK_HOSTS:
        return None
    return (f"주의: {host}에 바인딩했다. 같은 네트워크의 누구나 이 PC의 LLM 연결(구독·사내 토큰)을 쓸 수 있다. "
            "인증이 없으니 시연이 끝나면 끄고, 평소에는 기본값 127.0.0.1을 쓴다.")


def make_handler(llm: LLM, allowed_origins: list[str] | None = None, max_inflight: int | None = None):
    allowed = allowed_origin_list(allowed_origins)
    # 동시 LLM 요청 상한. 웹 데모의 '면책 다시 판단'은 4개를 병렬로 보내므로 최소 4로 둔다.
    inflight = threading.BoundedSemaphore(max_inflight or max(4, llm.concurrency))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # 본문 내용이 로그에 남지 않게 한다
            log.info("%s %s", self.command, self.path)

        def _origin_state(self) -> str:
            """'none'(Origin 없음: 브라우저 밖), 'ok'(허용 출처), 'denied'."""
            origin = self.headers.get("Origin")
            if origin is None:
                return "none"
            return "ok" if origin_allowed(origin, allowed) else "denied"

        def _cors(self):
            self.send_header("Vary", "Origin")
            if self._origin_state() != "ok":
                return
            self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin"))
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "content-type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Max-Age", "600")

        def _send(self, code: int, obj) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _deny_origin(self) -> bool:
            if self._origin_state() == "denied":
                log.warning("허용 목록 밖 출처의 요청을 거절했다: %s", (self.headers.get("Origin") or "")[:100])
                self._send(403, {"error": "허용되지 않은 출처다. serve --allow-origin 으로 추가할 수 있다"})
                return True
            return False

        def do_OPTIONS(self):
            if self._deny_origin():
                return
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self):
            if self._deny_origin():
                return
            if self.path.split("?")[0] == "/health":
                return self._send(200, {"ok": True, "mode": llm.mode, "model": llm.model, "calls": llm.usage.calls, "fallbacks": llm.usage.fallbacks})
            self._send(404, {"error": "없는 경로"})

        def do_POST(self):
            if self._deny_origin():
                return
            path = self.path.split("?")[0]
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                return self._send(415, {"error": "Content-Type은 application/json이어야 한다"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_BODY:
                    return self._send(413 if length > MAX_BODY else 411, {"error": "본문 길이가 올바르지 않다"})
                req = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._send(400, {"error": "JSON 해석 실패"})
            if path not in ("/extract", "/judge"):
                return self._send(404, {"error": "없는 경로"})
            if not inflight.acquire(blocking=False):
                return self._send(429, {"error": "동시 요청이 너무 많다. 잠시 뒤 다시 시도하라"})
            try:
                used_mock: list[bool] = []
                if path == "/extract":
                    cid = str(req.get("customer_id") or "X")
                    text = str(req.get("text") or "")
                    if len(text) < 40:
                        return self._send(400, {"error": "계약서 본문이 너무 짧다"})
                    r = extract_terms_from_text(llm, cid, text, mock_fn=lambda: (used_mock.append(True), _mock_terms_for_text(cid))[1])
                else:
                    cid = str(req.get("customer_id") or "X")
                    terms = PenaltyTerms.model_validate(req["terms"])
                    event = EventContext.model_validate(req["event"])
                    r = judge_from_text(llm, cid, terms, event, str(req.get("text") or ""),
                                        mock_fn=lambda: (used_mock.append(True), _mock_judgment_for_text(cid, terms))[1])
                out = json.loads(r.model_dump_json())
                if used_mock and llm.mode != "mock":
                    out["fallback"] = True  # 실제 모델 호출이 실패해 자리표시자가 돌아왔다. 웹은 이 결과를 쓰지 않는다
                return self._send(200, out)
            except Exception as e:  # noqa: BLE001
                log.exception("요청 처리 실패")
                err: dict = {"error": type(e).__name__}
                if isinstance(e, ValidationError):
                    err["fields"] = [".".join(str(p) for p in x.get("loc", ())) for x in e.errors()[:10]]
                elif isinstance(e, KeyError):
                    err["fields"] = [str(e.args[0]) if e.args else "?"]
                return self._send(500, err)
            finally:
                inflight.release()

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8787, llm: LLM | None = None, allowed_origins: list[str] | None = None) -> None:
    llm = llm or LLM()
    httpd = ThreadingHTTPServer((host, port), make_handler(llm, allowed_origins))
    httpd.daemon_threads = True
    print(f"ClauseTower 로컬 도우미: http://{host}:{port}  (LLM 모드 {llm.mode}, 모델 {llm.model}). 웹 데모의 '로컬 도우미'에 이 주소를 넣는다.", flush=True)
    print(f"허용 출처: {', '.join(allowed_origin_list(allowed_origins))} (추가: --allow-origin 또는 CLAUSETOWER_ALLOWED_ORIGINS)", flush=True)
    warn = bind_warning(host)
    if warn:
        print(warn, file=sys.stderr, flush=True)
    if llm.mode == "mock":
        print("주의: mock 모드다. 실제 분석이 아니라 자리표시자 결과가 나온다. --llm claude-code 또는 환경변수를 확인하라.", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    serve()
