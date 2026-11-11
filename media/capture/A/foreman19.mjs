// croScan foreman flow on staging for the final 19-clip set (V01–V11, captions 1–29), shot for PRAI.
// mode "A": the whole foreman flow in one run (plans → kinds → 0731 → first question → long answer → card → quote → confirm →
//           key-information window → spark/fire item and controls → AI candidate (quote, adopted by the foreman) → 위험한 이유 + case →
//           관련 자료 (back on the review screen) → submit → the submission's PDFs).
// mode "B": the same start, the typo answer only.  mode "P": a probe (A without the submission, logs every candidate, case and reference).
// Every shot is the real screen; log_<mode>.json keeps what was typed and what the app actually answered.
import fs from "node:fs";
import path from "node:path";

const BASE = "http://localhost:8776/";
const DAY = "C:/Users/seoco/OneDrive/Desktop/조선톤개발/croScan_github/samples/시연_하루";
export const SAY = {   // 콘티 §5, word for word
  A: "작업은 오후 1시부터 3시까지 해요. 장소는 3BAY 08~10칼럼 E42P 블록 상부고요. 아크 가우징하고 CO2 용접할 예정입니다.",
  B: "자겁은 오후 1시부터 3시까지 해요. 장소는 3BAY 08~10칼럼 E42P 블록 상부구요. 아크 가우징하고 CO2 용접할 예정임니다.",
};
const PICK = ["이 시간 내내 함", "잔불 확인·정리까지 포함", "CO2", "없음 · 검토 마치기", "모름"];   // never 「가스 안 씀」: the answer said CO2 welding

