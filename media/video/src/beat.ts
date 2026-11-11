// The music's beat (Kevin MacLeod "Getting it Done", 136 BPM). Every scene starts on a beat, so inside a scene
// beat k is at frame k × FPB; moves, pops and cuts are placed on it.
export const BPM = 136, FPB = (30 * 60) / BPM;              // 13.24 frames a beat
export const snapBeat = (frame: number) => Math.round(frame / FPB) * FPB;
