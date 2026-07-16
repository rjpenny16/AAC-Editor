import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const voiceDir = join(root, ".media", "audio", "voice");
const source = join(voiceDir, "narration.mp3");
const alignmentPath = join(voiceDir, "elevenlabs-alignment.json");

const lines = [
  "Build a complete TD Snap topic page—without editing every button by hand.",
  "Connect Page Builder to the page set already open on your computer.",
  "Create a World Cup Final topic for Spain versus Argentina.",
  "Add ready-to-say phrases, then arrange them in a live, color-coded preview.",
  "Review every change, then update TD Snap.",
  "The finished page appears in the same page set—ready to use, share, and sync.",
  "Less editing. More communicating.",
];

const payload = JSON.parse(readFileSync(alignmentPath, "utf8").replace(/^\uFEFF/, ""));
const a = payload.alignment;
const chars = a.characters;
const starts = a.character_start_times_seconds;
const ends = a.character_end_times_seconds;
const fullText = chars.join("");
const ranges = [];
let cursor = 0;

for (const text of lines) {
  const startIndex = fullText.indexOf(text, cursor);
  if (startIndex < 0) throw new Error(`Narration line missing from ElevenLabs alignment: ${text}`);
  const endIndex = startIndex + text.length;
  ranges.push({ text, startIndex, endIndex });
  cursor = endIndex;
}

const probe = spawnSync(
  "ffprobe",
  ["-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", source],
  { encoding: "utf8" },
);
if (probe.status !== 0) throw new Error(probe.stderr || "ffprobe failed");
const totalDuration = Number(probe.stdout.trim());
mkdirSync(voiceDir, { recursive: true });

const voices = ranges.map((range, index) => {
  const segmentStart = index === 0 ? 0 : Math.max(0, starts[range.startIndex] - 0.08);
  const segmentEnd = index + 1 < ranges.length
    ? Math.max(segmentStart + 0.1, starts[ranges[index + 1].startIndex] - 0.08)
    : totalDuration;
  const duration = segmentEnd - segmentStart;
  const output = join(voiceDir, `${String(index + 1).padStart(2, "0")}.mp3`);
  const ffmpeg = spawnSync(
    "ffmpeg",
    [
      "-hide_banner", "-loglevel", "error", "-ss", String(segmentStart), "-i", source,
      "-t", String(duration), "-c:a", "libmp3lame", "-q:a", "2", "-y", output,
    ],
    { encoding: "utf8" },
  );
  if (ffmpeg.status !== 0) throw new Error(ffmpeg.stderr || `ffmpeg failed for frame ${index + 1}`);

  const words = [];
  let wordStart = null;
  for (let i = range.startIndex; i <= range.endIndex; i += 1) {
    const isBoundary = i === range.endIndex || /\s/.test(chars[i]);
    if (wordStart == null && !isBoundary) wordStart = i;
    if (wordStart != null && isBoundary) {
      const text = chars.slice(wordStart, i).join("");
      words.push({
        id: `w${words.length}`,
        text,
        start: Number((starts[wordStart] - segmentStart).toFixed(3)),
        end: Number((ends[i - 1] - segmentStart).toFixed(3)),
      });
      wordStart = null;
    }
  }

  return {
    frame: index + 1,
    path: `.media/audio/voice/${String(index + 1).padStart(2, "0")}.mp3`,
    duration_s: Number(duration.toFixed(3)),
    provider: "elevenlabs",
    words,
  };
});

writeFileSync(join(root, "audio_meta.json"), `${JSON.stringify({ bgm: null, voices, sfx: [] }, null, 2)}\n`);
writeFileSync(
  join(voiceDir, "narration.words.json"),
  `${JSON.stringify(voices.flatMap((voice) => voice.words.map((word) => ({
    ...word,
    frame: voice.frame,
  }))), null, 2)}\n`,
);

console.log(JSON.stringify({ totalDuration, frames: voices.map((v) => ({ frame: v.frame, duration_s: v.duration_s })) }));
