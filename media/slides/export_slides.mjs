// Export every slide of deck.html for the PPTX builder:
//   pptx_src/sNN.png  (2× screenshot, 3840×2160)
//   pptx_src/slides.json  [{n, notes, vids:[{v, x, y, w, h}]}]   (boxes in 1920×1080 px)
import { chromium } from "file:///C:/Users/seoco/OneDrive/Desktop/PRAI/node_modules/playwright-core/index.mjs";
import path from "node:path";
import fs from "node:fs";

const dir = path.dirname(decodeURIComponent(new URL(import.meta.url).pathname).replace(/^\/(\w:)/, "$1"));
const out = path.join(dir, "pptx_src");
fs.mkdirSync(out, { recursive: true });
const b = await chromium.launch({ channel: "msedge", headless: true });
const page = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });
await page.goto("file:///" + path.join(dir, "deck.html").replace(/\\/g, "/"), { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);

const meta = await page.evaluate(() => [...document.querySelectorAll("section.slide")].map((s, i) => {
  const r = s.getBoundingClientRect();
  const notes = [...s.querySelectorAll(".notes")].map((e) => e.innerText.trim()).join("\n\n");
  const vids = [...s.querySelectorAll(".vid[data-v]")].map((e) => {
    const q = e.getBoundingClientRect();
    return { v: e.dataset.v, x: q.left - r.left, y: q.top - r.top, w: q.width, h: q.height };
  });
  return { n: i + 1, notes, vids };
}));
const slides = page.locator("section.slide");
for (let i = 0; i < meta.length; i++) {
  await slides.nth(i).screenshot({ path: path.join(out, `s${String(i + 1).padStart(2, "0")}.png`) });
}
fs.writeFileSync(path.join(out, "slides.json"), JSON.stringify(meta, null, 1));
console.log(`${meta.length} slides, ${meta.reduce((a, s) => a + s.vids.length, 0)} video boxes`);
await b.close();
