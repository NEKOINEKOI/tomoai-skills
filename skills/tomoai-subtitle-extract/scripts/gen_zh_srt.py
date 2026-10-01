"""
通用中文 srt 生成器——从 segments.json + 翻译文本生成带标点断行的中文字幕。
用法: python gen_zh_srt.py segments.json translations.txt [output.srt]
"""
import json, os, re, sys

def fmt(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def auto_break(text, max_len=20):
    """在标点处断行，语义完整，单行不超过 max_len 字。"""
    if len(text) <= max_len:
        return text

    parts = re.split(r'([，。！？、；：—…])', text)
    lines, cur, i = [], "", 0
    while i < len(parts):
        seg = parts[i]
        combined = seg + parts[i + 1] if i + 1 < len(parts) else seg
        i += 2 if i + 1 < len(parts) else 1
        if len(cur) + len(combined) <= max_len or not cur:
            cur += combined
        else:
            if cur:
                lines.append(cur.rstrip())
            cur = combined
    if cur:
        lines.append(cur.rstrip())

    final = []
    for line in lines:
        if len(line) > max_len:
            final.extend(re.findall(f'.{{1,{max_len}}}', line))
        else:
            final.append(line)

    # 合并孤立的标点行
    merged = []
    for line in final:
        if merged and re.match(r'^[，。！？、；：—…]+$', line):
            merged[-1] += line
        else:
            merged.append(line)
    return "\n".join(merged)

def main():
    if len(sys.argv) < 3:
        print("Usage: python gen_zh_srt.py segments.json translations.txt [output.srt]")
        sys.exit(1)

    segs_path = sys.argv[1]
    trans_path = sys.argv[2]
    out_path = sys.argv[3] if len(sys.argv) > 3 else os.path.splitext(segs_path)[0] + "_zh.srt"

    segs = json.load(open(segs_path, encoding="utf-8"))
    translations = [line.strip() for line in open(trans_path, encoding="utf-8").readlines() if line.strip()]

    assert len(translations) == len(segs), f"段数不匹配: translations={len(translations)} segs={len(segs)}"

    lines = []
    for i, (s, t) in enumerate(zip(segs, translations), 1):
        subtitle = auto_break(t)
        lines.append(f"{i}\n{fmt(s['start'])} --> {fmt(s['end'])}\n{subtitle}\n")

    with open(out_path, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write("\n".join(lines))

    print(f"Wrote {out_path} ({len(segs)} segments)")
    print("Preview (first 5):")
    for i in range(min(5, len(lines))):
        print(f"\n--- Block {i+1} ---")
        for line in lines[i].split("\n"):
            print(f"  {line}")

if __name__ == "__main__":
    main()
