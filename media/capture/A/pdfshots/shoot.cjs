const { chromium } = require('C:/Users/seoco/OneDrive/Desktop/PRAI/node_modules/playwright-core');
(async () => {
 const b = await chromium.launch({ channel: 'msedge', headless: true });
 const p = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });
 const R = {};
 await p.goto("file:///C:/Users/seoco/OneDrive/Desktop/%EC%A1%B0%EC%84%A0%ED%86%A4%EA%B0%9C%EB%B0%9C/croScan_demo_videos/work19/A/pdfshots/PDF_p1.html"); await p.waitForTimeout(500);
 R["PDF_p1"] = await p.evaluate(() => { const r = document.querySelector('#pg').getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
 await p.screenshot({ path: "C:\\Users\\seoco\\OneDrive\\Desktop\\\uc870\uc120\ud1a4\uac1c\ubc1c\\croScan_demo_videos\\work19\\A\\pdfshots\\PDF_p1.shot.png" });
 await p.goto("file:///C:/Users/seoco/OneDrive/Desktop/%EC%A1%B0%EC%84%A0%ED%86%A4%EA%B0%9C%EB%B0%9C/croScan_demo_videos/work19/A/pdfshots/PDF_p2.html"); await p.waitForTimeout(500);
 R["PDF_p2"] = await p.evaluate(() => { const r = document.querySelector('#pg').getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
 await p.screenshot({ path: "C:\\Users\\seoco\\OneDrive\\Desktop\\\uc870\uc120\ud1a4\uac1c\ubc1c\\croScan_demo_videos\\work19\\A\\pdfshots\\PDF_p2.shot.png" });
 require('fs').writeFileSync("C:\\Users\\seoco\\OneDrive\\Desktop\\\uc870\uc120\ud1a4\uac1c\ubc1c\\croScan_demo_videos\\work19\\A\\pdfshots\\pages.json", JSON.stringify(R));
 await b.close();
})();
