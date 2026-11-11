// Density audit of deck.html: per slide, on-screen characters (without notes, source line, footer), smallest body
// font size, number of cards and tables. Flags slides a first-time reader would find crowded.
//   node density.mjs        → review/density.md
import { chromium } from "file:///C:/Users/seoco/OneDrive/Desktop/PRAI/node_modules/playwright-core/index.mjs";
import path from "node:path";
import fs from "node:fs";

const dir = path.dirname(decodeURIComponent(new URL(import.meta.url).pathname).replace(/^\/(\w:)/, "$1"));
const b = await chromium.launch({ channel: "msedge", headless: true });
const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
await p.goto("file:///" + path.join(dir, "deck.html").split(path.sep).join("/"), { waitUntil: "networkidle" });
await p.evaluate(() => document.fonts.ready);
const rows = await p.evaluate(() => [...document.querySelectorAll("section.slide")].map((s, i) => {
  const skip = (e) => e.closest(".notes,.note,.need,.ft,.vlab,.hd .badge,.hd .chip,.part .brand");
  let chars = 0, minF = 99;
  const walker = document.createTreeWalker(s, NodeFilter.SHOW_TEXT);
  for (let n; (n = walker.nextNode());) {
    const el = n.parentElement, t = n.textContent.replace(/\s+/g, "");
    if (!t || skip(el)) continue;
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || el.closest(".notes")) continue;
    chars += t.length;
    const f = parseFloat(cs.fontSize);
    if (f > 4 && !el.closest("svg")) minF = Math.min(minF, f);
  }
  const apx = s.classList.contains("apx"), cover = /cover|part|plan/.test(s.className);
  const cards = s.querySelectorAll(".card").length, tables = s.querySelectorAll("table").length, rowsN = s.querySelectorAll("table tr").length;
  const title = (s.querySelector(".hd h1")?.innerText || s.querySelector(".pt")?.innerText || "").replace(/\s+/g, " ").slice(0, 34);
  const lim = apx ? 700 : 380, fmin = apx ? 20 : 22;
  const flags = [];
  if (!cover && chars > lim) flags.push(`글자 ${chars}>${lim}`);
  if (!cover && minF < fmin) flags.push(`최소 ${minF}px`);
  if (cards > 6) flags.push(`카드 ${cards}`);
  if (!apx && rowsN > 7) flags.push(`표 ${rowsN}행`);
  return { n: i + 1, apx, title, chars, minF: minF === 99 ? "-" : minF, cards, tables, rowsN, flags };
}));
const md = ["| 쪽 | 제목 | 글자 | 최소px | 카드 | 표행 | 판정 |", "|---|---|---|---|---|---|---|",
  ...rows.map((r) => `| ${r.n}${r.apx ? " (부록)" : ""} | ${r.title} | ${r.chars} | ${r.minF} | ${r.cards} | ${r.rowsN} | ${r.flags.join(" · ") || "OK"} |`)];
fs.writeFileSync(path.join(dir, "review", "density.md"), md.join("\n"));
const bad = rows.filter((r) => r.flags.length);
console.log(`${rows.length} slides, flagged ${bad.length}`);
for (const r of bad) console.log(`${r.n}${r.apx ? "(부록)" : ""} ${r.title} :: ${r.flags.join(" · ")}`);
await b.close();
