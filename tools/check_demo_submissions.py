"""Default demo submissions stay temporary and never enter the manager's prepared day.

Run: python tools/check_demo_submissions.py
The stored-submission mode is covered separately by check_submissions.py.
"""
import os
from pathlib import Path
import sys
import tempfile

os.environ["CROSCAN_KEEP_SUBMISSIONS"] = "0"
os.environ["CROSCAN_DATA"] = tempfile.mkdtemp(prefix="croscan_demo_sub_")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import submissions, qa

created = []
for i in range(7):
    created.append(submissions.create("review", i, f"key-{i}", {"permit": b"%PDF-demo"},
                                      {"revision": i}, {"permit_no": f"P-{i}"}, i))
assert len(submissions._HELD) == 6
assert created[0]["id"] not in submissions._HELD
assert submissions.latest() == {}, "demo submissions must not change the manager's sample day"
payload, files, summary = submissions.get(created[-1]["id"])
assert payload["revision"] == 6 and submissions.file(files, "permit") == b"%PDF-demo"
again = submissions.create("review", 6, "key-6", {"permit": b"changed"}, {}, {}, 9)
assert again["again"] and again["id"] == created[-1]["id"]
assert not submissions.PDFS.exists() and not list(qa.DATA.iterdir()), "demo creation must not persist documents"
print("PASS: bounded temporary storage, unchanged manager data, original bytes, duplicate request, no disk writes")
