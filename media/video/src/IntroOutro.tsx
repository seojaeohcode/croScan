// 인트로(28박)·엔딩(20박): 배경음악 136 BPM 박자표(Codex 설계)에 맞춘 모션그래픽.
// 모티프: 두 작업의 시간 막대가 겹치고 → 스캔선이 지나가고 → 방패(로고)로 모인다.
import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { C, FONT, FULL, HEAD, Screen } from "./lib";
import { Beam, FPB, Grad, Outline, Ribbons, Ripples, Sphere, Typing, White, Word, beat, clamp, ease, hit, stepped, tw } from "./motion";

const T0 = 8 * 60, T1 = 13 * 60;                                // the time axis of the bars: 08:00–13:00 (wide enough to read)
const X0 = 300, X1 = 1620;
const tx = (m: number) => X0 + ((m - T0) / (T1 - T0)) * (X1 - X0);
// the demo's 1순위 pair (P01): 밀폐 inside the tank 10:00–11:30 × the plan's welding above it 09:00–12:00 → overlap 10:00–11:30
const BARS = [{ label: "밀폐 · 탱크 내부 검사", a: 600, b: 690, y: 520, c: "#FFFFFF", ink: C.navy }, { label: "계획 · 갑판 보강재 용접", a: 540, b: 720, y: 640, c: "#BFD2FF", ink: C.navy }];

// a document card (the permit), with a folded corner
const Card: React.FC<{ x: number; y: number; w?: number; s?: number; o?: number; rot?: number; tag?: string }> = ({ x, y, w = 300, s = 1, o = 1, rot = 0, tag = "허가서" }) => (
  <div style={{ position: "absolute", left: x, top: y, width: w, height: w * 1.3, transform: `translate(-50%,-50%) scale(${s}) rotate(${rot}deg)`, opacity: o, borderRadius: 16,
    background: "linear-gradient(160deg, #FFFFFF 0%, #EEF3FC 100%)", boxShadow: "0 24px 50px rgba(0,20,60,.30)", padding: 26, overflow: "hidden" }}>
    <div style={{ position: "absolute", right: 0, top: 0, width: 54, height: 54, background: "linear-gradient(225deg, #C9D6F2 50%, transparent 50%)" }} />
    <div style={{ display: "inline-block", padding: "5px 14px", borderRadius: 8, background: C.navy, color: "#fff", font: `700 22px ${FONT}` }}>{tag}</div>
    {[0, 1, 2, 3, 4, 5].map((j) => <div key={j} style={{ height: 14, borderRadius: 7, background: "#D3DBE6", marginTop: 22, width: `${92 - (j * 19) % 40}%` }} />)}
  </div>
);

// the two bars on a time axis; `fold` (0→1) gathers them into the middle as cards
const Bars: React.FC<{ a: number; mark: number; fold?: number; dark?: boolean }> = ({ a, mark, fold = 0, dark = true }) => {
  const f = useCurrentFrame();
  const m = tw(f, mark, 8, ease.back);
  const ov = { x: tx(600), w: tx(690) - tx(600) };
  return (
    <div style={{ position: "absolute", inset: 0, opacity: 1 - fold, transform: `scale(${1 - 0.5 * fold})`, transformOrigin: "960px 600px" }}>
      {/* the axis */}
      <div style={{ position: "absolute", left: X0, right: 1920 - X1, top: 760, height: 2, background: dark ? "rgba(255,255,255,.5)" : "#A9B6C8", opacity: tw(f, a, 8) }} />
      {[8, 9, 10, 11, 12, 13].map((h) => <div key={h} style={{ position: "absolute", left: tx(h * 60) - 40, width: 80, top: 772, textAlign: "center", font: `600 26px ${FONT}`,
        color: dark ? "rgba(255,255,255,.8)" : C.ink2, opacity: tw(f, a, 8) }}>{`${String(h).padStart(2, "0")}:00`}</div>)}
      {BARS.map((B, i) => {
        const t = tw(f, a + i * beat(1), 10, ease.back);
        return <div key={i} style={{ position: "absolute", left: tx(B.a), top: B.y, width: (tx(B.b) - tx(B.a)) * t, height: 84, borderRadius: 18, background: B.c, overflow: "hidden",
          boxShadow: "0 14px 34px rgba(0,20,60,.28), inset 0 -5px 12px rgba(16,56,192,.16)", display: "flex", alignItems: "center", padding: "0 26px",
          color: B.ink, font: `800 30px ${FONT}`, whiteSpace: "nowrap" }}>{B.label}</div>;
      })}
      {/* the overlap: one thin red frame, '검토 필요' (not a verdict) */}
      <div style={{ position: "absolute", left: ov.x - 8, top: 500, width: ov.w + 16, height: 244, borderRadius: 22, border: `5px solid #FF6B5E`, background: "rgba(255,107,94,.14)",
        opacity: m, transform: `scale(${0.9 + 0.1 * m})` }} />
      <div style={{ position: "absolute", left: ov.x + ov.w / 2, top: 452, transform: `translate(-50%,0) scale(${m})`, padding: "6px 18px", borderRadius: 999, background: "#FF6B5E",
        color: "#fff", font: `800 28px ${FONT}`, whiteSpace: "nowrap" }}>겹침 10:00–11:30 · 검토 필요</div>
    </div>
  );
};

