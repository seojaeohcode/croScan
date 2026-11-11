"""Merge the two manifest parts, zip the 21 clips, and join them into one combined video.

    python final_pack.py          → final19/manifest.md·json, croScan_시연영상_21클립.zip, croScan_시연영상_통합본.mp4
"""
import json
import re
import subprocess
import zipfile
from pathlib import Path

W = Path(__file__).parent
OUT = W.parent / "final19"
FF = "C:/Users/seoco/OneDrive/Desktop/PRAI/node_modules/ffmpeg-static/ffmpeg.exe"
CONTI_NAMES = ("croScan_최종콘티_수정반영본_2026-11-02.md", "croScan_최종자막_57개_수정반영본_2026-11-02.md")
CONTI = [W / n for n in CONTI_NAMES]
ORDER = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "14B",
         "15", "16", "17", "17B", "18", "19"]          # play order: V14B after V14, V17B after V17
CLIP = re.compile(r"croScan_V(\d\dB?)_")


def clips():
    found = {CLIP.match(p.name).group(1): p for p in OUT.glob("croScan_V*.mp4") if CLIP.match(p.name)}
    missing = [n for n in ORDER if n not in found]
    if missing or len(found) != len(ORDER):
        raise SystemExit(f"클립이 {len(ORDER)}개가 아닙니다: 없음 {missing}, 찾음 {sorted(found)}")
    return [found[n] for n in ORDER]


def secs(mp4):
    r = subprocess.run([FF, "-i", str(mp4)], capture_output=True, text=True, encoding="utf-8", errors="ignore")
    h, m, s = r.stderr.split("Duration:")[1].split(",")[0].strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def manifest(files):
    parts = []
    for k in "AS":
        p = W / k / "manifest_part.json"
        parts.append(json.loads(p.read_text(encoding="utf-8")) if p.exists() else {})
    md = [p.with_suffix(".md") for p in (W / "A" / "manifest_part.json", W / "S" / "manifest_part.json")]
    total = sum(secs(f) for f in files)
    head = ["# croScan 최종 시연영상 21클립 manifest", "",
            f"2026-11-02 · 수정 반영본 콘티·자막 57개 기준 · 클립 21개 · 합계 {int(total // 60)}분 {total % 60:.0f}초", "",
            "| 클립 | 파일 | 길이 |", "|---|---|---|"]
    head += [f"| V{CLIP.match(f.name).group(1)} | `{f.name}` | {secs(f):.1f}초 |" for f in files]
    head += ["", "통합본: `croScan_시연영상_통합본.mp4` (V01~V19·V14B·V17B를 재생 순서대로 이어 붙임).", ""]
    body = [m.read_text(encoding="utf-8") for m in md if m.exists()]
    (OUT / "manifest.md").write_text("\n".join(head) + "\n\n" + "\n\n".join(body), encoding="utf-8")
    (OUT / "manifest.json").write_text(json.dumps({"clips": [f.name for f in files], "A": parts[0], "S": parts[1]},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")


def combine(files):
    lst = W / "concat.txt"
    lst.write_text("".join(f"file '{f.as_posix()}'\n" for f in files), encoding="utf-8")
    dst = OUT / "croScan_시연영상_통합본.mp4"
    r = subprocess.run([FF, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(dst)],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if r.returncode or abs(secs(dst) - sum(secs(f) for f in files)) > 1.5:      # parameters differ → re-encode once
        subprocess.run([FF, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                        "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart",
                        str(dst)], check=True, capture_output=True)
    return dst


def pack(files):
    z = OUT / "croScan_시연영상_21클립.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_STORED) as zf:      # mp4 does not compress further; names stay UTF-8
        for f in files:
            zf.write(f, f.name)
            png = f.with_name(f.stem + "_대표화면.png")
            if png.exists():
                zf.write(png, "대표화면/" + png.name)
        for n in ("manifest.md", "manifest.json"):
            zf.write(OUT / n, n)
        for src, name in zip(CONTI, CONTI_NAMES):
            zf.write(src, "콘티/" + name)
    return z


if __name__ == "__main__":
    fs = clips()
    manifest(fs)
    z = pack(fs)
    c = combine(fs)
    print(f"zip {z.name} {z.stat().st_size / 1e6:.1f}MB · 통합본 {c.name} {secs(c):.1f}초 {c.stat().st_size / 1e6:.1f}MB")
