import sys, json, os
from faster_whisper import WhisperModel

def format_ts(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t - int(t)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

audio = "audio_full.wav"
out_dir = os.path.dirname(os.path.abspath(audio))

# CPU 推理：large-v3 + int8 量化，速度与精度平衡
model = WhisperModel("large-v3", device="cpu", compute_type="int8")
segments, info = model.transcribe(
    audio, beam_size=5, vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500)
)
print(f"Detected language: {info.language} (prob {info.language_probability:.2f})", flush=True)

segs = []
srt_path = os.path.join(out_dir, "original.srt")
with open(srt_path, "w", encoding="utf-8") as f:
    for i, s in enumerate(segments, 1):
        text = s.text.strip()
        segs.append({"start": round(s.start, 3), "end": round(s.end, 3), "text": text})
        f.write(f"{i}\n{format_ts(s.start)} --> {format_ts(s.end)}\n{text}\n\n")

json_path = os.path.join(out_dir, "segments.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(segs, f, ensure_ascii=False, indent=2)

print(f"Segments: {len(segs)}", flush=True)
print(f"Wrote {srt_path}", flush=True)
print(f"Wrote {json_path}", flush=True)