export const INTRO_BEATS = 28;
export const Intro: React.FC = () => {
  const f = useCurrentFrame(), b = (n: number) => beat(n);
  // b3→b4: a card grows and turns into the blue screen
  const grow = tw(f, b(3) - 3, b(1), ease.inout);
  const blue = f >= b(4) - 3;
  const toWhite = f >= b(20);
  return (
    <AbsoluteFill style={{ fontFamily: FONT, overflow: "hidden" }}>
      {/* b0–3 흰 배경: 위험작업 허가서| */}
      <White>
        <Outline text="PERMIT TO WORK · PERMIT TO WORK" x={200 - stepped(f, 60)} y={150} size={260} />
        <Outline text="HOT · CONFINED · HEIGHT · LIFTING · LOTO" x={-400 + stepped(f, 44)} y={640} size={200} color="rgba(0,48,135,.10)" />
        <div style={{ position: "absolute", left: 0, right: 0, top: 470, textAlign: "center", font: `800 128px/1 ${FONT}`, color: C.navy, letterSpacing: "-3px",
          transform: `scale(${1 + 0.05 * (f < b(2) ? hit(f) : 0)})` }}>
          <span>위험작업</span><span style={{ opacity: f >= b(1) ? 1 : 0, display: "inline-block", marginLeft: 28,
            transform: `translateY(${(1 - tw(f, b(1), 5, ease.back)) * 30}px)` }}>허가서</span></div>
      </White>
      {/* the card that becomes the screen */}
      {!blue && grow > 0 && <div style={{ position: "absolute", left: 960 - (150 + 900 * grow), top: 540 - (195 + 400 * grow), width: 300 + 1800 * grow, height: 390 + 800 * grow,
        borderRadius: 16 * (1 - grow), background: `linear-gradient(135deg, ${C.navy}, ${C.blue})`, opacity: Math.min(1, grow * 3), boxShadow: "0 30px 80px rgba(0,20,60,.35)" }} />}
      {blue && !toWhite && <Grad>
        {/* soft glossy shapes far behind */}
        <Sphere x={1640} y={250 - 18 * hit(f)} r={130} o={0.55} /><Sphere x={260} y={880 - 14 * hit(f + FPB / 2)} r={90} o={0.45} c1="#BFD2FF" />
        {/* b4–7 하루 50건 + three kinds */}
        {f < b(8) && <>
          <div style={{ position: "absolute", inset: 0, transform: `scale(${1 + 0.07 * (f >= b(5) && f < b(6) ? hit(f) : 0)})` }}>
            <Word a={b(4)} size={190} y={360}>하루 {Math.round(interpolate(f, [b(4), b(5)], [0, 50], { ...clamp, easing: ease.out3 }))}건</Word></div>
          <div style={{ position: "absolute", left: 0, right: 0, top: 930, textAlign: "center", font: `600 30px ${FONT}`, color: "rgba(255,255,255,.85)", opacity: tw(f, b(5)) }}>
            위험작업 허가서 10 · 작업계획서 40 (시연 자료 기준)</div>
          {[["화기", 560], ["밀폐", 960], ["중량물인양", 1360]].map(([l, x], i) => {
            const t = tw(f, b(6) - 5 + i, 7, ease.back);
            return <div key={l as string} style={{ position: "absolute", left: x as number, top: 700 + (1 - t) * 160, transform: "translate(-50%,-50%)", opacity: t }}>
              <div style={{ padding: "18px 40px", borderRadius: 999, background: "linear-gradient(180deg,#fff,#DCE6FA)", color: C.navy, font: `800 40px ${FONT}`,
                boxShadow: "0 18px 40px rgba(0,20,60,.3), inset 0 -6px 14px rgba(16,56,192,.18)" }}>{l}</div></div>;
          })}
        </>}
        {/* b8–15 겹치는 작업은? the two bars, the overlap marked on b10; b14–15 they fold into the middle */}
        {f >= b(8) && f < b(16) && <>
          <Word a={b(8)} z={b(14)} size={110} y={250}>겹치는 작업은?</Word>
          <Bars a={b(8)} mark={b(10)} fold={tw(f, b(14), b(2), ease.inout)} />
        </>}
        {/* b16–19 the cards and the scan line; 위험작업 AI 사전검토 */}
        {f >= b(14) && <>
          {[[-60, -8], [0, 0], [60, 8]].map(([dx, r], i) => <Card key={i} x={960 + dx} y={620} w={260} rot={r} s={0.6 + 0.4 * tw(f, b(14) + i * 3, 12, ease.back)} o={tw(f, b(14) + i * 3, 8)}
            tag={["허가서", "계획서", "허가서"][i]} />)}
          <Beam a={b(16)} n={b(2)} top={420} bottom={830} />
          <Ripples x={960} y={620} a={b(18)} n={2} />
          <Word a={b(16)} size={96} y={250}>위험작업 AI 사전검토</Word>
        </>}
      </Grad>}
      {/* b20–23 white: the two bands wrap the logo, the line under it stays */}
      {toWhite && <White>
        <div style={{ position: "absolute", inset: 0, transformOrigin: "960px 470px", opacity: 1 - tw(f, b(26), b(1)),
          transform: `translateY(${-300 * tw(f, b(24), b(2), ease.inout)}px) scale(${1 - 0.45 * tw(f, b(24), b(2), ease.inout)})` }}>
          <Rings a={b(20)} />
          <Img src={staticFile("croscan_logo_real.png")} style={{ position: "absolute", left: 960 - 440, top: 380, width: 880,
            transform: `scale(${0.8 + 0.2 * tw(f, b(20) + 2, 8, ease.back)})`, opacity: tw(f, b(20) + 2, 4) }} />
          <div style={{ position: "absolute", left: 0, right: 0, top: 660, textAlign: "center", font: `700 56px ${FONT}`, color: C.ink, letterSpacing: "-1px",
            opacity: tw(f, b(21) - 4, 6), transform: `translateY(${(1 - tw(f, b(21) - 4, 6, ease.back)) * 20}px)` }}>위험작업 AI 사전검토</div>
        </div>
        {f >= b(24) && <div style={{ position: "absolute", inset: 0, transformOrigin: "960px 1080px",
          transform: `translateY(${160 * (1 - tw(f, b(24), b(4), ease.inout))}px) scale(${0.3 + 0.7 * tw(f, b(24), b(4), ease.inout)})`, opacity: tw(f, b(24), 6) }}>
          <Screen win={FULL} layers={[{ src: "shots/s3_form.png" }]} /></div>}
      </White>}
      {/* the white comes in as a circle from the middle on b20 */}
      {f >= b(20) - 8 && f < b(20) && <AbsoluteFill style={{ clipPath: `circle(${tw(f, b(20) - 8, 8, ease.inout) * 1200}px at 960px 620px)`, background: "#F7F9FC" }} />}
    </AbsoluteFill>
  );
};
// the two work bands as rings that come around the logo and settle (blue and a thin red, the overlap)
const Rings: React.FC<{ a: number }> = ({ a }) => {
  const f = useCurrentFrame(), t = tw(f, a, 24, ease.inout);
  return (
    <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0 }}>
      <g transform={`translate(960 470) rotate(${-120 + 120 * t})`} opacity={0.9}>
        <ellipse rx={560} ry={150} fill="none" stroke={C.blue} strokeWidth={10} strokeDasharray={`${3600 * t} 4000`} opacity={0.35} />
      </g>
      <g transform={`translate(960 470) rotate(${150 - 150 * t})`}>
        <ellipse rx={600} ry={175} fill="none" stroke="#FF6B5E" strokeWidth={5} strokeDasharray={`${3800 * t} 4200`} opacity={0.35} />
      </g>
    </svg>
  );
};

