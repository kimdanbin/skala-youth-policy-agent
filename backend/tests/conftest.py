"""테스트가 어느 폴더에서 실행되든 backend/와 mcp_server/를 import 할 수 있게 경로를 잡는다."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "backend", ROOT / "mcp_server"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# 테스트(가짜 LLM)의 실행 기록이 LangSmith 프로젝트에 섞이지 않게 끈다.
# main.py의 load_dotenv는 이미 있는 환경변수를 덮어쓰지 않으므로 여기서 먼저 정해 두면 된다.
os.environ["LANGSMITH_TRACING"] = "false"

# 테스트는 가짜 검색만 쓴다. 실수로 실제 벡터 DB를 여는 코드가 불리면 조용히 건드리지 말고
# 바로 실패하도록, 없는 폴더를 가리키게 한다 (retriever가 "폴더가 없습니다" 오류를 낸다).
os.environ["VECTORSTORE_DIR"] = str(Path(__file__).resolve().parent / "_no_vectorstore_in_tests")
