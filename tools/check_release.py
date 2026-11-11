"""Run the documented offline regression checks in isolated data directories.

Usage: python tools/check_release.py [--pdf]
No real LLM is called. --pdf includes the slower PDF-output regression scripts.
Requires Java 17+ and Node.js, in addition to requirements.txt.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"check_form_intact.py", "check_extract.py", "check_interpret.py", "check_release.py"}
SLOW = {"check_checklist.py", "check_reflect.py", "check_render.py"}
if "--pdf" not in sys.argv:
    SKIP |= SLOW

failed = []
with tempfile.TemporaryDirectory(prefix="croscan_checks_") as temp:
    scripts = [p for p in sorted((ROOT / "tools").glob("check_*.py")) if p.name not in SKIP]
    scripts.append(ROOT / "tools/eval_retrieval.py")
    for script in scripts:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1",
               "CROSCAN_DATA": str(Path(temp) / script.stem),
               "CROSCAN_KEEP_SUBMISSIONS": "1" if script.name in {"check_submissions.py", "check_submit_link.py"} else "0",
               "LLM_URL": "http://127.0.0.1:1/v1/chat/completions"}
        args = [sys.executable, "-u", str(script)]
        if script.name == "check_proxy_headers.py":
            args += ["--conf", "deploy/oidc-proxy/nginx.conf"]
        print(f"\n== {script.name} ==", flush=True)
        try:
            result = subprocess.run(args, cwd=ROOT, env=env, timeout=900)
            if result.returncode:
                failed.append(script.name)
        except subprocess.TimeoutExpired:
            failed.append(script.name + " (timeout)")
print(f"\nPassed {len(scripts) - len(failed)}/{len(scripts)} scripts")
if failed:
    print("Failed: " + ", ".join(failed))
sys.exit(bool(failed))
