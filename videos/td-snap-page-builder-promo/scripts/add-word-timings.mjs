import fs from "node:fs";

const lines = [...fs.readFileSync("SCRIPT.md", "utf8").matchAll(/^    (.+)$/gm)].map((m) => m[1]);
const log = fs.readFileSync(".hyperframes/audio.stderr.log", "utf8");
const speech = new Map([...log.matchAll(/voice\s+(\d+):.*\(([\d.]+)s,/g)].map((m) => [Number(m[1]), Number(m[2])]));

function addWords(path, idKey) {
  const meta = JSON.parse(fs.readFileSync(path, "utf8"));
  meta.voices.forEach((voice, i) => {
    const text = lines[i];
    const words = text.split(/\s+/);
    const weights = words.map((word) => Math.max(1, word.replace(/[^\p{L}\p{N}]/gu, "").length));
    const gap = 0.035;
    const startPad = 0.12;
    const usable = speech.get(i + 1) - startPad - 0.12 - gap * (words.length - 1);
    const total = weights.reduce((sum, weight) => sum + weight, 0);
    let cursor = startPad;
    voice.words = words.map((word, index) => {
      const start = cursor;
      const end = start + (usable * weights[index]) / total;
      cursor = end + gap;
      return { id: `w${index}`, text: word, start: +start.toFixed(3), end: +end.toFixed(3) };
    });
    if (idKey) voice[idKey] = String(i + 1).padStart(2, "0");
    console.assert(voice.words.length > 0 && voice.words.at(-1).end <= voice.duration_s, `bad timing for voice ${i + 1}`);
  });
  fs.writeFileSync(path, `${JSON.stringify(meta, null, 2)}\n`);
}

console.assert(lines.length === 6 && speech.size === 6, "expected six narration lines and source durations");
addWords("audio_meta.json");
addWords("audio_engine_meta.json", "id");
