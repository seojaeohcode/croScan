// V14B (21-clip conti): the 0735 foreman answers the manager's 담당별 확인 question 「작업 위치·시간과 인원 배치」 from the prepared
// demo material only (samples/시연_하루/permits.json answers_truth of 0735: T1 14:00~16:00 · L1 1BAY 14-16 칼럼 B21S 블록 상부 ·
// T6 러그 3개 절단·회수만, 3명이 2시간 · L3 4.5m · HT2 로프로 하부 적치함에 내림, 하부 통행 통제 · B3 하부에서 족장 해체 13:00~15:30 (삼녹)
// · HT1 가스절단 3개), confirms and submits again (0735 had an earlier submission). Nothing else is invented: a question the material
// does not answer gets 「모름」. Every typed line and every app answer is logged (log_F.json).
import fs from "node:fs";
import path from "node:path";

const BASE = "http://localhost:8776/";
const DAY = "C:/Users/seoco/OneDrive/Desktop/조선톤개발/croScan_github/samples/시연_하루";
export const SAY = "작업시간 14:00~16:00. 장소 1BAY 14-16 칼럼 B21S 블록 상부. 러그 3개 절단·회수만, 3명이 2시간.";
// later questions → the prepared answer (typed), matched on the question text
const LATER = [   // [question words, prepared answer, the button to choose first (the app asks for a button, then the typed words)]
  [/높이/, "4.5m", /^높이 입력$/],
  [/내리|내려|회수/, "로프로 하부 적치함에 내림, 하부 통행 통제", /^회수 방법 입력$/],
  [/방법|가스절단|절단/, "B21S 블록 러그 3개, 가스절단", /^가스절단$/],
  [/병행|다른 작업|같은 시간|아래|하부/, "하부에서 족장 해체 13:00~15:30 (삼녹)", /^있음$/],
];
const NEVER = /가스 안 씀/;

