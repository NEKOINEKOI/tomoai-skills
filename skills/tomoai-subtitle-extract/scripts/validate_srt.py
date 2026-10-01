import os, re, sys

base = os.path.dirname(os.path.abspath(__file__))
# 校验目标目录可通过命令行第二个参数传入；不传则默认当前目录
video_dir = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
name = sys.argv[1] if len(sys.argv) > 1 else ""

paths = [os.path.join(video_dir, name), os.path.join(base, name)]

ts_re = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})")

def to_ms(h, m, s, ms):
    return ((h * 60 + m) * 60 + s) * 1000 + ms

for p in paths:
    raw = open(p, "rb").read()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    blocks = [b.strip() for b in text.strip().split("\n\n") if b.strip()]

    errors = []
    prev_end = -1
    for i, b in enumerate(blocks, 1):
        lines = b.split("\n")
        if len(lines) < 3:
            errors.append(f"#{i} 块结构异常(行数={len(lines)})")
            continue
        if not lines[0].strip().isdigit():
            errors.append(f"#{i} 序号不是数字: {lines[0]!r}")
        m = ts_re.match(lines[1].strip())
        if not m:
            errors.append(f"#{i} 时间轴格式错: {lines[1]!r}")
            continue
        s = to_ms(*map(int, m.groups()[:4]))
        e = to_ms(*map(int, m.groups()[4:]))
        if e <= s:
            errors.append(f"#{i} 结束<=开始 ({e-s}ms)")
        if s < prev_end - 1:
            errors.append(f"#{i} 与上一段重叠 (prev_end={prev_end} this_start={s})")
        prev_end = e
        # 中文字数检查（每行）
        for ln in lines[2:]:
            cn = len(re.findall(r"[一-鿿]", ln))
            if cn > 22:
                errors.append(f"#{i} 单行汉字数偏多({cn}): {ln}")

    # 确保 UTF-8 BOM（Windows 播放器中文不乱码）
    if not has_bom:
        open(p, "w", encoding="utf-8-sig").write(text)
        bom_msg = "已补 UTF-8 BOM"
    else:
        bom_msg = "已有 BOM"

    print(f"文件: {p}")
    print(f"  块数: {len(blocks)} | BOM: {bom_msg}")
    print(f"  问题: {errors if errors else '无'}")
    print()
