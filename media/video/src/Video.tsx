// croScan 홍보 영상 (콘티: STORYBOARD.md, 자막은 Codex 검토안). 화면은 모두 실제 croScan(시연 자료)을 찍은 것.
import React from "react";
import { AbsoluteFill, Audio, Easing, Img, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import R from "./rects.json";
import { Bg, Box, C, Caption, Click, FONT, FULL, Fade, HEAD, Mark, Screen, pad, union, useCamera, useFonts } from "./lib";
import { INTRO_BEATS, Intro, OUTRO_BEATS, Outro } from "./IntroOutro";
import { FPB, beat } from "./motion";

const OVER = 0;                                     // scenes cut on the beat (no overlap): the new one punches in
// a zoom target with room under it for the caption
const room = (b: Box, p = 40): Box => { const x = pad(b, p); return { ...x, h: x.h * 1.3 }; };
const r = R as any;

// 1. 쌓인 서류: documents fall into a pile, the day's count runs up
const DOCS = [["허가서", C.navy], ["계획", "#5B6779"], ["허가서", C.navy], ["계획", "#5B6779"], ["계획", "#5B6779"], ["허가서", C.navy],
  ["계획", "#5B6779"], ["계획", "#5B6779"], ["허가서", C.navy], ["계획", "#5B6779"], ["계획", "#5B6779"], ["허가서", C.navy]] as const;
const Pile: React.FC = () => {
  const f = useCurrentFrame(), { fps } = useVideoConfig();
  const n = Math.round(interpolate(f, [10, 75], [0, 50], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) }));
  const head = spring({ frame: f - 40, fps, config: { damping: 200 } });
  return (
    <AbsoluteFill>
      <Bg />
      {DOCS.map(([t, c], i) => {
        const k = spring({ frame: f - i * 4, fps, config: { damping: 14, mass: 0.6 } });
        const x = 360 + (i % 4) * 70 + (i % 3) * 18, y = 560 - Math.floor(i / 4) * 26 - i * 6, rot = ((i * 37) % 17) - 8;
        return (
          <div key={i} style={{ position: "absolute", left: x, top: y - (1 - k) * 700, width: 300, height: 380, borderRadius: 14, background: "#fff",
            border: `1px solid ${C.line}`, boxShadow: "0 12px 30px rgba(0,37,84,.16)", transform: `rotate(${rot}deg)`, padding: 24 }}>
            <div style={{ display: "inline-block", padding: "4px 12px", borderRadius: 8, background: c, color: "#fff", font: `700 20px ${FONT}` }}>{t}</div>
            {[0, 1, 2, 3, 4, 5, 6].map((j) => <div key={j} style={{ height: 12, borderRadius: 6, background: "#E3E9F2", marginTop: 20, width: `${90 - (j * 23) % 40}%` }} />)}
          </div>
        );
      })}
      <div style={{ position: "absolute", left: 1020, top: 300, width: 760 }}>
        <div style={{ font: `800 210px/1 ${HEAD}`, color: C.navy, letterSpacing: "-4px" }}>{n}<span style={{ fontSize: 90, marginLeft: 10 }}>건</span></div>
        <div style={{ font: `600 38px ${FONT}`, color: C.ink2, marginTop: 18 }}>허가서 10 · 작업계획서 40 · 하루치</div>
        <div style={{ font: `600 32px ${FONT}`, color: C.ink2, marginTop: 12 }}>시연 자료 기준 (대조립 공장 하루)</div>
        <div style={{ font: `800 64px/1.25 ${FONT}`, color: C.ink, marginTop: 70, opacity: head, transform: `translateY(${(1 - head) * 24}px)`, letterSpacing: "-1px" }}>
          쌓인 서류,<br />겹치는 작업은?</div>
      </div>
    </AbsoluteFill>
  );
};

// 2·9. 로고
const Logo: React.FC<{ line: string; small?: string }> = ({ line, small }) => {
  const f = useCurrentFrame(), { fps } = useVideoConfig();
  const k = spring({ frame: f, fps, config: { damping: 16 } }), t = spring({ frame: f - 14, fps, config: { damping: 200 } });
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
      <Bg />
      <Img src={staticFile("croscan_logo_real.png")} style={{ width: 900, transform: `scale(${0.7 + 0.3 * k})`, opacity: k }} />
      <div style={{ marginTop: 56, font: `700 54px ${FONT}`, color: C.ink, opacity: t, transform: `translateY(${(1 - t) * 20}px)`, letterSpacing: "-1px" }}>{line}</div>
      {small && <div style={{ marginTop: 22, font: `500 28px ${FONT}`, color: C.ink2, opacity: t }}>{small}</div>}
    </AbsoluteFill>
  );
};

