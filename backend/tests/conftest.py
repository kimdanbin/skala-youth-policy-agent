"""테스트가 어느 폴더에서 실행되든 backend/와 mcp_server/를 import 할 수 있게 경로를 잡는다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "backend", ROOT / "mcp_server"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
