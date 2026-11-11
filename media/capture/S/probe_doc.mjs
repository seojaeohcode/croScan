import fs from "node:fs";
import { chromium } from "file:///C:/Users/seoco/OneDrive/Desktop/PRAI/node_modules/playwright-core/index.mjs";
const OUT = "C:/Users/seoco/OneDrive/Desktop/조선톤개발/croScan_demo_videos/work19/S/probe/";
const b = await chromium.launch({ channel: "msedge", headless: true });
const p = await (await b.newContext({ viewport: { width: 1920, height: 1080 }, locale: "ko-KR" })).newPage(); p.setDefaultTimeout(60000);
const sleep = (ms) => p.waitForTimeout(ms);
await p.goto("http://localhost:8776/#safety/2026-10-29/P02"); await p.waitForSelector("#s-safety:not([hidden])"); await sleep(6000);
console.log("detail head:", (await p.innerText("#sf-pdetail").catch(()=>"")).slice(0,200));
await p.evaluate(`document.querySelector('#sf-pdetail details.sf-pc-d').open = true`); await sleep(1000);
for (const id of ["WP-1029-01", "0731"]) {
  await p.evaluate(`document.querySelector('#sf-pdetail .sf-jd [data-open="${id}"]').click()`); await sleep(5000);
  await p.screenshot({ path: OUT + "doc_" + id + ".png" });
  console.log("== panel", id, (await p.innerText("#sf-panel")).slice(0, 1500));
  console.log("imgs", await p.evaluate(`[...document.querySelectorAll('#sf-panel img, #sf-panel canvas')].map(i=>i.tagName+' '+(i.src||'').slice(-60)+' '+i.width+'x'+i.height)`));
  await p.keyboard.press("Escape"); await sleep(1500);
}
await b.close();
