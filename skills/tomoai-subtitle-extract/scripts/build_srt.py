# -*- coding: utf-8 -*-
"""由 segments.json + 中文改写稿（| 分隔成品字幕条）生成 zh / en / zh-en 三份 srt。

时间轴对齐（2026-10-01 重写，解决"中文比语音快/慢"的问题）：
  1. 段边界用 words[0].start / words[-1].end，而不是 seg.start / seg.end
     —— whisper 的段边界常含前后静音，这是"字幕早于语音出现"的主因
  2. 段内多条按【英文词序列】定位，而不是按时间平均分
     —— 英文说得快的地方中文也该快，有停顿的地方中文不该硬摊，这是"对不上"的主因
  3. 读速约束：中文挂太久（< MIN_CPS 字/秒）就提前收；太挤（> MAX_CPS）则报警提示改短中文
  4. 绝不侵入下一段（hard_end 优先于一切时长规则）

用法:
  python build_srt.py segments.json zh_translations.txt <输出目录> <文件名基名>
"""
import json, sys, os, re

MAX_DUR = 4.8        # 单条最长
MIN_DUR = 0.5        # 单条最短（保底，避免一闪而过）
MIN_CPS = 2.4        # 读速下限（字/秒）：低于此说明中文挂在静音上，提前收
MAX_CPS = 6.5        # 读速上限：高于此观众读不完
READ_CPS = 4.0       # 提前收时用的目标读速
BORROW_CPS = 5.0     # 读不完时向后借静音区，按这个读速补时
ALPHA = 0.65         # 词级对齐权重（其余用时间均分兜底，抑制词时间戳噪声）
TAIL_STRIP = "，,、；;：:。.！!？?…—-~ "


def han_len(s):
    return sum(2 if ord(c) > 127 else 1 for c in s)


def n_chars(s):
    """折算成'字数'：汉字算 1，英数串按宽度折算"""
    return han_len(s) / 2.0


def strip_tail(s):
    return s.rstrip(TAIL_STRIP).strip()


