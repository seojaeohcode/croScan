// Motion pieces for the beat-cut intro and ending (references: soft glossy shapes, words cut on the beat, ripples, ribbons).
// No 3D engine: gradients, shadows and SVG give the glossy look.
import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { C, FONT, HEAD } from "./lib";

// the music: Kevin MacLeod "Getting it Done", 136 BPM, first beat at 0.02 s
import { BPM, FPB } from "./beat";
export { BPM, FPB };
export const beat = (b: number) => Math.round(b * FPB);   // frame of beat b (inside a scene that starts on a beat)
// motion that moves only on the beat: a step at each beat (eased over its first 5 frames)
export const stepped = (f: number, per = 1) => { const k = Math.floor(f / FPB), ph = Math.min(1, (f - k * FPB) / 5); return (k + (1 - Math.pow(1 - ph, 3))) * per; };
// a bounce on each beat: 1 on the beat, 0 after 7 frames
export const hit = (f: number) => { const ph = (f % FPB) / 7; return ph < 1 ? Math.pow(1 - ph, 2) : 0; };
export const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const out3 = Easing.out(Easing.cubic), back = Easing.out(Easing.back(1.7)), inout = Easing.bezier(0.65, 0, 0.35, 1);
export const ease = { out3, back, inout };
// 0→1 from frame a over n frames
export const tw = (f: number, a: number, n = 8, e = out3) => interpolate(f, [a, a + n], [0, 1], { ...clamp, easing: e });
// a short bump on each beat (1 on the beat, back to 0 in 6 frames): for scale pulses
export const pulse = (f: number, from = 0) => { if (f < from) return 0; const p = ((f - from) % FPB) / 6; return p < 1 ? 1 - p : 0; };

export const Grad: React.FC<{ a?: string; b?: string; angle?: number; children?: React.ReactNode }> = ({ a = C.navy, b = C.blue, angle = 135, children }) =>
  <AbsoluteFill style={{ background: `linear-gradient(${angle}deg, ${a} 0%, ${b} 100%)` }}>{children}</AbsoluteFill>;
export const White: React.FC<{ children?: React.ReactNode }> = ({ children }) =>
  <AbsoluteFill style={{ background: "radial-gradient(120% 90% at 50% 10%, #FFFFFF 0%, #F0F4F8 75%, #E3E9F2 100%)" }}>{children}</AbsoluteFill>;