export const OUTRO_BEATS = 20;
export const Outro: React.FC = () => {
  const f = useCurrentFrame(), b = (n: number) => beat(n);
  const card = tw(f, b(8) - 5, 7, ease.back);
  return (
    <AbsoluteFill style={{ fontFamily: FONT, overflow: "hidden" }}>
      <Grad a="#0A2A7A" b="#2D57D8" angle={160}>
        <Ribbons o={0.6} />
        <Sphere x={1700} y={180 - 16 * hit(f)} r={110} o={0.6} /><Sphere x={200} y={900 - 20 * hit(f + FPB / 2)} r={150} o={0.5} c1="#BFD2FF" /><Sphere x={1500} y={930 - 12 * hit(f)} r={60} o={0.7} />
        <Word a={b(0)} z={b(4)} size={110} y={250}>서류를 읽고</Word>
        {f < b(4) + 4 && <div style={{ position: "absolute", inset: 0, opacity: 1 - tw(f, b(4) - 2, 6) }}>
          {[[-200, -8], [0, 0], [200, 8]].map(([dx, r], i) => <Card key={i} x={960 + dx} y={650} w={280} rot={r} s={0.7 + 0.3 * tw(f, b(1) - 6 + i * 2, 7, ease.back)} o={tw(f, b(1) - 6 + i * 2, 4)}
            tag={["허가서", "작업계획서", "허가서"][i]} />)}
          <Beam a={b(1)} n={b(2)} top={430} bottom={880} />
        </div>}
        <Word a={b(4)} z={b(8)} size={110} y={250}>겹치는 위험을 살피고</Word>
        {f >= b(4) && f < b(8) && <Bars a={b(4)} mark={b(6)} />}
        <Word a={b(8)} z={b(12)} size={110} y={250}>현장 게시 서류까지</Word>
        {f >= b(8) && f < b(12) + 8 && <div style={{ position: "absolute", left: 960, top: 640, transform: `translate(-50%,-50%) scale(${0.6 + 0.4 * card})`, opacity: card }}>
          <div style={{ width: 820, padding: "40px 48px", borderRadius: 26, background: "linear-gradient(160deg,#fff,#EEF3FC)", boxShadow: "0 30px 70px rgba(0,20,60,.35)" }}>
            <div style={{ font: `800 50px ${FONT}`, color: C.navy, display: "inline-block", transform: `scale(${1 + 0.06 * (f >= b(10) && f < b(11) ? hit(f) : 0)})`, transformOrigin: "left center" }}>
              병행작업 조정 · <span style={{ position: "relative" }}>착수조건<i style={{ position: "absolute", left: 0, bottom: -6, height: 8, borderRadius: 4, background: "#FF6B5E",
                width: `${100 * tw(f, b(10) - 3, 5, ease.out3)}%` }} /></span></div>
            <div style={{ font: `600 32px ${FONT}`, color: C.ink2, marginTop: 10 }}>현장 게시용 별지 · 양쪽 반장 확인</div>
            {[0, 1, 2].map((j) => <div key={j} style={{ height: 18, borderRadius: 9, background: "#D3DBE6", marginTop: 26, width: `${90 - j * 18}%` }} />)}
          </div></div>}
      </Grad>
      {/* b12: the card's white fills the screen; the logo and the last line, credits at the bottom */}
      {f >= b(12) - 7 && <AbsoluteFill style={{ clipPath: `circle(${tw(f, b(12) - 7, 7, ease.inout) * 2300}px at 960px 640px)` }}>
        <White>
          <Img src={staticFile("croscan_logo_real.png")} style={{ position: "absolute", left: 960 - 420, top: 360, width: 840,
            transform: `scale(${0.9 + 0.1 * tw(f, b(12) - 2, 7, ease.back)})`, opacity: f >= b(12) - 2 ? 1 : 0 }} />
          <div style={{ position: "absolute", left: 0, right: 0, top: 640, textAlign: "center", font: `700 58px ${FONT}`, color: C.ink, letterSpacing: "-1px",
            opacity: tw(f, b(13) - 4, 5), transform: `translateY(${(1 - tw(f, b(13) - 4, 6, ease.back)) * 20}px)` }}>작업 전 위험 검토, croScan</div>
          <div style={{ position: "absolute", left: 0, right: 0, bottom: 44, textAlign: "center", font: `500 24px ${FONT}`, color: C.ink2, lineHeight: 1.6, opacity: tw(f, b(14) - 3, 5) }}>
            음악: “Getting it Done” Kevin MacLeod (incompetech.com) · Licensed under Creative Commons: By Attribution 4.0<br />
            음성: Microsoft Edge 신경망 음성(edge-tts) · 화면: croScan 시연 자료</div>
        </White>
      </AbsoluteFill>}
    </AbsoluteFill>
  );
};
export { HEAD };
