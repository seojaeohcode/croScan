"""Wait until render_all.log says each clip is done (this batch), then package it. usage: python wait_pack.py v13 v14 ..."""
import subprocess
import sys
import time
from pathlib import Path

S = Path(__file__).parent
log = S / "render_all.log"
for v in sys.argv[1:]:
    for _ in range(900):
        txt = log.read_text(encoding="utf-8-sig", errors="ignore").split("--- 21-clip renders")[-1]
        if f"done {v} " in txt:
            break
        time.sleep(2)
    subprocess.run([sys.executable, str(S / "package21.py"), v], check=False)
