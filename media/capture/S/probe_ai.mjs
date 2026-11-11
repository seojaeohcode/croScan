// probe: free question (explain), near pair AI review box (no request), coord note, post-draft. Writes probe/*.png + probe/log.json
import fs from "node:fs";
import { chromium } from "file:///C:/Users/seoco/OneDrive/Desktop/PRAI/node_modules/playwright-core/index.mjs";
const OUT = "C:/Users/seoco/OneDrive/Desktop/조선톤개발/croScan_demo_videos/work19/S/probe/";
const log = {}; const L = (k, v) => { log[k] = v; fs.writeFileSync(OUT + "log.json", JSON.stringify(log, null, 1)); console.log("##", k, typeof v === "string" ? v.slice(0, 600) : JSON.stringify(v).slice(0, 600)); };
const b = await chromium.launch({ channel: "msedge", headless: true });
const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 }, locale: "ko-KR" });
const p = await ctx.newPage(); p.setDefaultTimeout(120000);
p.on("dialog", (d) => d.accept());
const sleep = (ms) => p.waitForTimeout(ms);
const shot = (n) => p.screenshot({ path: OUT + n + ".png" });
try {
  await p.goto("http://localhost:8776/"); await p.waitForSelector("#s-login:not([hidden])");
  await p.click('[data-login="safety"]'); await p.click(".login-go"); await p.waitForSelector("#s-safety:not([hidden])"); await sleep(4000);
  if (await p.isVisible("#sf-resume-close")) await p.click("#sf-resume-close");
  if (!(await p.isVisible("#sf-res"))) await p.click((await p.isVisible("#sfn-detect")) ? "#sfn-detect" : "#sf-detect");
  await p.waitForSelector("#sf-res:not([hidden])"); await sleep(2500);
  await shot("a_home");
  await p.locator('#sfn-list [data-ptab="1"]').first().click(); await sleep(1500);
  await p.evaluate(`[...document.querySelectorAll('#sf-plist .sf-prow')].find(r => r.innerText.replace(/\\s+/g,' ').includes('0731 × WP-01')).click()`); await sleep(4000);
  // 판정 근거·원문
  await p.evaluate(`document.querySelector('#sf-pdetail details.sf-pc-d').open = true`); await sleep(1500);
  await p.evaluate(`document.querySelector('#sf-pdetail .sf-jd').scrollIntoView({block:'start'})`); await sleep(800);
  L("jd_text", await p.innerText("#sf-pdetail .sf-jd"));
  await shot("b_jd");
  await p.evaluate(`document.querySelector('#sf-pdetail .sf-why').scrollIntoView({block:'center'})`); await sleep(500);
  await p.fill("#sf-pdetail .sf-why-ask input", "왜 1순위인가요?");
  const t0 = Date.now();
  await p.click("#sf-pdetail .sf-why-ask button[type=submit]");
  await sleep(1200); await shot("c_why_wait");
  await p.waitForFunction(`(() => { const o = document.querySelector('#sf-pdetail .sf-why-out'); return o && !/고르는 중|정리하는 중/.test(o.innerText) && o.innerText.trim().length > 0; })()`, null, { timeout: 90000 }).catch(() => {});
  L("why_secs", (Date.now() - t0) / 1000);
  await p.evaluate(`document.querySelector('#sf-pdetail .sf-why-out').scrollIntoView({block:'center'})`); await sleep(600);
  L("why_out", await p.innerText("#sf-pdetail .sf-why-out"));
  await shot("d_why_done");
  // the document open button inside judgement (for V13 comparison)
  L("jd_buttons", await p.evaluate(`[...document.querySelectorAll('#sf-pdetail .sf-jd [data-open]')].map(b=>b.dataset.open)`));
  // near pairs
  await p.locator('#sfn-list [data-ptab="near"]').first().click().catch(() => {}); await sleep(2000);
  L("near_rows", await p.evaluate(`[...document.querySelectorAll('#sf-plist .sf-nrow')].map(r=>r.dataset.near+' | '+r.innerText.replace(/\\s+/g,' '))`));
  await shot("e_near");
  const tgt = await p.evaluate(`(() => { const r = [...document.querySelectorAll('#sf-plist .sf-nrow')].find(r => r.dataset.near && /0735\\|?|WP-1029-15/.test(r.dataset.near)); return r ? r.dataset.near : null; })()`);
  L("near_keys_sample", tgt);
  await p.evaluate(`document.querySelector('#sf-plist .sf-nrow').click()`); await sleep(2500);
  L("near_detail", await p.innerText("#sf-pdetail"));
  await shot("f_near_detail");
  // ai list
  await p.evaluate(`document.querySelector('#sfn-list [data-ptab="ai"]')?.click()`); await sleep(2500);
  L("ai_list", await p.innerText("#sf-plist"));
  await shot("g_ai_list");
  // coord message for P02
  await p.locator('#sfn-list [data-ptab="1"]').first().click(); await sleep(1500);
  await p.evaluate(`[...document.querySelectorAll('#sf-plist .sf-prow')].find(r => r.innerText.replace(/\\s+/g,' ').includes('0731 × WP-01')).click()`); await sleep(3000);
  await p.locator("#sf-pdetail button:has-text('작업 조정 문자 작성')").first().click(); await sleep(1500);
  const t1 = Date.now();
  await p.waitForFunction(`(() => { const o = document.querySelector('#mg-note'); return o && !/찾는 중/.test(o.innerText); })()`, null, { timeout: 90000 }).catch(() => {});
  L("note_secs", (Date.now() - t1) / 1000);
  L("mg_note", await p.innerText("#mg-note").catch(() => "(none)"));
  L("panel", await p.innerText("#sf-panel").catch(() => ""));
  await shot("h_coord");
  // post: issue step, preview 0731
  await p.keyboard.press("Escape"); await sleep(1000);
  await p.locator('[data-pstep="issue"]').first().click().catch(() => {}); await sleep(3000);
  L("post_body_head", (await p.innerText("#sf-post-body").catch(() => "")).slice(0, 800));
  await p.evaluate(`[...document.querySelectorAll('#sf-post-body details')].find(d => /0731/.test(d.closest('li,article,div').innerText))?.setAttribute('open','')`); await sleep(1500);
  await p.evaluate(`(() => { const c = [...document.querySelectorAll('#sf-post-body details')].find(d => /0731/.test(d.closest('li,article,div').innerText))?.closest('li,article,div'); [...c.querySelectorAll('button')].find(b => /미리 보기/.test(b.innerText))?.click(); })()`); await sleep(4000);
  L("sheet_ai_buttons", await p.evaluate(`[...document.querySelectorAll('[data-shai-go]')].map(b=>b.dataset.shaiGo+' | '+b.closest('tr,section,div').innerText.slice(0,120))`));
  await shot("i_sheet");
  const t2 = Date.now();
  await p.evaluate(`document.querySelector('[data-shai-go]')?.click()`);
  await sleep(1500); await shot("j_sheet_wait");
  await p.waitForFunction(`!document.querySelector('.sh-ai[role=status]')`, null, { timeout: 120000 }).catch(() => {});
  L("draft_secs", (Date.now() - t2) / 1000);
  L("sheet_ai_box", await p.evaluate(`[...document.querySelectorAll('.sh-ai')].map(x=>x.innerText)`));
  await p.evaluate(`document.querySelector('.sh-ai-d, .sh-ai')?.scrollIntoView({block:'center'})`); await sleep(500);
  await shot("k_sheet_draft");
  L("sheet_text", await p.innerText("#sf-panel").catch(() => ""));
} catch (e) { L("error", String(e)); await shot("z_err"); }
await b.close();
