# -*- coding: utf-8 -*-
"""faster-whisper GPU 转写（RTX 显卡，fp16）。

用法:
  # 关键：cublas64_12.dll 来自 torch 的 lib 目录，必须先加进 PATH，
  # 否则 ctranslate2 报 "Library cublas64_12.dll is not found"
  # 把下面这个路径换成你机器上 torch/lib 的实际位置
  export PATH="/path/to/your/python/site-packages/torch/lib:$PATH"
  HF_HUB_OFFLINE=1 python transcribe_gpu.py audio.wav [out.json]

实测：17 分钟音频，RTX 5060 + large-v3 fp16 约 5.5 分钟（CPU int8 需数十分钟）。
"""
import json, os, sys

# 本地模型快照：不要用 "large-v3" 这种别名，联网会走代理 502
# 首次运行请用 huggingface-cli 下载：
#   huggingface-cli download Systran/faster-whisper-large-v3
# 然后把 MODEL_DIR 指向本地 snapshots 目录
_DEFAULT_MODEL = os.path.expanduser(
    os.path.join("~", ".cache", "huggingface", "hub",
                 "models--Systran--faster-whisper-large-v3", "snapshots",
                 "edaa852ec7e145841d8ffdb056a99866b5f0a478")
)
MODEL_DIR = os.environ.get("WHISPER_MODEL_DIR", _DEFAULT_MODEL)

from faster_whisper import WhisperModel

def main():
    audio = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(audio)[0] + "_segments.json"

    model = WhisperModel(MODEL_DIR, device="cuda", compute_type="float16")
    segments, info = model.transcribe(
        audio,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=400),
        condition_on_previous_text=False,
        word_timestamps=True,  # 词级时间戳：段内重建时间轴用（避免中文挂在静音停顿处）
    )
    print("LANG:", info.language, "PROB:", info.language_probability, flush=True)

    data = []
    for seg in segments:
        words = []
        try:
            for w in (seg.words or []):
                words.append({"start": round(w.start, 3), "end": round(w.end, 3),
                              "word": w.word})
        except Exception:
            words = []
        data.append({"id": seg.id, "start": round(seg.start, 3),
                     "end": round(seg.end, 3), "text": seg.text.strip(),
                     "words": words})
        print(seg.id, round(seg.start, 2), round(seg.end, 2), seg.text.strip(), flush=True)

    with open(out, "w", encoding="utf-8") as f:
        json.dump({"language": info.language, "segments": data}, f, ensure_ascii=False, indent=1)
    print("DONE", len(data), "->", out)

if __name__ == "__main__":
    main()
