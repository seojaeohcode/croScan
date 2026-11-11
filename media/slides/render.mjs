// Render deck.html (one <section class="slide"> per 1920×1080 page) to PDF, plus optional PNG previews.
//   node render.mjs            → croScan_PPT_구성안.pdf
//   node render.mjs png 3,7    → prev/s03.png, prev/s07.png (for review)
import { chromium } from "file:///C:/Users/seoco/OneDrive/Desktop/PRAI/node_modules/playwright-core/index.mjs";
import path from "node:path";
import fs from "node:fs";

const dir = path.dirname(decodeURIComponent(new URL(import.meta.url).pathname).replace(/^\/(\w:)/, "$1"));
const url = "file:///" + path.join(dir, "deck.html").replace(/\\/g, "/");
const b = await chromium.launch({ channel: "msedge", headless: true });
const page = await b.newPage({ viewport: { width: 1920, height: 1080 } });
await page.goto(url, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);

const [mode, which] = process.argv.slice(2);
if (mode === "png") {
  fs.mkdirSync(path.join(dir, "prev"), { recursive: true });
  const n = await page.locator("section.slide").count();
  const want = which ? which.split(",").map(Number) : [...Array(n).keys()].map((i) => i + 1);
  for (const i of want) {
    const el = page.locator("section.slide").nth(i - 1);
    await el.screenshot({ path: path.join(dir, "prev", `s${String(i).padStart(2, "0")}.png`), scale: "css" });
  }
  // overflow audit: any element whose box leaves its slide
  const bad = await page.evaluate(() => [...document.querySelectorAll("section.slide")].flatMap((s, i) => {
    const r = s.getBoundingClientRect();
    return [...s.querySelectorAll("*")].filter((e) => {
      const q = e.getBoundingClientRect();
      return q.width && (q.right > r.right + 1 || q.bottom > r.bottom + 1 || e.scrollWidth > e.clientWidth + 2 && getComputedStyle(e).overflow === "hidden");
    }).slice(0, 3).map((e) => `s${i + 1}: <${e.tagName.toLowerCase()} class="${e.className}"> ${e.textContent.trim().slice(0, 40)}`);
  }));
  console.log(bad.length ? "OVERFLOW\n" + bad.join("\n") : "no overflow");
} else {
  await page.pdf({ path: path.join(dir, "croScan_PPT_구성안.pdf"), width: "1920px", height: "1080px", printBackground: true, preferCSSPageSize: true });
  console.log("pdf ok");
}
await b.close();
