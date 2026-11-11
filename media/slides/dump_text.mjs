// deck.html → review/deck_text.md (visible text + notes of every slide, for fact review)
import { chromium } from "file:///C:/Users/seoco/OneDrive/Desktop/PRAI/node_modules/playwright-core/index.mjs";
import path from "node:path";
import fs from "node:fs";

const dir = path.dirname(decodeURIComponent(new URL(import.meta.url).pathname).replace(/^\/(\w:)/, "$1"));
const b = await chromium.launch({ channel: "msedge", headless: true });
const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
await p.goto("file:///" + path.join(dir, "deck.html").split(path.sep).join("/"), { waitUntil: "networkidle" });
const t = await p.evaluate(() => [...document.querySelectorAll("section.slide")].map((s, i) => {
  const notes = [...s.querySelectorAll(".notes")].map((e) => e.textContent.trim()).join("\n");
  const vis = s.innerText.replace(/\n{2,}/g, "\n");
  const vids = [...s.querySelectorAll(".vid[data-v]")].map((e) => e.dataset.v).join(",");
  return `## 쪽 ${i + 1}${vids ? " · 영상 " + vids : ""}\n${vis}\n[노트] ${notes}\n`;
}).join("\n"));
fs.mkdirSync(path.join(dir, "review"), { recursive: true });
fs.writeFileSync(path.join(dir, "review", "deck_text.md"), t);
console.log(t.length);
await b.close();
