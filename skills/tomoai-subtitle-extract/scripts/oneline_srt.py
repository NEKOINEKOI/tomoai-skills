# -*- coding: utf-8 -*-
"""把中文 srt 重排为「单行」字幕。

长句按标点/虚词拆成多条（每条一行），时间按字数比例分配。
绝不在英文单词或中文词中间切（"垃圾信息" 不会被切成 "全是垃/圾信息"）。

用法:
  python oneline_srt.py input.srt output.srt [maxlen=18]
  python oneline_srt.py input.srt output.srt 18 --en en.srt --bi out.zh-en.srt

要点:
  - maxlen 按字符数计；中文一行 18 字左右最舒服，14-16 更短但更碎
  - 输出 utf-8-sig（BOM）
  - 会自动补中英文之间的空格（"Instagram和Threads" -> "Instagram 和 Threads"）
"""
import re, sys

ATOM_PUNC = "，。、；：？！,.;:?!"
SAFE = set("，。、；：？！—…,.;:?!" + " " + "）()（）[]【】")
SAFE_WORDS = ["的", "了", "和", "与", "或", "在", "是", "就", "也", "还", "把", "被", "给",
              "用", "让", "对", "从", "到", "能", "会", "要", "有", "跟", "而", "但", "然后",
              "因为", "所以", "比如", "包括", "另外", "可以", "已经", "还是", "我们", "他们",
              "你们", "以及", "并且", "而且", "如果", "这样", "那样", "这个", "那个", "什么",
              "怎么", "自己", "现在", "之后", "之前", "里面", "上面", "其中", "其实", "个",
              "些", "这", "那", "你", "我", "他", "它"]
DICT = {"FacebookMessenger": "Facebook Messenger", "MagicTheater": "Magic Theater",
        "ChowMin": "Chow Min", "iPhone13Pro": "iPhone 13 Pro", "iPhone13": "iPhone 13",
        "AppStore": "App Store", "BestBuy": "Best Buy", "StateFarm": "State Farm",
        "GoldenGate": "Golden Gate", "RedPanda": "Red Panda"}
MIN_DUR = 0.75


def parse_srt(path):
    out = []
    for b in open(path, encoding="utf-8-sig").read().strip().split("\n\n"):
        lines = [l for l in b.split("\n") if l.strip()]
        m = re.match(r"(\d\d):(\d\d):(\d\d),(\d\d\d)\s*-->\s*(\d\d):(\d\d):(\d\d),(\d\d\d)", lines[1])
        h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, m.groups())
        out.append([h1*3600+m1*60+s1+ms1/1000, h2*3600+m2*60+s2+ms2/1000, "".join(lines[2:])])
    return out