export async function foreman0735({ page, shot }, outDir) {
  const logFile = path.join(outDir, "log_F.json"), log = { typed_first: SAY, events: [] };
  const ev = (k, v) => { log.events.push({ k, v, at: new Date().toISOString() }); fs.writeFileSync(logFile, JSON.stringify(log, null, 1)); console.log(`  [F] ${k}:`, (typeof v === "string" ? v : JSON.stringify(v)).slice(0, 300)); };
  const sleep = (ms) => page.waitForTimeout(ms);
  const tag = (js, id) => page.evaluate(`(() => { document.querySelectorAll('[data-cap=${JSON.stringify(id)}]').forEach(x => x.removeAttribute('data-cap')); const e = (${js}); if (e) e.setAttribute('data-cap', ${JSON.stringify(id)}); return !!e; })()`);
  const txt = (sel) => page.innerText(sel).catch(() => "");
  const t0 = Date.now(), el = () => `${Math.round((Date.now() - t0) / 1000)}s`;
  page.setDefaultTimeout(300000);
  const subs0 = await page.request.get(`${BASE}api/safety/submissions`).then((r) => r.json()).catch(() => ({}));
  ev("submission_0735_before", subs0["AC00-IH-20261029-0735"] || null);

  await page.goto(BASE); await page.waitForSelector("#s-login:not([hidden])");
  if (await page.locator('[data-login="foreman"]').count()) await page.click('[data-login="foreman"]');
  await sleep(500);
  await shot("F_login", { roles: "#login-roles", go: ".login-go", foreman: '[data-login="foreman"]' });
  await page.click(".login-go"); await page.waitForSelector("#s-plans:not([hidden])"); await sleep(1200);
  // the plan of the work below 0735 (삼녹 족장 해체), as the foreman's own day material
  await page.setInputFiles("#wpfile", [`${DAY}/작업계획서/WP-1029-04_삼녹.pdf`]); await sleep(1500);
  await page.click("#wp-start");
  for (let i = 0; i < 100 && (await page.locator("button.plan-check").count()) < 1; i++) await sleep(3000);
  await sleep(3000);
  ev("plans_list", await txt("#plan-list"));
  for (let r = 0; r < 3; r++) {
    for (let i = 0; i < (await page.locator("button.plan-check").count()); i++) {
      const bt = page.locator("button.plan-check").nth(i);
      if ((await bt.getAttribute("aria-pressed")) !== "true") { await bt.click(); await sleep(1000); }
    }
    if (await page.isEnabled("#go-submit")) break;
  }
  await page.click("button:has-text('다음: 허가서 올리기')"); await page.waitForSelector("#s-upload:not([hidden])"); await sleep(1200);
  await page.click("#kinds button:has-text('고소')");
  await page.setInputFiles("#file", `${DAY}/허가서/0735_고소_A.pdf`); await sleep(1200);
  await tag(`[...document.querySelectorAll('#kinds button')].find(b => b.innerText.includes('고소'))`, "cap-kind");
  await shot("F_upload", { kinds: "#kinds", kind: "[data-cap=cap-kind]", drop: "#drop", start: "#start" });
  await page.click("#start");
  await page.waitForSelector("#s-edit:not([hidden]) #msgs .msg", { timeout: 400000 }); await sleep(9000);
  ev("t_review", el());
  ev("fields", await page.evaluate(`[...document.querySelectorAll('#sheet .fi[data-key]')].map(e => e.dataset.key + '=' + e.innerText.replace(/\\s+/g, ' ').slice(0, 40))`));
  await tag(`[...document.querySelectorAll('#msgs .msg.ai')].pop()`, "cap-q");
  ev("first_question", await txt("[data-cap=cap-q]"));
  await shot("F_review", { sheet: "#sheet", msgs: "#msgs", question: "[data-cap=cap-q]", location: '#sheet .fi[data-key="p1.location"]',
    time: ['#sheet .fi[data-key="p1.date_1"]', '#sheet .fi[data-key="p1.from_1"]', '#sheet .fi[data-key="p1.to_1"]'], composer: "#composer" });

  // wait for the reading card of the last typed answer, log it, confirm it (the foreman's 「확인」)
  let cards = 0;
  const readCard = async (name) => {
    const sent = Date.now();
    for (let i = 0; i < 150 && (await page.locator(".ai-card").count()) <= cards; i++) await sleep(2000);
    let t = "";
    for (let i = 0; i < 150; i++) {
      t = await page.locator(".ai-card").last().innerText().catch(() => "");
      if (/확인 \(\d+건\)|AI 결과를 준비하지 못함|확인한 우리 작업 정보/.test(t) && !/답 해석 중|결과 검사 중|대기 중/.test(t)) break;
      await sleep(2000);
    }
    cards = await page.locator(".ai-card").count();
    ev(`${name}_wait_s`, Math.round((Date.now() - sent) / 1000));
    await sleep(1500);
    await tag(`[...document.querySelectorAll('.ai-card')].pop()`, "cap-card");
    await page.evaluate(`document.querySelector('[data-cap=cap-card]')?.scrollIntoView({ block: 'center' })`); await sleep(700);
    ev(`${name}_card`, await txt("[data-cap=cap-card]"));
    const rows = `[...document.querySelectorAll('[data-cap=cap-card] .spill-list li')]`;
    await tag(`${rows}.find(l => /작업시간/.test(l.innerText))`, "cap-ctime");
    await tag(`${rows}.find(l => /작업장소|위치/.test(l.innerText))`, "cap-cloc");
    await tag(`${rows}.find(l => /인원/.test(l.innerText))`, "cap-cppl");
    return t;
  };
  // a reading the prepared material does not say is taken out before confirming (「이것 빼기」): on the first card everything but time and
  // place (the manager asked for those), and anywhere a cutting method other than gas cutting (the material says 가스절단)
  const BAD = /그라인더|기계절단|플라즈마/;
  const prune = async (keepOnly) => {
    const rows = await page.evaluate(`[...document.querySelectorAll("[data-cap=cap-card] .spill-list li")].map(l => ({ t: l.innerText.split("\\n")[0], tog: l.querySelector("[data-rd-tog]")?.dataset.rdTog || null, all: l.innerText }))`);
    const out = [];
    for (const r of rows) {
      const drop = (keepOnly && !keepOnly.test(r.t)) || BAD.test(r.all);
      if (drop && r.tog) { await page.evaluate(`document.querySelector('[data-cap=cap-card] [data-rd-tog="${r.tog}"]')?.click()`); await sleep(500); }
      out.push({ row: r.t, dropped: !!(drop && r.tog) });
    }
    return out;
  };
  const confirmCard = async () => {
    const ok = page.locator("[data-cap=cap-card] [data-rd-ok]").first();
    if ((await ok.count()) && (await ok.isEnabled())) { await ok.click(); await sleep(5000); return true; }
    return false;
  };

  // the manager's question, answered from the prepared material in one typed line
  await page.fill("#input", SAY); await sleep(600);
  await shot("F_typed", { composer: "#composer", input: "#input", question: "[data-cap=cap-q]", msgs: "#msgs" });
  await page.click("#send");
  await readCard("first");
  const CARD = { card: "[data-cap=cap-card]", time: "[data-cap=cap-ctime]", loc: "[data-cap=cap-cloc]", ppl: "[data-cap=cap-cppl]", ok: "[data-cap=cap-card] [data-rd-ok]",
    rows: "[data-cap=cap-card] .spill-list", head: "[data-cap=cap-card] .spill-h", msgs: "#msgs", sheet: "#sheet" };
  ev("first_pruned", await prune(/작업시간|작업장소|위치/));
  await tag(`[...document.querySelectorAll('.ai-card')].pop()`, "cap-card");
  await shot("F_card", CARD);
  ev("first_confirmed", await confirmCard());
  ev("first_card_after", await txt("[data-cap=cap-card]"));
  ev("fields_after", await page.evaluate(`[...document.querySelectorAll('#sheet .fi[data-key]')].map(e => e.dataset.key + '=' + e.innerText.replace(/\\s+/g, ' ').slice(0, 60) + (e.classList.contains('answered') ? ' (answered)' : '')).filter(s => /answered/.test(s))`));
  await shot("F_applied", { sheet: "#sheet", answered: "#sheet .fi.answered", msgs: "#msgs", card: "[data-cap=cap-card]", location: '#sheet .fi[data-key="p1.location"]',
    time: ['#sheet .fi[data-key="p1.date_1"]', '#sheet .fi[data-key="p1.from_1"]', '#sheet .fi[data-key="p1.to_1"]'] });

  // the remaining questions: the prepared answer when the material has one, else 「모름」 / 「없음 · 검토 마치기」
  const done = [];
  let lastQ = "";
  // the newest message that still has live answer buttons is the open question
  const LIVE = `[...document.querySelectorAll('#msgs .choices')].filter(c => c.getAttribute('aria-disabled') !== 'true' && c.offsetParent && c.querySelector('button'))[0]`;
  const QOF = `(() => { const box = ${LIVE}; if (!box) return ''; const qs = [...document.querySelectorAll('#msgs .msg.ai')].filter(m => box.compareDocumentPosition(m) & Node.DOCUMENT_POSITION_PRECEDING); const m = qs.pop(); return (m ? m.innerText : '') + ' #' + [...document.querySelectorAll('#msgs .choices')].indexOf(box); })()`;
  let idle = 0;
  for (let i = 0; i < 40 && !(await page.isVisible("#go-plans")); i++) {
    let q = await page.evaluate(QOF);
    if (!q) {                                          // a question without buttons: answered in the box (prepared answer, else 「모름」)
      const lastAi = await page.evaluate(`(() => { const m = [...document.querySelectorAll('#msgs .msg')].pop(); return m && m.classList.contains('ai') ? m.innerText : ''; })()`);
      if (lastAi && /\?/.test(lastAi) && lastAi !== lastQ && (await page.isEnabled("#input").catch(() => false))) {
        const h2 = LATER.find(([re]) => re.test(lastAi));
        const say = h2 ? h2[1] : "모름";
        lastQ = lastAi;
        await page.fill("#input", say); await sleep(400); await page.click("#send");
        let pr = null, c = null;
        if (h2 && h2[2]) { await readCard(`free${i}`); pr = await prune(null); c = await confirmCard(); } else await sleep(6000);
        done.push({ q: lastAi.slice(0, 200), buttons: [], typed: say, pruned: pr, confirmed: c });
        ev("later_answer", done[done.length - 1]);
        idle = 0; continue;
      }
    }
    if (!q || q === lastQ) { if (++idle > 30) { ev("stuck", await page.evaluate(`[...document.querySelectorAll('#msgs .msg')].slice(-3).map(m => m.innerText).join(' || ')`)); break; } await sleep(3000); continue; }
    idle = 0;
    const btns = await page.evaluate(`(() => { const m = ${LIVE}; return m ? [...m.querySelectorAll('button')].filter(b => b.offsetParent && !b.disabled && !(b.className || '').includes('picked')).map(b => b.innerText.trim()) : []; })()`);
    const qs = q.split("\n").filter((l) => !/^(관측|왜 묻나요|허가서에서)/.test(l));
    const head = (qs.find((l) => /함께 여쭙니다/.test(l)) || qs.find((l) => /\?|요\.?$/.test(l)) || qs[0] || "").trim();
    const hit = LATER.find(([re, , br]) => btns.some((t) => br.test(t)) && re.test(qs.join(" ")));
    if (hit) {
      lastQ = q;
      await page.fill("#input", hit[1]); await sleep(400);
      const bt = btns.find((t) => hit[2].test(t));
      await page.evaluate(`(() => { const m = ${LIVE}; [...m.querySelectorAll('button')].find(b => b.innerText.trim() === ${JSON.stringify(bt)} && !b.disabled)?.click(); })()`); await sleep(1500);
      if ((await page.inputValue("#input").catch(() => "")).trim() && (await page.isEnabled("#send").catch(() => false))) await page.click("#send");
      await sleep(5000);
      // an answer the AI reads comes back as a card to confirm: wait for it, take out what the material does not say, confirm
      let pr = null, c = null;
      for (let k = 0; k < 45; k++) { const t = await page.locator(".ai-card").last().innerText().catch(() => ""); if (!/답 해석 중|결과 검사 중|대기 중/.test(t)) break; await sleep(2000); }
      if (await page.locator(".ai-card [data-rd-ok]:not([disabled])").count()) {
        await tag(`[...document.querySelectorAll('.ai-card')].filter(c => c.querySelector('[data-rd-ok]:not([disabled])')).pop()`, "cap-card");
        ev(`later${i}_card`, await txt("[data-cap=cap-card]"));
        pr = await prune(null); c = await confirmCard();
      }
      done.push({ q: head.slice(0, 160), buttons: btns, chose: bt, typed: hit[1], pruned: pr, confirmed: c });
      ev("later_answer", done[done.length - 1]);
      continue;
    }
    const pick = ["모름", "없음 · 검토 마치기"].find((t) => btns.includes(t));
    if (pick && !NEVER.test(pick)) {
      lastQ = q;
      await page.evaluate(`(() => { const m = ${LIVE}; [...m.querySelectorAll('button')].filter(b => b.innerText.trim() === ${JSON.stringify(pick)} && !b.disabled).pop()?.click(); })()`);
      done.push({ q: head.slice(0, 160), full: q.slice(0, 300), buttons: btns, clicked: pick });
      ev("later_answer", done[done.length - 1]);
      await sleep(5000);
      continue;
    }
    await sleep(4000);
  }
  ev("remaining", done);
  await shot("F_done", { sheet: "#sheet", msgs: "#msgs", next: "#go-plans" });

  await page.click("#go-plans"); await sleep(3000);
  if (await page.isVisible("#presub")) {
    await page.waitForSelector("#ps-ok:not([disabled])", { timeout: 200000 }); await sleep(1500);
    ev("popup", await txt("#presub"));
    await shot("F_popup", { dialog: "#presub .dialog", body: "#ps-body", ok: "#ps-ok" });
    await page.click("#ps-ok");
  } else ev("popup", "(no window)");
  await page.waitForSelector("#s-check:not([hidden])"); await sleep(4000);
  for (let i = 0; i < 90; i++) { const s = await page.evaluate(`st.ckAi ? st.ckAi.status : 'none'`); if (s !== "loading") break; await sleep(2000); }
  ev("check_bar", await txt("#ck-bar"));
  let steps = 0;
  for (; steps < 160; steps++) {
    const left = await page.evaluate("typeof ckPending === 'function' ? ckPending().length : 0");
    if (!left) break;
    await page.evaluate(`document.querySelector('#ck-bar [data-cknext]')?.click()`); await sleep(450);
    await page.evaluate("document.activeElement && document.activeElement.click()"); await sleep(400);
  }
  ev("check_steps", steps);
  ev("check_bar_done", await txt("#ck-bar"));
  await page.evaluate(`document.querySelector('#ck-next')?.click()`); await page.waitForSelector("#s-submit:not([hidden])"); await sleep(2500);
  ev("summary", await txt("#summary"));
  await shot("F_submit", { summary: "#summary", send: "#sendfinal" });
  await page.click("#sendfinal"); await sleep(2500);
  if (await page.isVisible("#presub")) { ev("submit_popup", await txt("#presub")); await page.click("#ps-ok"); }
  await page.waitForSelector("#sub-docs:not([hidden])", { timeout: 400000 }); await sleep(3000);
  await page.locator("#sub-docs").scrollIntoViewIfNeeded();
  ev("sent", await txt("#s-submit"));
  const sub = await page.evaluate(`st.submission`);
  ev("submission", sub);
  await tag(`document.querySelector('#s-submit .ok, #s-submit .done, #s-submit h2, #s-submit h3')`, "cap-subhead");
  await shot("F_sent", { docs: "#sub-docs", list: "#doc-list", id: "#sub-id", toast: "#toast", head: "[data-cap=cap-subhead]" });
  const subs1 = await page.request.get(`${BASE}api/safety/submissions`).then((r) => r.json()).catch(() => ({}));
  ev("submission_0735_after", subs1["AC00-IH-20261029-0735"] || null);
  ev("done", el());
}
