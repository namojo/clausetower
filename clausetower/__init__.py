"""저장소 루트에서 설치 없이 `python -m clausetower ...`를 실행할 수 있게 하는 연결 패키지.

실제 코드는 src/clausetower에 있다(src 레이아웃). 저장소 루트에서 실행하면 Python이 이 폴더를 먼저 찾으므로,
패키지 검색 경로(__path__)를 src/clausetower로 돌려 같은 모듈을 불러온다. 배포 패키지에는 들어가지 않는다
(pyproject.toml의 packages.find where=["src"]). `pip install -e .`로 설치한 경우에도 같은 파일을 불러오므로 결과가 같다.
"""

import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src", "clausetower")
__path__ = [_SRC]
__file__ = _os.path.join(_SRC, "__init__.py")
with open(__file__, encoding="utf-8") as _f:
    exec(compile(_f.read(), __file__, "exec"))
