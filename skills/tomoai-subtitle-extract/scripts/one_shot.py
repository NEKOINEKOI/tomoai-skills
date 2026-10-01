"""
一键视频字幕提取流程。
用法: python one_shot.py <video.mp4> [model_size] [translations.txt]
- 无 translations.txt: 只生成英文 original.srt
- 有 translations.txt: 同时生成中文 srt
"""
import os, sys, subprocess, json

VIDEO = sys.argv[1]
MODEL = sys.argv[2] if len(sys.argv) > 2 else "large-v3"
TRANS_FILE = sys.argv[3] if len(sys.argv) > 3 else None

OUT_DIR = os.path.dirname(os.path.abspath(VIDEO))
PY = sys.executable

print(f"=== Step 1: Extract audio ===")
audio = os.path.join(OUT_DIR, "audio_extract.wav")
subprocess.run([
    "ffmpeg", "-y", "-i", VIDEO, "-vn",
    "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
    audio
], check=True, capture_output=True)
print(f"Audio: {audio}")

print(f"\n=== Step 2: ASR transcription ===")
subprocess.run([
    PY, os.path.join(os.path.dirname(__file__), "transcribe_cpu.py"),
    audio, MODEL
], check=True)
print(f"Segments: segments.json")

print(f"\n=== Step 3: Generate Chinese srt ===")
if TRANS_FILE and os.path.exists(TRANS_FILE):
    base_name = os.path.splitext(os.path.basename(VIDEO))[0]
    out_srt = os.path.join(OUT_DIR, base_name + "_zh.srt")
    subprocess.run([
        PY, os.path.join(os.path.dirname(__file__), "gen_zh_srt.py"),
        "segments.json", TRANS_FILE, out_srt
    ], check=True)
    print(f"Chinese srt: {out_srt}")
else:
    print("No translations file provided. Only English srt generated.")

print(f"\n=== Step 4: Validate ===")
for srt in ["original.srt", os.path.join(OUT_DIR, os.path.splitext(base_name)[0] + "_zh.srt") if TRANS_FILE else None]:
    if srt and os.path.exists(srt):
        subprocess.run([PY, os.path.join(os.path.dirname(__file__), "validate_srt.py"), srt], check=True)

print("\nDone!")