def ts(t):
    h = int(t//3600); m = int((t % 3600)//60); s = int(t % 60)
    ms = int(round((t - int(t))*1000))
    if ms == 1000: s += 1; ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def fix_spacing(s):
    for k, v in DICT.items():
        s = s.replace(k, v)
    s = re.sub(r"([A-Za-z0-9%\.\)])([\u4e00-\u9fff])", r"\1 \2", s)
    s = re.sub(r"([\u4e00-\u9fff])([A-Za-z0-9])", r"\1 \2", s)
    return re.sub(r" {2,}", " ", s).strip()

def is_en(c):
    return c.isascii() and c.isalpha()

def breakable(s, i):
    """注意：中文字符 isalpha() 也是 True，必须限定 ASCII，否则所有切点都被否掉。"""
    if i <= 0 or i >= len(s): return False
    if is_en(s[i-1]) or is_en(s[i]): return False
    if s[i-1] in SAFE: return True
    if s[i-1] in SAFE_WORDS: return True
    return False

def hard_split(s, n):
    out = []
    while len(s) > n:
        cut = None
        for i in range(n, max(3, n - 12), -1):
            if breakable(s, i): cut = i; break
        if cut is None:
            for i in range(n + 1, min(len(s), n + 12)):
                if breakable(s, i): cut = i; break
        if cut is None:
            out.append(s); s = ""; break      # 宁可整行稍长，也不切坏词
        out.append(s[:cut].strip()); s = s[cut:].strip()
    if s: out.append(s)
    return out

def split_line(text, maxlen):
    if len(text) <= maxlen: return [text]
    atoms = [a for a in re.findall(r"[^%s]*[%s]|[^%s]+" % (ATOM_PUNC, ATOM_PUNC, ATOM_PUNC), text) if a.strip()]
    pieces, buf = [], ""
    for a in atoms:
        if len(a) > maxlen:
            if buf: pieces.append(buf); buf = ""
            pieces.extend(hard_split(a, maxlen)); continue
        if buf and len(buf) + len(a) > maxlen:
            pieces.append(buf); buf = a
        else:
            buf += a
    if buf: pieces.append(buf)
    merged = []
    for p in pieces:
        if merged and len(p) <= 5 and not p.startswith("好"):
            merged[-1] += p
        else:
            merged.append(p)
    return [p for p in merged if p.strip()]

# 行尾标点：字幕每行结尾不留标点（TOMOAI 要求，像字幕不像句子）
TAIL_PUNCS = "，。、；：？！—…,.;:?!"

def strip_tail(text):
    return text.rstrip(TAIL_PUNCS).rstrip()

def allocate(start, end, pieces):
    w = [max(1, len(p)) for p in pieces]
    total, span, cum = sum(w), end - start, 0.0
    times = []
    for x in w:
        s = start + span*cum/total; cum += x
        times.append([s, start + span*cum/total])
    for _ in range(2):
        for i in range(len(times) - 1):
            if times[i][1] - times[i][0] < MIN_DUR:
                times[i][1] = min(times[i][0] + MIN_DUR, times[i+1][1] - 0.03)
        for i in range(1, len(times)):
            times[i][0] = max(times[i][0], times[i-1][1])
    times[-1][1] = max(times[-1][1], end)
    return times

def build(cues, maxlen):
    rows = []
    for st, end, text in cues:
        text = fix_spacing(text)
        if not text.strip(): continue
        for (s, e), p in zip(allocate(st, end, split_line(text, maxlen)),
                             split_line(text, maxlen)):
            rows.append([s, e, strip_tail(p)])
    i = 0
    while i < len(rows) - 1:                      # 消灭一闪而过的条目
        if rows[i][1] - rows[i][0] < 0.5:
            rows[i+1][0] = rows[i][0]
            rows[i+1][2] = rows[i][2] + rows[i+1][2]
            del rows[i]
        else:
            i += 1
    return rows

def write(path, rows, mode="zh", en=None):
    def en_at(t):
        for e in en or []:
            if e[0] <= t < e[1]: return e[2]
        for e in en or []:
            if abs((e[0]+e[1])/2 - t) < 6: return e[2]
        return ""
    buf = []
    for i, r in enumerate(rows, 1):
        body = r[2] if mode == "zh" else ((en_at((r[0]+r[1])/2) + "\n" + r[2]) if en_at((r[0]+r[1])/2) else r[2])
        buf.append(f"{i}\n{ts(r[0])} --> {ts(r[1])}\n{body}\n")
    open(path, "w", encoding="utf-8-sig").write("\n".join(buf))
    print(path, len(rows), "cues | 平均", round(sum(len(r[2]) for r in rows)/len(rows), 1),
          "| 最长", max(len(r[2]) for r in rows), "| 两行条数", sum(1 for r in rows if "\n" in r[2]))

def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]
    maxlen = int(sys.argv[3]) if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else 18
    en = parse_srt(sys.argv[sys.argv.index("--en") + 1]) if "--en" in sys.argv else None
    bi = sys.argv[sys.argv.index("--bi") + 1] if "--bi" in sys.argv else None

    rows = build(parse_srt(src), maxlen)
    write(dst, rows, "zh")
    if bi:
        write(bi, rows, "both", en)

if __name__ == "__main__":
    main()