export async function foreman({ page, shot }, mode, outDir) {
  const take = mode === "B" ? "B" : "A", P = mode === "P" ? "P" : take;
  const logFile = path.join(outDir, `log_${P}.json`), log = { mode, typed: SAY[take], events: [] };
  const ev = (k, v) => { log.events.push({ k, v, at: new Date().toISOString() }); fs.writeFileSync(logFile, JSON.stringify(log, null, 1)); console.log(`  [${P}] ${k}:`, (typeof v === "string" ? v : JSON.stringify(v)).slice(0, 300)); };
  const sleep = (ms) => page.waitForTimeout(ms);
  const S = (n) => `${P}_${n}`;
  // mark an element for measuring with data-cap (never touch the app's own ids)
  const tag = (js, id) => page.evaluate(`(() => { document.querySelectorAll('[data-cap=${JSON.stringify(id)}]').forEach(x => x.removeAttribute('data-cap')); const e = (${js}); if (e) e.setAttribute('data-cap', ${JSON.stringify(id)}); return !!e; })()`);
  const txt = (sel) => page.innerText(sel).catch(() => "");
  const center = (sel) => page.evaluate(`document.querySelector(${JSON.stringify(sel)})?.scrollIntoView({ block: 'center' })`);
  const t0 = Date.now(); const el = () => `${Math.round((Date.now() - t0) / 1000)}s`;
  page.setDefaultTimeout(300000);

  await page.goto(BASE); await page.waitForSelector("#s-login:not([hidden])");
  if (await page.locator('[data-login="foreman"]').count()) await page.click('[data-login="foreman"]');
  await sleep(500);
  await shot(S("s01_login"), { roles: "#login-roles", go: ".login-go", foreman: '[data-login="foreman"]' });
  await page.click(".login-go"); await page.waitForSelector("#s-plans:not([hidden])"); await sleep(1200);

  // V01: plans in two formats — a partner company (동성화인텍) and the in-house team (대조립1부-운반1팀)
  const plans = [`${DAY}/작업계획서/WP-1029-01_동성화인텍.pdf`, `${DAY}/작업계획서/WP-1029-10_대조립1부-운반1팀.pdf`];
  await page.setInputFiles("#wpfile", plans); await sleep(1500);
  await shot(S("s02_pick"), { drop: "#wpdrop", list: "#wp-list", start: "#wp-start" });
  await page.click("#wp-start");
  for (let i = 0; i < 100 && (await page.locator("button.plan-check").count()) < 2; i++) await sleep(3000);
  await sleep(3000);
  ev("plans_list", await txt("#plan-list"));
  await tag(`document.querySelector('#plan-list li, #plan-list .plan-row, #plan-list [data-plan]')`, "cap-plan1");
  await shot(S("s03_read"), { sheet: "#sheet", list: "#plan-list", left: "#plans-left", plan1: "[data-cap=cap-plan1]" });
  const items = page.locator("#plan-list li, #plan-list .plan-row, #plan-list [data-plan]");
  if ((await items.count()) > 1) {
    await items.nth(1).click({ position: { x: 30, y: 12 } }).catch(() => {}); await sleep(2500);
    await tag(`[...document.querySelectorAll('#plan-list li, #plan-list .plan-row, #plan-list [data-plan]')][1]`, "cap-plan2");
    await shot(S("s04_read2"), { sheet: "#sheet", list: "#plan-list", plan2: "[data-cap=cap-plan2]" });
  }
  for (let r = 0; r < 3; r++) {
    for (let i = 0; i < (await page.locator("button.plan-check").count()); i++) {
      const bt = page.locator("button.plan-check").nth(i);
      if ((await bt.getAttribute("aria-pressed")) !== "true") { await bt.click(); await sleep(1000); }
    }
    if (await page.isEnabled("#go-submit")) break;
  }
  await shot(S("s05_checked"), { list: "#plan-list", left: "#plans-left", next: "#go-submit", checks: "button.plan-check" });
  await page.click("button:has-text('다음: 허가서 올리기')"); await page.waitForSelector("#s-upload:not([hidden])"); await sleep(1200);

  // V02: the permit kinds, then 화기 + 0731
  ev("kinds", await txt("#kinds"));
  await shot(S("s06_kinds"), { kinds: "#kinds", drop: "#drop" });
  await page.click("#kinds button:has-text('화기')");
  await tag(`[...document.querySelectorAll('#kinds button')].find(b => b.innerText.includes('화기'))`, "cap-hot");
  await page.setInputFiles("#file", `${DAY}/허가서/0731_화기_A.pdf`); await sleep(1200);
  await shot(S("s07_ready"), { kinds: "#kinds", hot: "[data-cap=cap-hot]", drop: "#drop", start: "#start" });
  await page.click("#start");
  await page.waitForSelector("#s-edit:not([hidden]) #msgs .msg", { timeout: 400000 }); await sleep(9000);
  ev("t_review", el());

  const keys = await page.evaluate(`[...document.querySelectorAll('#sheet .fi[data-key]')].map(e => e.dataset.key + '=' + e.innerText.replace(/\\s+/g, ' ').slice(0, 40))`);
  ev("fields", keys);
  await tag(`[...document.querySelectorAll('#msgs .msg.ai')].pop()`, "cap-q");
  ev("first_question", await txt("[data-cap=cap-q]"));
  const TIME = ['#sheet .fi[data-key="p1.date_1"]', '#sheet .fi[data-key="p1.from_1"]', '#sheet .fi[data-key="p1.to_1"]'];
  await shot(S("s08_review"), { sheet: "#sheet", msgs: "#msgs", question: "[data-cap=cap-q]", location: '#sheet .fi[data-key="p1.location"]',
    time: TIME, detail: '#sheet .fi[data-key="p1.job_detail"]', composer: "#composer" });

  // V03 / V04: one long spoken answer (A) or the same facts with typos (B), from the same clean start
  await page.fill("#input", SAY[take]); await sleep(600);
  await shot(S("s09_typed"), { composer: "#composer", input: "#input", question: "[data-cap=cap-q]", msgs: "#msgs" });
  const sent = Date.now();
  await page.click("#send");
  await page.waitForSelector(".ai-card", { timeout: 300000 });
  let cardText = "";
  for (let i = 0; i < 150; i++) {
    cardText = await page.locator(".ai-card").last().innerText();
    if (/확인 \(\d+건\)|AI 결과를 준비하지 못함|확인한 우리 작업 정보/.test(cardText) && !/답 해석 중|결과 검사 중|대기 중/.test(cardText)) break;
    await sleep(2000);
  }
  ev("ai_wait_s", Math.round((Date.now() - sent) / 1000));
  // the status line above the input catches up on its own poll: wait for it so the card and the line agree
  for (let i = 0; i < 15; i++) { const l = await page.evaluate(`(() => { const e = document.querySelector('#ai-line'); return e && !e.hidden ? e.innerText : ''; })()`); if (!/해석 중|검사 중|대기 중/.test(l)) break; await sleep(2000); }
  ev("ai_line", await page.evaluate(`(() => { const e = document.querySelector('#ai-line'); return e && !e.hidden ? e.innerText : '(hidden)'; })()`));
  await sleep(2000);
  await tag(`[...document.querySelectorAll('.ai-card')].pop()`, "cap-card");
  await page.evaluate(`document.querySelector('[data-cap=cap-card]')?.scrollIntoView({ block: 'center' })`); await sleep(800);
  const cardRows = `[...document.querySelectorAll('[data-cap=cap-card] .spill-list li')]`;
  await tag(`${cardRows}.find(l => /작업시간/.test(l.innerText))`, "cap-ctime");
  await tag(`${cardRows}.find(l => /작업장소|위치/.test(l.innerText))`, "cap-cloc");
  await tag(`document.querySelector('[data-cap=cap-cloc] .q')`, "cap-cquote");
  await tag(`document.querySelector('[data-cap=cap-cloc] .ai-dest')`, "cap-cdest");
  const co2Tags = async () => {
    await tag(`[...document.querySelectorAll('[data-cap=cap-card] .spill-list li')].find(l => /공법|가스/.test(l.innerText))`, "cap-cco2");
    await tag(`document.querySelector('[data-cap=cap-cco2] .q')`, "cap-co2q");
    await tag(`document.querySelector('[data-cap=cap-cco2] .ai-dest')`, "cap-co2d");
    await tag(`document.querySelector('[data-cap=cap-cco2] b')`, "cap-co2v");
  };
  await co2Tags();
  ev("card", await txt("[data-cap=cap-card]"));
  ev("card_html", (await page.evaluate(`document.querySelector('[data-cap=cap-card]')?.outerHTML || ''`)).slice(0, 6000));
  const CARD = { card: "[data-cap=cap-card]", time: "[data-cap=cap-ctime]", loc: "[data-cap=cap-cloc]", quote: "[data-cap=cap-cquote]", dest: "[data-cap=cap-cdest]",
    ok: "[data-cap=cap-card] [data-rd-ok]", fix: "[data-cap=cap-cloc] [data-rd-fix]", msgs: "#msgs", sheet: "#sheet",
    co2: "[data-cap=cap-cco2]", co2q: "[data-cap=cap-co2q]", co2d: "[data-cap=cap-co2d]", co2v: "[data-cap=cap-co2v]", co2chip: "[data-cap=cap-cco2] .ai-chip",
    head: "[data-cap=cap-card] .spill-h", rows: "[data-cap=cap-card] .spill-list" };
  await shot(S("s10_card"), CARD);
  // 2026-11-02 15h conti: V05–V11 continue from the typo answer (take B), so B runs the whole flow too

  // V05: a value that needs fixing (the 「고」 of 「상부고요」 kept in the place) is fixed by the foreman with 「항목 고치기」, then confirmed
  ev("card_buttons", await page.evaluate(`[...document.querySelectorAll('[data-cap=cap-card] button')].map(b => b.innerText.trim())`));
  const locVal = await page.evaluate(`document.querySelector('[data-cap=cap-cloc] b')?.innerText || ''`);
  ev("card_location_value", locVal);
  let fixed = false;
  if (/상부(고|구)\s*$/.test(locVal.trim()) && (await page.locator("[data-cap=cap-cloc] [data-rd-fix]").count())) {
    await page.evaluate(`document.querySelector('[data-cap=cap-cloc] [data-rd-fix]').click()`); await sleep(800);
    const inp = page.locator("[data-cap=cap-card] .rd-fix input");
    ev("fix_before", await inp.inputValue().catch(() => ""));
    await inp.fill("3BAY 08~10칼럼 E42P 블록 상부"); await sleep(500);
    await tag(`document.querySelector('[data-cap=cap-card] .rd-fix')`, "cap-fixrow");
    await shot(S("s11_fix"), { ...CARD, fixrow: "[data-cap=cap-fixrow]", save: "[data-cap=cap-card] [data-rd-fixsave]" });
    await page.evaluate(`document.querySelector('[data-cap=cap-card] [data-rd-fixsave]').click()`); await sleep(6000);
    fixed = true;
    ev("after_fix_card", await txt("[data-cap=cap-card]"));
  }
  ev("fixed", fixed);
  const ok = page.locator("[data-cap=cap-card] [data-rd-ok]").first();
  if ((await ok.count()) && (await ok.isEnabled())) {
    await tag(`[...document.querySelectorAll('.ai-card')].pop()`, "cap-card"); await co2Tags();
    await shot(S("s12_beforeok"), { card: "[data-cap=cap-card]", ok: "[data-cap=cap-card] [data-rd-ok]", msgs: "#msgs", co2: "[data-cap=cap-cco2]", co2q: "[data-cap=cap-co2q]",
      co2d: "[data-cap=cap-co2d]", rows: "[data-cap=cap-card] .spill-list", answer: "[data-cap=cap-card] ~ .msg.user, #msgs .msg.user" });
    await ok.click(); await sleep(5000);
  }
  ev("card_after", await txt("[data-cap=cap-card]"));
  ev("fields_after", await page.evaluate(`[...document.querySelectorAll('#sheet .fi[data-key]')].map(e => e.dataset.key + '=' + e.innerText.replace(/\\s+/g, ' ').slice(0, 60) + (e.classList.contains('answered') ? ' (answered)' : '')).filter(s => /answered/.test(s))`));
  await co2Tags();
  await shot(S("s13_applied"), { sheet: "#sheet", answered: "#sheet .fi.answered", co2: "[data-cap=cap-cco2]", co2chip: "[data-cap=cap-cco2] .ai-chip", location: '#sheet .fi[data-key="p1.location"]', time: TIME,
    detail: '#sheet .fi[data-key="p1.job_detail"]', msgs: "#msgs", card: "[data-cap=cap-card]" });

  // the remaining questions, answered with the buttons
  const live = async (t) => { for (const b of (await page.locator(`#msgs button:has-text('${t}')`).all()).reverse()) if ((await b.isVisible()) && (await b.isEnabled()) && !((await b.getAttribute("class")) || "").includes("picked")) return b; return null; };
  const answered = [], asked = [];
  for (let i = 0; i < 45 && !(await page.isVisible("#go-plans")); i++) {
    let hit = null; for (const t of PICK) { hit = await live(t); if (hit) { asked.push(await page.evaluate(`[...document.querySelectorAll('#msgs .msg.ai')].pop()?.innerText.slice(0, 200) || ''`)); answered.push(t); break; } }
    if (hit) { await hit.click(); await sleep(5000); } else await sleep(4000);
  }
  ev("remaining_questions", asked); ev("remaining_answers", answered);
  // every 「왜 묻나요?」 with 관련 자료, for V10 (read now, opened again later on this same screen)
  const whys = await page.evaluate(`[...document.querySelectorAll('#msgs .why-box')].map((b, i) => ({ i, q: b.closest('.msg')?.innerText.split('\\n')[0].slice(0, 120), refs: b.querySelectorAll('.why-refs li').length, text: b.innerHTML.replace(/<[^>]+>/g, ' ').replace(/\\s+/g, ' ').slice(0, 900) }))`);
  ev("why_boxes", whys);
  await shot(S("s14_done"), { sheet: "#sheet", msgs: "#msgs", next: "#go-plans" });

  // V06: 「다음: 위험 체크리스트」 opens the key-information window
  await page.click("#go-plans"); await sleep(3000);
  if (await page.isVisible("#presub")) {
    await page.waitForSelector("#ps-ok:not([disabled])", { timeout: 200000 }); await sleep(1500);
    ev("popup", await txt("#presub"));
    ev("popup_html", (await page.evaluate(`document.querySelector('#ps-body').innerHTML`)).slice(0, 4000));
    const row = (k) => `[...document.querySelectorAll('#ps-body dt')].find(d => d.textContent.replace(/\\s+/g, '').startsWith(${JSON.stringify(k.replace(/\s+/g, ""))}))?.parentElement`;
    await tag(row("작업일·작업시간"), "cap-pstime"); await tag(row("작업 위치"), "cap-psloc"); await tag(row("작업 내용"), "cap-psjob");
    await shot(S("s15_popup"), { dialog: "#presub .dialog", body: "#ps-body", ok: "#ps-ok", lead: "#ps-lead", open: "#ps-body .ps-open",
      time: "[data-cap=cap-pstime]", loc: "[data-cap=cap-psloc]", job: "[data-cap=cap-psjob]", rows: "#ps-body .ps-list" });
    await page.click("#ps-ok");
  } else ev("popup", "(no window)");
  await page.waitForSelector("#s-check:not([hidden])"); await sleep(4000);

  // V07: the checklist and the spark/fire item
  // the AI candidates (a background model call that a more urgent call can take the model from): when it comes back
  // 「AI 결과를 준비하지 못함」, the checklist is opened again from the stepper, which asks again (at most 4 times; every try logged)
  const ckWait = async () => { for (let i = 0; i < 90; i++) { const s = await page.evaluate(`st.ckAi ? st.ckAi.status : 'none'`); if (s !== "loading") break; await sleep(2000); } };
  await ckWait();
  for (let a = 1; a <= 6; a++) {
    const s = await page.evaluate(`st.ckAi ? { status: st.ckAi.status, items: st.ckAi.items.length, marks: Object.keys(st.ckAi.marks || {}).length } : null`);
    ev(`ck_ai_try${a}`, s);
    if (!s || s.status !== "fail") break;
    if (a === 6) break;
    await sleep(45000);   // the model is shared (other takes run too): give it time before asking again
    await page.evaluate(`document.querySelector('#stepper li[data-step="4"] button').click()`); await sleep(3000);
    if (await page.isVisible("#presub")) { await page.waitForSelector("#ps-ok:not([disabled])"); await page.click("#ps-ok"); await sleep(2000); }
    await ckWait();
  }
  ev("ck_ai_status", await page.evaluate(`st.ckAi ? { status: st.ckAi.status, items: st.ckAi.items.length, marks: Object.keys(st.ckAi.marks || {}).length } : null`));
  await sleep(1500);
  ev("check_bar", await txt("#ck-bar"));
  ev("ck_items", await page.evaluate(`[...document.querySelectorAll('#ck-list .ck-item')].map(e => e.querySelector('.ck-title')?.innerText.replace(/\\s+/g, ' '))`));
  ev("ck_candidates", await page.evaluate(`[...document.querySelectorAll('#ck-list .ck-cand, #ck-list .ck-cand-status')].map(e => e.innerText)`));
  ev("ck_marks", await page.evaluate(`[...document.querySelectorAll('#ck-list .ck-mark')].map(e => (e.closest('.ck-item')?.querySelector('.ck-title')?.innerText || '') + ' :: ' + e.innerText)`));
  ev("ck_ai_raw", await page.evaluate(`JSON.stringify(st.ckAi).slice(0, 8000)`));
  await shot(S("s16_check"), { bar: "#ck-bar", card: "#s-check .ck-card", list: "#ck-list" });
  const FIRE = `[...document.querySelectorAll('#ck-list .ck-item')].find(e => /불티/.test(e.innerText)) || [...document.querySelectorAll('#ck-list .ck-item')].find(e => /화재/.test(e.innerText))`;
  const fireRects = () => ({ fire: "[data-cap=cap-fire]", head: "[data-cap=cap-fire] .ck-head", why: "[data-cap=cap-fire] .ck-why", reason: "[data-cap=cap-fire] .ck-reason",
    seg: "[data-cap=cap-fire] .ck-seg", ok: "[data-cap=cap-fire] .ck-ok:not(.ck-ctl-ok)", ctl: "[data-cap=cap-fire] .ck-ctrls", ctlok: "[data-cap=cap-fire] .ck-ctl-ok",
    ctl1: "[data-cap=cap-fire] .ck-ctrl", done: "[data-cap=cap-fire] .ck-done", mark: "[data-cap=cap-fire] .ck-mark",
    xwhy: "[data-cap=cap-fire] .x-why", bar: "#ck-bar" });
  if (await tag(FIRE, "cap-fire")) {
    await center("[data-cap=cap-fire]"); await sleep(1200);
    ev("fire_item", await txt("[data-cap=cap-fire]"));
    ev("fire_html", (await page.evaluate(`document.querySelector('[data-cap=cap-fire]').outerHTML`)).slice(0, 5000));
    await shot(S("s17_fire"), fireRects());
    // DOM clicks: the sticky progress bar can cover these buttons, which makes a pointer click wait forever
    const cls = await page.evaluate(`document.querySelector('[data-cap=cap-fire] .ck-ok')?.className || ''`);
    if (cls && !cls.includes(" on")) { await page.evaluate(`document.querySelector('[data-cap=cap-fire] .ck-ok')?.click()`); await sleep(900); }
    await tag(FIRE, "cap-fire");
    // the controls as croScan chose them, confirmed with 「준비할 안전조치 그대로 확인」 (the selection is not changed)
    const c2 = await page.evaluate(`document.querySelector('[data-cap=cap-fire] .ck-ctl-ok')?.className || ''`);
    if (c2 && !c2.includes(" on")) { await page.evaluate(`document.querySelector('[data-cap=cap-fire] .ck-ctl-ok')?.click()`); await sleep(900); }
    await tag(FIRE, "cap-fire");
    ev("fire_controls", await page.evaluate(`[...document.querySelectorAll('[data-cap=cap-fire] .ck-ctrl')].map(l => (l.querySelector('input').checked ? '[v] ' : '[ ] ') + l.innerText.replace(/\\s+/g, ' '))`));
    await tag(FIRE, "cap-fire"); await center("[data-cap=cap-fire]"); await sleep(800);
    ev("fire_after", await txt("[data-cap=cap-fire]"));
    ev("fire_after_html", (await page.evaluate(`document.querySelector('[data-cap=cap-fire]').outerHTML`)).slice(0, 5000));
    await shot(S("s18_fire_done"), fireRects());
  } else ev("fire_item", "(not found)");

  // V08: one AI candidate — what it says, the words it is based on, and the foreman adopting it
  const cand = await page.locator("#ck-list .ck-cand").count();
  ev("cand_count", cand);
  if (cand) {
    // prefer a candidate quoting the answer's own words (CO2 / 가우징 / 용접), else the first
    await tag(`(() => { const c = [...document.querySelectorAll('#ck-list .ck-cand')]; return c.find(e => /CO2|가우징|용접/.test(e.querySelector('.ck-reason')?.innerText || '')) || c[0]; })()`, "cap-cand");
    await center("[data-cap=cap-cand]"); await sleep(1000);
    const candId = await page.evaluate(`document.querySelector('[data-cap=cap-cand] [data-ckai-put]')?.dataset.ckaiPut || ''`);
    ev("cand_pick", { id: candId, text: await txt("[data-cap=cap-cand]") });
    await shot(S("s19_cand"), { cand: "[data-cap=cap-cand]", head: "[data-cap=cap-cand] .ck-head", why: "[data-cap=cap-cand] .ck-why", reason: "[data-cap=cap-cand] .ck-reason",
      put: "[data-cap=cap-cand] [data-ckai-put]", no: "[data-cap=cap-cand] [data-ckai-no]", chip: "[data-cap=cap-cand] .ai-chip", list: "#ck-list" });
    await page.evaluate(`document.querySelector('[data-cap=cap-cand] [data-ckai-put]')?.click()`); await sleep(1500);
    const NEW = `[...document.querySelectorAll('#ck-list .ck-item')].find(e => e.dataset.ckLi && e.dataset.ckLi.endsWith(${JSON.stringify("|" + candId)}))`;
    if (await tag(NEW, "cap-adopt")) {
      await center("[data-cap=cap-adopt]"); await sleep(1000);
      ev("adopted", await txt("[data-cap=cap-adopt]"));
      await shot(S("s20_adopted"), { item: "[data-cap=cap-adopt]", head: "[data-cap=cap-adopt] .ck-head", chip: "[data-cap=cap-adopt] .ai-chip", seg: "[data-cap=cap-adopt] .ck-seg",
        reason: "[data-cap=cap-adopt] .ck-reason", bar: "#ck-bar" });
    } else ev("adopted", "(not found after 채택)");
  } else if (await page.locator("#ck-list .ck-mark").count()) {
    // no candidate row: the AI's reading on a base item (「AI 제안」 line), and the foreman choosing the state with it in view
    // prefer an AI line quoting the foreman's own answer (작업 설명), else the first
    const MK = `(() => { const m = [...document.querySelectorAll('#ck-list .ck-mark')]; return (m.find(e => /반장 답/.test(e.innerText) && /가우징|용접|CO2/.test(e.innerText)) || m.find(e => /반장 답/.test(e.innerText)) || m[0])?.closest('.ck-item'); })()`;
    await tag(MK, "cap-cand"); await center("[data-cap=cap-cand]"); await sleep(1000);
    ev("cand_pick", { mark: true, text: await txt("[data-cap=cap-cand]") });
    await shot(S("s19_cand"), { cand: "[data-cap=cap-cand]", head: "[data-cap=cap-cand] .ck-head", reason: "[data-cap=cap-cand] .ck-mark", chip: "[data-cap=cap-cand] .ck-mark .ai-chip",
      seg: "[data-cap=cap-cand] .ck-seg", put: "[data-cap=cap-cand] .ck-ok", list: "#ck-list" });
    const okc = await page.evaluate(`document.querySelector('[data-cap=cap-cand] .ck-ok')?.className || ''`);
    if (okc && !okc.includes(" on")) { await page.evaluate(`document.querySelector('[data-cap=cap-cand] .ck-ok')?.click()`); await sleep(900); }
    await tag(MK, "cap-adopt"); await center("[data-cap=cap-adopt]"); await sleep(800);
    ev("adopted", await txt("[data-cap=cap-adopt]"));
    await shot(S("s20_adopted"), { item: "[data-cap=cap-adopt]", head: "[data-cap=cap-adopt] .ck-head", chip: "[data-cap=cap-adopt] .ck-mark .ai-chip", seg: "[data-cap=cap-adopt] .ck-seg",
      reason: "[data-cap=cap-adopt] .ck-mark", ok: "[data-cap=cap-adopt] .ck-ok", bar: "#ck-bar" });
  } else {
    ev("cand_none", await page.evaluate(`[...document.querySelectorAll('#ck-list .ck-cand-status')].map(e => e.innerText)`));
    if (await tag(`document.querySelector('#ck-list .ck-cand-status')`, "cap-cand")) { await center("[data-cap=cap-cand]"); await sleep(800); await shot(S("s19_cand"), { cand: "[data-cap=cap-cand]", list: "#ck-list" }); }
  }

  // V09: 「위험한 이유 보기」 — the reason, the facts used, the standard, and a linked accident case
  const openWhy = async (capId) => {
    await page.evaluate(`document.querySelector('[data-cap=${capId}] .x-why')?.click()`);
    for (let i = 0; i < 40; i++) { const t = await txt(`[data-cap=${capId}] .x-why-out`); if (t && !/정리하는 중/.test(t)) break; await sleep(500); }
    await sleep(600);
    return txt(`[data-cap=${capId}] .x-why-out`);
  };
  let whyCap = null;
  if (await tag(FIRE, "cap-fire")) {
    const w = await openWhy("cap-fire"); ev("why_fire", w);
    if (/사고 사례|사례집/.test(w)) whyCap = "cap-fire";
    else await page.evaluate(`document.querySelector('[data-cap=cap-fire] .x-why')?.click()`);   // closed again
  }
  if (!whyCap) {   // the first item whose reason links a case
    const n = await page.locator("#ck-list .ck-item").count();
    for (let i = 0; i < n && !whyCap; i++) {
      if (!(await tag(`[...document.querySelectorAll('#ck-list .ck-item')][${i}]`, "cap-whyi"))) continue;
      if (!(await page.locator("[data-cap=cap-whyi] .x-why").count())) continue;
      const w = await openWhy("cap-whyi");
      if (/사고 사례|사례집/.test(w)) { whyCap = "cap-whyi"; ev("why_case_item", { i, title: await txt("[data-cap=cap-whyi] .ck-title"), text: w }); }
      else await page.evaluate(`document.querySelector('[data-cap=cap-whyi] .x-why')?.click()`);
    }
  }
  if (whyCap) {
    await tag(`[...document.querySelectorAll('[data-cap=${whyCap}] .x-why-out li')].find(l => /사고 사례|사례집/.test(l.innerText))`, "cap-case");
    await tag(`[...document.querySelectorAll('[data-cap=${whyCap}] .x-why-out ul')][0]`, "cap-facts");
    await page.evaluate(`document.querySelector('[data-cap=${whyCap}] .x-why-out')?.scrollIntoView({ block: 'center' })`); await sleep(900);
    ev("why_html", (await page.evaluate(`document.querySelector('[data-cap=${whyCap}] .x-why-out').outerHTML`)).slice(0, 5000));
    await shot(S("s21_why"), { item: `[data-cap=${whyCap}]`, out: `[data-cap=${whyCap}] .x-why-out`, judge: `[data-cap=${whyCap}] .x-why-out .sf-why-judge`,
      facts: "[data-cap=cap-facts]", case: "[data-cap=cap-case]", btn: `[data-cap=${whyCap}] .x-why`, left: `[data-cap=${whyCap}] .x-why-out .sf-why-left` });
    ev("why_case_line", await txt("[data-cap=cap-case]"));
    await page.evaluate(`document.querySelector('[data-cap=${whyCap}] .x-why')?.click()`); await sleep(500);   // closed
  } else ev("why_case_line", "(no item with a case)");

  // V10: 관련 자료 — back on the review screen, a question's 「왜 묻나요?」 with the searched passages, source and review state
  const withRefs = whys.filter((w) => w.refs > 0);
  if (withRefs.length) {
    await page.evaluate(`document.querySelector('#stepper li[data-step="2"] button').click()`); await page.waitForSelector("#s-edit:not([hidden])"); await sleep(2000);
    await shot(S("s22_back"), { msgs: "#msgs", stepper: "#stepper", sheet: "#sheet" });
    const wi = withRefs[0].i;
    await tag(`[...document.querySelectorAll('#msgs .why-box')][${wi}]?.closest('.msg')`, "cap-wq");
    await page.evaluate(`(() => { const m = document.querySelector('[data-cap=cap-wq]'); const b = m.querySelector('.why-btn'); if (b.getAttribute('aria-expanded') !== 'true') b.click(); })()`); await sleep(800);
    await tag(`document.querySelector('[data-cap=cap-wq] .why-refs')`, "cap-refs");
    await tag(`document.querySelector('[data-cap=cap-wq] .why-refs li')`, "cap-ref1");
    await tag(`document.querySelector('[data-cap=cap-wq] .why-refs-h')`, "cap-refsh");
    await page.evaluate(`document.querySelector('[data-cap=cap-wq] .why-box')?.scrollIntoView({ block: 'center' })`); await sleep(900);
    ev("refs_question", await txt("[data-cap=cap-wq]"));
    ev("refs_html", (await page.evaluate(`document.querySelector('[data-cap=cap-wq] .why-box').outerHTML`)).slice(0, 5000));
    await shot(S("s23_refs"), { q: "[data-cap=cap-wq]", box: "[data-cap=cap-wq] .why-box", refs: "[data-cap=cap-refs]", ref1: "[data-cap=cap-ref1]", refsh: "[data-cap=cap-refsh]",
      grade: "[data-cap=cap-ref1] .why-grade", src: "[data-cap=cap-ref1] .why-ref", text: "[data-cap=cap-ref1] small", need: "[data-cap=cap-wq] .why-need", msgs: "#msgs" });
    await page.evaluate(`document.querySelector('[data-cap=cap-wq] .why-btn').click()`); await sleep(700);   // closed
    await shot(S("s24_refs_closed"), { q: "[data-cap=cap-wq]", msgs: "#msgs", stepper: "#stepper" });
    await page.evaluate(`document.querySelector('#stepper li[data-step="4"] button').click()`); await sleep(2500);
    if (await page.isVisible("#presub")) { ev("popup_again", await txt("#presub")); await page.waitForSelector("#ps-ok:not([disabled])"); await page.click("#ps-ok"); }
    await page.waitForSelector("#s-check:not([hidden])"); await sleep(3000);
    for (let i = 0; i < 90; i++) { const s = await page.evaluate(`st.ckAi ? st.ckAi.status : 'none'`); if (s !== "loading") break; await sleep(2000); }
    ev("check_bar_back", await txt("#ck-bar"));
  } else ev("refs_question", "(no question with 관련 자료)");

  if (mode === "P") { ev("probe_end", el()); return; }

  // V11: the rest confirmed with 「다음 미완료로 이동」 (shortened in the video), submit, the submission's own PDFs
  let steps = 0;
  for (; steps < 140; steps++) {
    const left = await page.evaluate("typeof ckPending === 'function' ? ckPending().length : 0");
    if (!left) break;
    if (steps === 3) await shot(S("s25_mid"), { bar: "#ck-bar", next: "#ck-bar [data-cknext]" });
    await page.evaluate(`document.querySelector('#ck-bar [data-cknext]')?.click()`); await sleep(450);
    await page.evaluate("document.activeElement && document.activeElement.click()"); await sleep(400);
  }
  ev("check_steps", steps);
  ev("check_bar_done", await txt("#ck-bar"));
  await page.locator("#ck-next").scrollIntoViewIfNeeded();
  await shot(S("s26_done"), { bar: "#ck-bar", next: "#ck-next" });
  await page.evaluate(`document.querySelector('#ck-next')?.click()`); await page.waitForSelector("#s-submit:not([hidden])"); await sleep(2500);
  ev("summary", await txt("#summary"));
  await shot(S("s27_submit"), { summary: "#summary", send: "#sendfinal" });
  await page.click("#sendfinal"); await sleep(2500);
  if (await page.isVisible("#presub")) { ev("submit_popup", await txt("#presub")); await page.click("#ps-ok"); }
  await page.waitForSelector("#sub-docs:not([hidden])", { timeout: 400000 }); await sleep(3000);
  await page.locator("#sub-docs").scrollIntoViewIfNeeded();
  ev("sent", await txt("#s-submit"));
  const sub = await page.evaluate(`st.submission`);
  ev("submission", sub);
  await shot(S("s28_sent"), { docs: "#sub-docs", list: "#doc-list", id: "#sub-id", toast: "#toast" });
  const pdfDir = path.join(outDir, "pdf"); fs.mkdirSync(pdfDir, { recursive: true });
  for (const k of ["permit", "plans", "checklist"]) {
    try { const r = await page.request.get(`${BASE}api/submissions/${encodeURIComponent(sub.id)}/${k}.pdf`); if (r.ok()) fs.writeFileSync(path.join(pdfDir, `${sub.id}_${k}.pdf`), await r.body()); else ev("pdf_status", { k, s: r.status() }); }
    catch (e) { ev("pdf_error", String(e)); }
  }
  ev("done", el());
}