def fmt(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return "%02d:%02d:%02d,%03d" % (h, m, int(s), round((s - int(s)) * 1000))


def write_srt(path, blocks):
    with open(path, "w", encoding="utf-8-sig") as f:
        for i, (st, en, txt) in enumerate(blocks, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (i, fmt(st), fmt(en), txt))


def word_bounds(seg, ratios):
    """按累计比例在【英文词序列】上取时间点。

    ratios: 各条中文的累计比例（不含最后一条），长度 = 条数-1
    返回 (段首, 段尾, 切点列表) 或 None（无词级数据时退回时间均分）
    """
    words = [w for w in (seg.get("words") or [])
             if isinstance(w.get("start"), (int, float))
             and isinstance(w.get("end"), (int, float))
             and w["end"] > w["start"]]
    if not words:
        return None
    wts = [max(len(w["word"].strip()), 1) for w in words]  # 长词 = 信息量大
    tot = sum(wts)
    cuts = []
    for r in ratios:
        target = r * tot
        cum = 0.0
        pos = words[-1]["end"]
        for w, wt in zip(words, wts):
            if cum + wt >= target:
                frac = (target - cum) / wt
                pos = w["start"] + frac * (w["end"] - w["start"])
                break
            cum += wt
        cuts.append(pos)
    return words[0]["start"], words[-1]["end"], cuts


def seg_speech_range(seg):
    """段的真实语音区间（去掉首尾静音）"""
    words = [w for w in (seg.get("words") or [])
             if isinstance(w.get("start"), (int, float)) and isinstance(w.get("end"), (int, float))]
    if words:
        return words[0]["start"], max(w["end"] for w in words)
    return seg["start"], seg["end"]


def main():
    seg_path, zh_path, outdir, base = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    d = json.load(open(seg_path, encoding="utf-8"))
    segs = d["segments"]
    raw = [l.strip() for l in open(zh_path, encoding="utf-8").read().splitlines() if l.strip()]
    assert len(raw) == len(segs), "改写稿行数 %d != 段数 %d" % (len(raw), len(segs))

    blocks_zh, blocks_en, blocks_bi = [], [], []
    issues = []

    for idx, (seg, line) in enumerate(zip(segs, raw)):
        lines = [strip_tail(x) for x in line.split("|")]
        lines = [x for x in lines if x] or [strip_tail(line)]

        # 下一段的真实语音起点 → 本段的硬上限
        if idx + 1 < len(segs):
            hard_end = seg_speech_range(segs[idx + 1])[0] - 0.05
        else:
            hard_end = seg["end"] + 5

        # 本段真实语音区间（去掉 whisper 段边界里的首尾静音）
        st, en = seg_speech_range(seg)
        st = max(st, seg["start"] - 0.15)   # 允许极小的前置，别切太死
        en = min(en, hard_end)

        widths = [han_len(l) for l in lines]
        total = sum(widths) or 1
        acc, ratios = 0, []
        for w in widths[:-1]:
            acc += w
            ratios.append(acc / total)

        # 段内切点：词级对齐 + 时间均分 混合（抑制词时间戳在快语速段的噪声）
        span = en - st
        flat = [st + span * r for r in ratios]
        wa = word_bounds(seg, ratios)
        if wa:
            w_st, w_en, cuts = wa
            st = max(min(w_st, st + 0.1), seg["start"] - 0.15)
            en = min(w_en, hard_end)
            cuts = [ALPHA * c + (1 - ALPHA) * f for c, f in zip(cuts, flat)]
        else:
            cuts = flat

        # 先算出每条的原始窗口
        raw_blocks = []
        for li, ln in enumerate(lines):
            a = st if li == 0 else cuts[li - 1]
            b = en if li == len(lines) - 1 else cuts[li]
            raw_blocks.append([a, b, ln])

        # 反向收紧：任何一条都不得越过下一条的起点
        for li in range(len(raw_blocks) - 2, -1, -1):
            raw_blocks[li][1] = min(raw_blocks[li][1], raw_blocks[li + 1][0] - 0.02)

        for li, (a, b, ln) in enumerate(raw_blocks):
            nc = n_chars(ln)
            # 硬约束：不超过单条上限，不侵入下一段
            b = min(b, a + MAX_DUR, hard_end)

            # 读不完（中文比语音长）→ 向后借静音区补时，但不得碰到下一条
            need = nc / BORROW_CPS + 0.3
            if nc / max(b - a, 0.001) > MAX_CPS and need > b - a:
                room = raw_blocks[li + 1][0] - 0.02 if li + 1 < len(raw_blocks) else hard_end
                b = min(a + need, room)
                b = max(b, a + MIN_DUR)

            # 读速过慢（中文挂在静音上）→ 提前收
            dur = b - a
            if dur > 0.2 and nc / dur < MIN_CPS:
                b = min(b, a + nc / READ_CPS + 0.5)

            # 过短保底
            if b - a < MIN_DUR:
                b = min(a + MIN_DUR, hard_end)
            if b <= a:
                b = min(a + 0.2, hard_end)

            dur = max(b - a, 0.001)
            rate = nc / dur
            # 短条一眼能扫完，不算问题；只有"字多 + 读不完"才需要改短
            too_fast = (nc >= 8 and rate > MAX_CPS) or (nc >= 12 and rate > 6.0)
            if too_fast:
                issues.append(("挤 %.1f字/秒 语音%.1fs 建议缩到%d字"
                               % (rate, dur, int(dur * 5.0)), round(a, 2), ln))
            elif rate < 1.6 and nc >= 4:
                issues.append(("拖 %.1f字/秒 中文太短，可再加点内容" % rate, round(a, 2), ln))

            blocks_zh.append((a, b, ln))
            entxt = re.sub(r"\s+", " ", seg["text"].strip())[:90].rstrip(" ,.")
            blocks_bi.append((a, b, (entxt + "\n" + ln) if li == 0 else ln))

        blocks_en.append((st, max(en, st + MIN_DUR),
                          re.sub(r"\s+", " ", seg["text"].strip())))

    os.makedirs(outdir, exist_ok=True)
    pz = os.path.join(outdir, base + ".zh.srt")
    pe = os.path.join(outdir, base + ".en.srt")
    pb = os.path.join(outdir, base + ".zh-en.srt")
    write_srt(pz, blocks_zh)
    write_srt(pe, blocks_en)
    write_srt(pb, blocks_bi)

    print("zh blocks", len(blocks_zh), "| en", len(blocks_en))
    print("max width", max(han_len(t) for _, _, t in blocks_zh))
    over = [(a, b, t) for a, b, t in blocks_zh if b - a > MAX_DUR + 0.01]
    print("bad dur", over)
    lap = [(blocks_zh[i - 1], blocks_zh[i]) for i in range(1, len(blocks_zh))
           if blocks_zh[i][0] < blocks_zh[i - 1][1] - 0.001]
    print("overlap", lap)
    if issues:
        print("--- 读速异常 %d 条（挤=中文太长读不完，拖=中文太短挂太久）---" % len(issues))
        for tag, t, txt in issues[:25]:
            print("  [%s] %.2fs  %s" % (tag, t, txt))
    print(pz); print(pe); print(pb)


if __name__ == "__main__":
    main()