// a glossy pill (a field or kind of work) floating with a soft shadow
export const Chip: React.FC<{ x: number; y: number; label: string; color?: string; s?: number; o?: number; rot?: number; glow?: string }> = ({ x, y, label, color = "#FFFFFF", s = 1, o = 1, rot = 0, glow }) => (
  <div style={{ position: "absolute", left: x, top: y, transform: `translate(-50%,-50%) scale(${s}) rotate(${rot}deg)`, opacity: o, padding: "18px 34px", borderRadius: 999,
    background: `linear-gradient(180deg, #FFFFFF 0%, ${color} 100%)`, color: C.navy, font: `800 38px ${FONT}`, whiteSpace: "nowrap", letterSpacing: "-0.5px",
    boxShadow: `0 18px 40px rgba(0,20,60,.28), inset 0 -6px 14px rgba(16,56,192,.18), inset 0 4px 8px rgba(255,255,255,.9)${glow ? `, 0 0 0 8px ${glow}` : ""}`,
    border: "1px solid rgba(255,255,255,.7)" }}>{label}</div>
);
// a glossy sphere
export const Sphere: React.FC<{ x: number; y: number; r: number; c1?: string; c2?: string; o?: number }> = ({ x, y, r, c1 = "#9DB4EE", c2 = C.blue, o = 1 }) => (
  <div style={{ position: "absolute", left: x - r, top: y - r, width: 2 * r, height: 2 * r, borderRadius: "50%", opacity: o,
    background: `radial-gradient(circle at 32% 28%, #FFFFFF 0%, ${c1} 22%, ${c2} 70%, #001A55 100%)`, boxShadow: `0 ${r * 0.35}px ${r * 0.8}px rgba(0,20,60,.30)` }} />
);
// very large outline type behind (moves slowly)
export const Outline: React.FC<{ text: string; x: number; y: number; size?: number; color?: string; o?: number }> = ({ text, x, y, size = 300, color = "rgba(16,56,192,.16)", o = 1 }) => (
  <div style={{ position: "absolute", left: x, top: y, font: `800 ${size}px/1 ${HEAD}`, color: "transparent", WebkitTextStroke: `3px ${color}`, whiteSpace: "nowrap", opacity: o, letterSpacing: "-4px" }}>{text}</div>
);
// typing with a caret
export const Typing: React.FC<{ text: string; a: number; perChar?: number; style?: React.CSSProperties }> = ({ text, a, perChar = 2.2, style }) => {
  const f = useCurrentFrame(), n = Math.max(0, Math.min(text.length, Math.floor((f - a) / perChar)));
  return <span style={style}>{text.slice(0, n)}<span style={{ opacity: f % 16 < 9 ? 1 : 0, fontWeight: 300, marginLeft: 4 }}>|</span></span>;
};
// concentric rings that open from a point
export const Ripples: React.FC<{ x: number; y: number; a: number; n?: number; color?: string; max?: number }> = ({ x, y, a, n = 4, color = "#FFFFFF", max = 1100 }) => {
  const f = useCurrentFrame();
  return <>{Array.from({ length: n }).map((_, i) => {
    const t = tw(f, a + i * 5, 34, out3); if (t <= 0 || t >= 1) return null;
    const r = t * max;
    return <div key={i} style={{ position: "absolute", left: x - r, top: y - r, width: 2 * r, height: 2 * r, borderRadius: "50%", border: `${6 - i}px solid ${color}`, opacity: (1 - t) * 0.8 }} />;
  })}</>;
};
// the scan beam: a bright line with a glow moving down over [a, a+n]
export const Beam: React.FC<{ a: number; n: number; top?: number; bottom?: number }> = ({ a, n, top = 200, bottom = 880 }) => {
  const f = useCurrentFrame(), t = tw(f, a, n, inout); if (f < a || f > a + n + 6) return null;
  const y = top + (bottom - top) * t;
  return (<>
    <div style={{ position: "absolute", left: 0, right: 0, top: top, height: y - top, background: "linear-gradient(180deg, rgba(91,134,255,0) 0%, rgba(91,134,255,.16) 100%)" }} />
    <div style={{ position: "absolute", left: 0, right: 0, top: y - 3, height: 6, background: "#BFD2FF", boxShadow: "0 0 30px 10px rgba(120,160,255,.85)" }} />
  </>);
};
// a circle that grows from (x, y) and covers the screen (a scene change inside a scene)
export const Wipe: React.FC<{ a: number; n?: number; x?: number; y?: number; color?: string; children?: React.ReactNode }> = ({ a, n = 14, x = 960, y = 540, color = "#FFFFFF", children }) => {
  const f = useCurrentFrame(), t = tw(f, a, n, inout); if (t <= 0) return null;
  return <AbsoluteFill style={{ clipPath: `circle(${t * 2300}px at ${x}px ${y}px)`, background: color }}>{children}</AbsoluteFill>;
};
// flowing ribbons (the ending): wide soft strokes whose waves move
export const Ribbons: React.FC<{ o?: number }> = ({ o = 1 }) => {
  const f = useCurrentFrame();
  const path = (k: number, amp: number, y0: number) => {
    let d = "";
    for (let x = -100; x <= 2020; x += 40) { const y = y0 + Math.sin((x / 420) + f / 26 + k) * amp + Math.sin((x / 170) + f / 17 + k * 2) * amp * 0.25; d += `${x === -100 ? "M" : "L"}${x},${y.toFixed(1)} `; }
    return d;
  };
  return (
    <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0, opacity: o }}>
      <defs>
        <linearGradient id="rb1" x1="0" x2="1"><stop offset="0" stopColor="#5B86FF" stopOpacity="0" /><stop offset=".4" stopColor="#9DB4EE" /><stop offset="1" stopColor="#FFFFFF" stopOpacity=".2" /></linearGradient>
        <linearGradient id="rb2" x1="0" x2="1"><stop offset="0" stopColor="#FFFFFF" stopOpacity=".1" /><stop offset=".6" stopColor="#7FA2FF" /><stop offset="1" stopColor="#1038C0" stopOpacity="0" /></linearGradient>
        <filter id="soft"><feGaussianBlur stdDeviation="6" /></filter>
      </defs>
      <path d={path(0, 120, 640)} stroke="url(#rb1)" strokeWidth={130} fill="none" strokeLinecap="round" opacity={0.55} filter="url(#soft)" />
      <path d={path(2, 90, 760)} stroke="url(#rb2)" strokeWidth={70} fill="none" strokeLinecap="round" opacity={0.6} />
      <path d={path(4, 150, 420)} stroke="url(#rb2)" strokeWidth={26} fill="none" strokeLinecap="round" opacity={0.45} />
    </svg>
  );
};
// one line of big type that lands on its beat (slides up a little, a slight overshoot)
export const Word: React.FC<{ a: number; z?: number; children: React.ReactNode; size?: number; color?: string; x?: number; y?: number; align?: "center" | "left"; weight?: number }> =
  ({ a, z = 1e9, children, size = 120, color = "#fff", x = 960, y = 540, align = "center", weight = 800 }) => {
    const early = Math.min(5, a), f = useCurrentFrame(); if (f < a - early || f >= z) return null;
    const t = early ? tw(f, a - early, early + 2, Easing.out(Easing.back(2.6))) : 1, settle = early ? 0 : 1 - tw(f, 0, 6, ease.out3);
    const oz = z < 1e9 ? 1 - tw(f, z - 3, 3) : 1;
    return <div style={{ position: "absolute", left: align === "center" ? 0 : x, right: align === "center" ? 0 : undefined, top: y, textAlign: align,
      transform: `translateY(${(1 - t) * 40 - size / 2}px) scale(${(0.92 + 0.08 * t) * (1 + 0.12 * settle)})`, opacity: Math.min(t * 1.6, oz), font: `${weight} ${size}px/1.1 ${FONT}`, color, letterSpacing: "-2px" }}>{children}</div>;
  };
