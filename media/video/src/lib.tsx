// Shared pieces: fonts, the framed app screen with a camera that zooms to boxes, highlight boxes, clicks, captions.
import React from "react";
import { AbsoluteFill, Easing, Img, continueRender, delayRender, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { FPB, snapBeat } from "./beat";

export const C = { navy: "#003087", navy9: "#002554", blue: "#1038C0", blue50: "#EEF3FC", ground: "#F0F4F8", ink: "#0F1B2D", ink2: "#3D4B60",
  p1: "#B42318", ask: "#C86A00", ok: "#00752E", line: "#D3DBE6" };
export const FONT = '"Pretendard", "Malgun Gothic", sans-serif', HEAD = '"HDHyundai", "Pretendard", sans-serif';

const faces = [["HDHyundai", 500, "HDHyundai-Medium"], ["HDHyundai", 700, "HDHyundai-Bold"], ["Pretendard", 400, "Pretendard-Regular"],
  ["Pretendard", 500, "Pretendard-Medium"], ["Pretendard", 700, "Pretendard-Bold"], ["Pretendard", 800, "Pretendard-ExtraBold"]] as const;
let fontsAsked = false;
export function useFonts() {
  if (fontsAsked) return;
  fontsAsked = true;
  const h = delayRender("fonts");
  Promise.all(faces.map(([fam, w, f]) => new FontFace(fam, `url(${staticFile(`fonts/${f}.woff2`)}) format("woff2")`, { weight: String(w) }).load()
    .then((ff) => (document as any).fonts.add(ff)))).then(() => continueRender(h), () => continueRender(h));
}

export type Box = { x: number; y: number; w: number; h: number };
export const FULL: Box = { x: 0, y: 0, w: 1920, h: 1080 };
export const pad = (b: Box, p: number): Box => ({ x: b.x - p, y: b.y - p, w: b.w + 2 * p, h: b.h + 2 * p });
export const union = (...bs: Box[]): Box => { const x = Math.min(...bs.map((b) => b.x)), y = Math.min(...bs.map((b) => b.y));
  return { x, y, w: Math.max(...bs.map((b) => b.x + b.w)) - x, h: Math.max(...bs.map((b) => b.y + b.h)) - y }; };
// the window grown to the frame's 16:9 and kept on the screenshot
function fit(b: Box): Box {
  let w = Math.max(b.w, b.h * 16 / 9), h = w * 9 / 16;
  w = Math.min(w, 1920); h = Math.min(h, 1080);
  let x = b.x + b.w / 2 - w / 2, y = b.y + b.h / 2 - h / 2;
  x = Math.max(0, Math.min(1920 - w, x)); y = Math.max(0, Math.min(1080 - h, y));
  return { x, y, w, h };
}
export const FRAME = { x: 96, y: 54, w: 1728, h: 972 };
const ease = Easing.bezier(0.65, 0, 0.35, 1);
// keyframes: [frame, box]; between two the camera moves with an ease-in-out
// on the beat: each move takes one beat and arrives exactly on a beat (holds in between stay still)
const snapEase = Easing.bezier(0.72, 0, 0.16, 1);
function beatKeys(keys: [number, Box][]) {
  const out: [number, Box][] = [];
  keys.forEach(([k, b], i) => {
    if (!i) { out.push([k, b]); return; }
    const prev = out[out.length - 1], same = JSON.stringify(b) === JSON.stringify(keys[i - 1][1]);
    const end = Math.max(prev[0] + 2, snapBeat(k));
    if (same) { out.push([end, b]); return; }
    const start = Math.max(prev[0] + 1, end - FPB);
    if (start > prev[0] + 0.5) out.push([start, prev[1]]);
    out.push([end, b]);
  });
  return out;
}
export function useCamera(keys0: [number, Box][]) {
  const f = useCurrentFrame(), keys = beatKeys(keys0);
  const ws = keys.map(([, b]) => fit(b)), fs = keys.map(([k]) => k);
  if (keys.length === 1) return ws[0];
  const at = (k: keyof Box) => interpolate(f, fs, ws.map((w) => w[k]), { easing: snapEase, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  // the size moves on a log scale so a zoom feels even
  const lw = interpolate(f, fs, ws.map((w) => Math.log(w.w)), { easing: snapEase, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const w = Math.exp(lw), cx = at("x") + at("w") / 2, cy = at("y") + at("h") / 2;
  return { x: cx - w / 2, y: cy - w * 9 / 32, w, h: w * 9 / 16 };
}

// the app screen in a browser-like frame; children are drawn in screenshot coordinates (they zoom with it)
export const Screen: React.FC<{ win: Box; layers: { src: string; opacity?: number }[]; children?: React.ReactNode; url?: string }> = ({ win, layers, children, url }) => {
  const s = FRAME.w / win.w, f = useCurrentFrame();
  const ph = (f % (FPB * 4)) / 7, bump = ph < 1 ? (1 - ph) * 0.006 : 0;       // a 0.6 % push on each downbeat
  return (
    <AbsoluteFill style={{ transform: `scale(${1 + bump})` }}>
      <div style={{ position: "absolute", left: FRAME.x, top: FRAME.y - 40, width: FRAME.w, height: FRAME.h + 40, borderRadius: 18, overflow: "hidden",
        background: "#fff", boxShadow: "0 30px 80px rgba(0,37,84,.22), 0 4px 14px rgba(0,37,84,.10)" }}>
        <div style={{ height: 40, background: "#E9EEF5", display: "flex", alignItems: "center", gap: 8, padding: "0 16px", borderBottom: `1px solid ${C.line}` }}>
          {["#F26B5B", "#F5BF4F", "#5CC26E"].map((c) => <i key={c} style={{ width: 13, height: 13, borderRadius: 7, background: c, display: "block" }} />)}
          <div style={{ marginLeft: 18, flex: "0 1 560px", height: 24, borderRadius: 12, background: "#fff", color: C.ink2, font: `500 14px ${FONT}`,
            display: "flex", alignItems: "center", padding: "0 14px" }}>{url || "croscan · 위험작업 허가서 사전검토"}</div>
        </div>
        <div style={{ position: "relative", width: FRAME.w, height: FRAME.h, overflow: "hidden" }}>
          <div style={{ position: "absolute", left: 0, top: 0, width: 1920, height: 1080, transformOrigin: "0 0",
            transform: `scale(${s}) translate(${-win.x}px, ${-win.y}px)` }}>
            {layers.map((l, i) => <Img key={i} src={staticFile(l.src)} style={{ position: "absolute", left: 0, top: 0, width: 1920, height: 1080, opacity: l.opacity ?? 1 }} />)}
            <ScaleCtx.Provider value={s}>{children}</ScaleCtx.Provider>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
const ScaleCtx = React.createContext(1);

// a box drawn around a part of the screen, from frame a to b (in screen pixels its line keeps its width)
// pops in on the beat (overshoot, then settles), leaves on a beat
export const Mark: React.FC<{ b: Box; a: number; z?: number; color?: string; p?: number; label?: string }> = ({ b, a: a0, z: z0 = 9999, color = C.ask, p = 6, label }) => {
  const f = useCurrentFrame(), s = React.useContext(ScaleCtx), a = snapBeat(a0), z = z0 >= 9999 ? z0 : snapBeat(z0);
  const o = interpolate(f, [a - 1, a + 2, z - 4, z], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const grow = interpolate(f, [a, a + 7], [1.3, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.back(2.2)) });
  const bx = pad(b, p / 1);
  return (
    <div style={{ position: "absolute", left: bx.x, top: bx.y, width: bx.w, height: bx.h, opacity: o, transform: `scale(${grow})`, transformOrigin: "center",
      border: `${4 / s}px solid ${color}`, borderRadius: 10 / s, boxShadow: `0 0 0 ${6 / s}px ${color}33`, background: `${color}10` }}>
      {label && <div style={{ position: "absolute", left: -4 / s, top: -56 / s, padding: `${6 / s}px ${16 / s}px`, borderRadius: 10 / s, background: color, color: "#fff",
        font: `700 ${30 / s}px ${FONT}`, whiteSpace: "nowrap", boxShadow: `0 ${4 / s}px ${12 / s}px rgba(0,0,0,.18)` }}>{label}</div>}
    </div>
  );
};
// a click: a pointer comes in and a ring opens at the point
export const Click: React.FC<{ x: number; y: number; at: number }> = ({ x, y, at: at0 }) => {
  const f = useCurrentFrame(), s = React.useContext(ScaleCtx), at = snapBeat(at0);
  if (f < at - 20 || f > at + 30) return null;
  const move = interpolate(f, [at - 20, at], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  const ring = interpolate(f, [at, at + 22], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <>
      {f >= at && <div style={{ position: "absolute", left: x - 40 / s * ring, top: y - 40 / s * ring, width: 80 / s * ring, height: 80 / s * ring, borderRadius: "50%",
        border: `${4 / s}px solid ${C.blue}`, opacity: 1 - ring }} />}
      <svg viewBox="0 0 24 24" style={{ position: "absolute", left: x + 60 / s * move, top: y + 60 / s * move, width: 36 / s, height: 36 / s, opacity: 1 - interpolate(f, [at + 20, at + 30], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>
        <path d="M3 2l7 19 2.6-7.4L20 11z" fill="#fff" stroke="#0F1B2D" strokeWidth="1.6" strokeLinejoin="round" />
      </svg>
    </>
  );
};

// the line said on screen: a navy pill at the bottom, in from below
export const Caption: React.FC<{ text: string; from?: number; sub?: string }> = ({ text, from = FPB, sub }) => {
  const f = useCurrentFrame(), { fps } = useVideoConfig();
  const k = spring({ frame: f - snapBeat(from), fps, config: { damping: 11, stiffness: 260, mass: 0.6 } });
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 64, display: "flex", flexDirection: "column", alignItems: "center", gap: 10,
      opacity: k, transform: `translateY(${(1 - k) * 30}px)` }}>
      <div style={{ padding: "18px 40px", borderRadius: 999, background: C.navy9, color: "#fff", font: `700 46px ${FONT}`, letterSpacing: "-0.5px",
        boxShadow: "0 14px 40px rgba(0,37,84,.35)" }}>{text}</div>
      {sub && <div style={{ padding: "6px 16px", borderRadius: 999, background: "rgba(255,255,255,.92)", color: C.ink2, font: `500 22px ${FONT}` }}>{sub}</div>}
    </div>
  );
};
export const Bg: React.FC = () => <AbsoluteFill style={{ background: `radial-gradient(120% 90% at 50% 0%, #FFFFFF 0%, ${C.ground} 70%, #E3E9F2 100%)` }} />;
// fades a scene in and out (scenes overlap by OVER frames: a cross-fade)
// a cut on the beat: the new scene punches in (scale and blur for 5 frames), the old one leaves in 3 frames
export const Fade: React.FC<{ len: number; children: React.ReactNode; first?: boolean; last?: boolean }> = ({ len, children, first, last }) => {
  const f = useCurrentFrame();
  const inT = first ? 1 : interpolate(f, [0, 5], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  void len; void last;
  return <AbsoluteFill style={{ transform: `scale(${1 + 0.03 * (1 - inT)})` }}>{children}</AbsoluteFill>;
};