// 3. 빈칸과 확인할 내용을 먼저 묻습니다
const S3: React.FC = () => {
  const s = r.s3_form, both = union(s.location, s.daterow);
  const win = useCamera([[0, FULL], [22, FULL], [52, room(both, 70)], [96, room(both, 70)], [124, room(s.question, 50)]]);
  return (<AbsoluteFill><Bg />
    <Screen win={win} layers={[{ src: "shots/s3_form.png" }]}>
      <Mark b={s.location} a={50} z={118} label="팀 이름만" /><Mark b={s.daterow} a={58} z={118} label="종일 신청" />
      <Mark b={s.question} a={120} color={C.blue} label="croScan이 묻습니다" />
    </Screen>
    <Caption text="확인이 필요한 칸을 먼저 묻습니다" /></AbsoluteFill>);
};

// 4. 긴 답도 시간·장소·인원으로 (the whole answer is shown large while it is typed: the box itself is small)
const SAY = "실제 용접은 13시부터 15시까지만 합니다. 장소는 3BAY 12–14 칼럼입니다. 화재감시인 1명이 함께 들어갑니다.";
const TypeCard: React.FC<{ a: number; z: number }> = ({ a, z }) => {
  const f = useCurrentFrame();
  const n = Math.round(interpolate(f, [a + 6, a + 46], [0, SAY.length], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  const o = interpolate(f, [a, a + 8, z - 8, z], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", left: 300, right: 300, top: 150, opacity: o, transform: `translateY(${(1 - o) * 20}px)`, padding: "30px 40px", borderRadius: 24,
      background: "#fff", boxShadow: "0 24px 60px rgba(0,37,84,.28)", border: `2px solid ${C.blue}` }}>
      <div style={{ font: `700 26px ${FONT}`, color: C.blue, marginBottom: 12 }}>작업반장이 한 번에 적은 답</div>
      <div style={{ font: `600 40px/1.45 ${FONT}`, color: C.ink, letterSpacing: "-0.5px" }}>{SAY.slice(0, n)}<span style={{ opacity: f % 20 < 10 ? 1 : 0 }}>|</span></div>
    </div>
  );
};
const S4: React.FC = () => {
  const f = useCurrentFrame(), a = r.s4_typing, b = r.s4_spill;
  const win = useCamera([[0, FULL], [26, room(a.composer, 30)], [74, room(a.composer, 30)], [96, room(b.spill, 30)], [146, room(b.spill, 30)], [170, room(union(b.location, b.detail), 50)]]);
  const swap = interpolate(f, [beat(6), beat(6) + 4], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (<AbsoluteFill><Bg />
    <Screen win={win} layers={[{ src: "shots/s4_spill.png", opacity: swap }, { src: "shots/s4_typing.png", opacity: 1 - swap }]}>
      <Mark b={b.spill} a={98} z={150} color={C.ok} label="시간 · 장소 · 감시인을 나눠 읽음" />
      <Mark b={b.location} a={172} label="장소 → 3BAY 12-14 칼럼" /><Mark b={b.detail} a={182} label="실제 작업시간" />
    </Screen>
    <TypeCard a={beat(1)} z={beat(6)} />
    <Caption text="긴 답도 시간·장소·인원으로" /></AbsoluteFill>);
};

// 5. 답변을 맞는 칸에 파란 글씨로 (반영본 = 서버가 그린 제출본 앞장)
const S5: React.FC = () => {
  const p = r.s5_reflect.page, d = r.s5_reflect.pdf, k = p.w / d.w;
  const at = (bx: number[]): Box => ({ x: p.x + bx[0] * k, y: p.y + bx[1] * k, w: (bx[2] - bx[0]) * k, h: (bx[3] - bx[1]) * k });
  const loc = at(d.location), det = at(d.detail);
  const win = useCamera([[0, FULL], [24, FULL], [58, room(union(loc, det), 60)]]);
  return (<AbsoluteFill><Bg />
    <Screen win={win} layers={[{ src: "shots/s5_reflect.png" }]}>
      <Mark b={loc} a={60} color={C.blue} label="① 작업장소" /><Mark b={det} a={72} color={C.blue} label="② 실제 작업시간" />
    </Screen>
    <Caption text="답변을 맞는 칸에 파란 글씨로" sub="업로드한 원본 파일은 그대로 · 칸에 없는 내용은 별지로" /></AbsoluteFill>);
};

// 6. 남은 빈칸도 차례로 수정: 칸을 고르고 → 오른쪽 입력창에 값 → 「적용」 → 양식에 들어감
const S6: React.FC = () => {
  const f = useCurrentFrame(), s = r.s6_fedit, t = r.s6_typed, d = r.s6_applied;
  const win = useCamera([[0, FULL], [16, FULL], [44, room(union(s.sel, s.composer), 24)]]);
  const o2 = interpolate(f, [beat(7), beat(7) + 4], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const o3 = interpolate(f, [beat(10), beat(10) + 4], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (<AbsoluteFill><Bg />
    <Screen win={win} layers={[{ src: "shots/s6_fedit.png" }, { src: "shots/s6_typed.png", opacity: o2 }, { src: "shots/s6_applied.png", opacity: o3 }]}>
      <Click x={s.sel.x + s.sel.w / 2} y={s.sel.y + s.sel.h / 2} at={52} />
      <Mark b={s.sel} a={54} z={124} label="고른 칸" />
      <Mark b={s.fedit} a={64} z={124} color={C.blue} label="수정할 칸이 입력창 위에" />
      <Mark b={t.input} a={92} z={124} color={C.blue} label="값 입력" />
      <Click x={t.send.x + t.send.w / 2} y={t.send.y + t.send.h / 2} at={120} />
      <Mark b={d.field} a={140} color={C.ok} label="양식에 들어감" />
    </Screen>
    <Caption text="남은 빈칸도 차례로 수정" /></AbsoluteFill>);
};

// 7. 작업 간 위험을 규칙으로 검토: the result in one card, then the reason of the first pair, large
const Stat: React.FC<{ a: number; z: number }> = ({ a, z }) => {
  const f = useCurrentFrame(), { fps } = useVideoConfig();
  const k = spring({ frame: f - a, fps, config: { damping: 200 } }), o = Math.min(k, interpolate(f, [z - 10, z], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  const n = Math.round(interpolate(f, [a + 4, a + 34], [0, 13], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) }));
  const pri = [["1순위", "즉시 조정", 8, C.p1, "#FEF3F2"], ["2순위", "조건부 병행", 3, "#9A4D00", "#FFF6E5"], ["3순위", "확인 필요", 2, "#3D5A80", "#EEF2F8"]] as const;
  return (
    <AbsoluteFill style={{ background: `rgba(240,244,248,${0.78 * o})`, alignItems: "center", justifyContent: "center" }}>
      <div style={{ opacity: o, transform: `scale(${0.94 + 0.06 * k})`, padding: "44px 60px", borderRadius: 28, background: "#fff", boxShadow: "0 30px 80px rgba(0,37,84,.25)", textAlign: "center" }}>
        <div style={{ font: `700 30px ${FONT}`, color: C.blue }}>쌍작업 위험탐지 결과 · 규칙 판정</div>
        <div style={{ font: `800 96px/1.15 ${HEAD}`, color: C.ink, margin: "8px 0 26px" }}>위험 쌍 <span style={{ color: C.p1 }}>{n}쌍</span></div>
        <div style={{ display: "flex", gap: 22, justifyContent: "center" }}>
          {pri.map(([l, d, v, c, bg], i) => {
            const kk = spring({ frame: f - a - 18 - i * 6, fps, config: { damping: 200 } });
            return <div key={l} style={{ opacity: kk, transform: `translateY(${(1 - kk) * 16}px)`, display: "flex", alignItems: "center", gap: 16, padding: "16px 28px",
              borderRadius: 18, border: `2px solid ${c}55`, background: bg, color: c }}>
              <b style={{ font: `800 64px/1 ${HEAD}` }}>{v}</b><span style={{ font: `700 30px/1.25 ${FONT}`, textAlign: "left" }}>{l}<br /><i style={{ fontStyle: "normal", fontWeight: 500, fontSize: 24 }}>{d}</i></span></div>;
          })}
        </div>
        <div style={{ font: `600 28px ${FONT}`, color: C.ink2, marginTop: 28 }}>시연 자료 기준: 허가서 10 · 작업계획서 40 → 445쌍 검토 → 13쌍 경보</div>
      </div>
    </AbsoluteFill>
  );
};
const S7: React.FC = () => {
  const s = r.s7_pairs;
  const win = useCamera([[0, FULL], [100, FULL], [128, room(union(s.head, s.chain), 16)]]);
  return (<AbsoluteFill><Bg />
    <Screen win={win} layers={[{ src: "shots/s7_pairs.png" }]} url="croscan · 안전관리자 · 수집 문서 검토">
      <Mark b={s.tabs} a={6} z={30} color={C.blue} />
      <Mark b={s.head} a={132} z={160} color={C.p1} label="1순위 쌍" />
      <Mark b={s.chain} a={160} color={C.p1} label="조건 → 원인 → 사고" />
    </Screen>
    <Stat a={beat(2)} z={beat(8)} />
    <Caption text="작업 간 위험을 규칙으로 검토" /></AbsoluteFill>);
};

// 8. 언제, 어디서 겹치는지 한눈에: the pair's two works lit on the plan map at the time they meet
const S8: React.FC = () => {
  const s = r.s8_map, clockL: Box = { x: s.clock.x, y: s.clock.y, w: 640, h: s.clock.h };
  const win = useCamera([[0, FULL], [18, FULL], [44, room(clockL, 40)], [78, room(clockL, 40)], [106, room(s.pair, 150)]]);
  return (<AbsoluteFill><Bg />
    <Screen win={win} layers={[{ src: "shots/s8_map.png" }]} url="croscan · 안전관리자 · 계획 배치도">
      <Mark b={clockL} a={46} z={80} color={C.blue} label="고른 시각" />
      <Mark b={s.pair} a={108} color={C.p1} label="같은 시간 · 같은 곳의 두 작업" />
    </Screen>
    <Caption text="언제, 어디서 겹치는지 한눈에" /></AbsoluteFill>);
};

// 장면 길이는 박자(136 BPM)로 잰다: 장면이 바뀌는 곳이 박자에 떨어지게, 내레이션이 들어갈 만큼 (2박 단위)
// [장면, 박 수, 내레이션 파일 번호, 그 장면 안에서 말이 시작하는 박]
const SCENES: [React.FC, number, number[], number[]][] = [
  [Intro, INTRO_BEATS, [1, 2], [1, 16]], [S3, 14, [3], [0.7]], [S4, 18, [4], [0.7]], [S5, 16, [5], [0.7]], [S6, 14, [6], [0.7]],
  [S7, 22, [7], [0.7]], [S8, 14, [8], [0.7]], [Outro, OUTRO_BEATS, [9], [10]]];
const NARR = [5.64, 3.89, 5.02, 6.58, 5.81, 4.97, 7.8, 4.97, 3.41];   // seconds of public/audio/n1–n9.mp3
const at = (b: number) => Math.round(b * FPB + 0.6);              // frame of beat b of the whole video (first beat at 0.02 s)
const BEATS = SCENES.map((_, i) => SCENES.slice(0, i).reduce((a, x) => a + x[1], 0));
export const TOTAL = at(BEATS[BEATS.length - 1] + SCENES[SCENES.length - 1][1]);
const VOICES = SCENES.flatMap(([, , ns, bs], i) => ns.map((n, k) => ({ n, from: at(BEATS[i] + bs[k]), len: Math.ceil(NARR[n - 1] * 30) })));
// the music: softer under the voice, up where nobody speaks; in from the start, out over the last 4 beats
function musicVolume(f: number) {
  let duck = 1;                                           // 1 = full, 0 = under the voice; 10-frame ramps
  for (const v of VOICES) duck = Math.min(duck, f < v.from ? Math.min(1, (v.from - f) / 10) : f > v.from + v.len ? Math.min(1, (f - v.from - v.len) / 10) : 0);
  const v = 0.14 + (0.34 - 0.14) * duck;
  const fade = Math.min(1, f / 6, (TOTAL - f) / (FPB * 4));
  return Math.max(0, v * fade);
}

export const CroScan: React.FC = () => {
  useFonts();
  return (
    <AbsoluteFill style={{ background: C.ground, fontFamily: FONT }}>
      <Audio src={staticFile("audio/bgm_getting_it_done.mp3")} volume={musicVolume} />
      {VOICES.map((v) => <Sequence key={`n${v.n}`} from={v.from} durationInFrames={v.len + 6}><Audio src={staticFile(`audio/n${v.n}.mp3`)} volume={1} /></Sequence>)}
      {SCENES.map(([S, nb], i) => {
        const from = at(BEATS[i]), to = at(BEATS[i] + nb), len = to - from, last = i === SCENES.length - 1, pre = i ? OVER : 0;
        // the beat-timed scenes count from their own first beat (the cross-fade frames before it show nothing of them yet)
        const timed = S === Intro || S === Outro;
        return (
          <Sequence key={i} from={from - pre} durationInFrames={len + pre}>
            <Fade len={len + pre} first={i === 0} last={last}>{timed && pre ? <Sequence from={pre}><S /></Sequence> : <S />}</Fade>
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
