---
name: tomoai-subtitle-extract
description: 视频字幕提取与生成 skill。输入视频文件，自动提取音频、ASR 转写（faster-whisper large-v3）、生成英文/中文字幕 srt，中文字幕走「中国本地化改写」（不直译，把英文表达换成中国人真正会说的说法），支持手工断行与双语/纯中文三份输出。适用于任何需要处理视频字幕的场景。
agent_created: true
---

# tomoai-subtitle-extract — 视频字幕提取与本地化改写

将视频转换为带时间戳的中文 srt 字幕文件。
中文字幕不是"翻译"，是**本地化改写**——把英文表达换成中国人真正会说的中文（详见 Step 3）。

## 适用场景

- 用户要求给视频加字幕/提取字幕
- 用户说"做个 srt"、"字幕提取"、"翻译字幕"、"字幕翻成中文"
- 任何需要从视频音频中提取文字的 task

## 工作流程

### Step 1: 探测视频 + 提取音频

```bash
VIDEO="视频路径"
OUTPUT_DIR="./subtitle_output"
mkdir -p "$OUTPUT_DIR"

# 检查视频信息
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1 "$VIDEO"

# 提取完整音频（避免旧脚本截断问题）
ffmpeg -y -i "$VIDEO" -vn -acodec pcm_s16le -ar 16000 -ac 1 "$OUTPUT_DIR/audio.wav"
```

**注意**：必须确认音频时长与视频一致，否则时间轴会错位。

### Step 2: ASR 语音识别

**优先走 GPU**（2026-09-28 实测可用，比 CPU 快一个数量级）：

```bash
# 解释器用预装 faster-whisper 1.2.1 + ctranslate2 4.8.2 的 venv
PY="python"  # 换成你机器上有 faster-whisper 的 python

# 关键 1：把 torch 的 lib 加进 PATH，cublas64_12.dll 在里面
export PATH="/path/to/your/python/site-packages/torch/lib:$PATH"
# 关键 2：离线模式，别让它去联网查模型
HF_HUB_OFFLINE=1 "$PY" scripts/transcribe_gpu.py "$OUTPUT_DIR/audio.wav"
```

无 GPU 或 cublas 仍报错时，退回 CPU：

```bash
python scripts/transcribe_cpu.py "$OUTPUT_DIR/audio.wav"
```

输出：
- `original.srt` - 英文原文（带时间戳）
- `segments.json` - 结构化数据（start/end/text）

**已知坑点（2026-09-28 更新）**：
- `RuntimeError: Library cublas64_12.dll is not found` —— 机器上没装 CUDA Toolkit，但 **PyTorch 自带这份 DLL**。
  把 `<python3.13>/Lib/site-packages/torch/lib` 加进 PATH 即可跑 GPU fp16（实测 17 分钟音频 ≈ 5.5 分钟跑完）。
  不要因为这条报错就退回 CPU。
- 模型名别写 `"large-v3"` 别名，faster-whisper 会去 HuggingFace 联网校验，代理环境下直接 502。
  **直接传本地快照绝对路径**：
  `~/.cache/huggingface/hub/models--Systran--faster-whisper-large-v3/snapshots/<commit-hash>`
  （turbo 版：`models--mobiuslabsgmbh--faster-whisper-large-v3-turbo/snapshots/<commit-hash>`）。
  首次使用先 `huggingface-cli download Systran/faster-whisper-large-v3` 拉到本地
- 模型已缓存在 `~/.cache/huggingface/hub/`，无需重复下载；始终带 `HF_HUB_OFFLINE=1`
- 转写参数推荐：`vad_filter=True` + `condition_on_previous_text=False`（避免幻觉复读）

**时间轴对齐（2026-09-29 新增，重要）**：
- **痛点**：whisper 段（segment）常把 2-3 句话并成一段（最长 6-7s、中间带停顿）。只按段 start/end 给中文分配时间，字幕会在静音停顿处还挂着，观感就是"英文说完了中文还停着"。
- **正解**：转写时开 `word_timestamps=True`，拿到词级时间戳：
  ```python
  segments, info = model.transcribe(audio, beam_size=5, vad_filter=True,
      condition_on_previous_text=False, word_timestamps=True)
  ```
  每段内 `seg.words` 是 `[{start,end,word}]`。
- **重建时间轴**：把每段按词间静音 > 0.3s 切成子块（口语连读时静音阈值不可靠，可再按字数比例把块内多条中文摊开），保证：
  - 每条中文的起止落在对应英文语音块内
  - 段内中文按字数比例铺满段长，不重叠
  - 单条 ≤ 4.8s（过长宁提前收，不可拖后）；字少（≤15 字）却时长 >4.2s 的条压缩到约 字数/3.2+0.9s
  - 最短 0.5s（太短会闪）
- **双语版同时间轴**：zh-en.srt 每块两行 = 英文段原文 + 对应中文，英文行取自段 text（截断到 90 字符），中英文用同一时间窗，避免"中英错位"。
- 校验：无重叠/负时长、单条 ≤4.8s、行尾无标点（中文行不做句子）、行内无「。」和「——」。

### Step 3: 中国本地化改写 + 断行（本 skill 的核心，别当普通翻译做）

**改写稿格式**（一行 = 一个 whisper 段，`|` 分隔成品字幕条，无句号）：

```
嘿，我是你的 Dot|刚进 ChatGPT
以后你手上的事都交给我
...
```

**生成命令**（用 Step 3.6 的 `build_srt.py`，一次出三份）：

```bash
python scripts/build_srt.py segments.json zh_translations.txt <输出目录> <基名>
```

（`gen_zh_srt.py` / `oneline_srt.py` 是旧版自动断行脚本，有切坏词风险，仅作兜底）

**中国本地化改写（2026-09-30 TOMOAI 实战要求，最高优先级）**：

翻的不是句子，是"这个场景里中国人会怎么说话"。直译的结果永远是"外国人讲的中国话"，
观众一眼就能看出来。目标：看字幕的人觉得说话的人本来就在讲中文。

**三条总纲**：
1. **先想场景，再想措辞** —— 这句话在中文里是什么场合、对谁说的？职场汇报、跟老婆聊天、
   跟观众吐槽，说法完全不同
2. **意思对等 > 形式对等** —— 宁可整个换说法，也别硬搬英文的句法结构
3. **字幕是听的，不是读的** —— 一口气念不顺的，就是没改到位

**九条硬规则**（完整对照表见 `references/localization-playbook.md`，拿不准就去查）：

1. **填充词整句跳过**：you know / I mean / like / literally / basically / right? / so / well 一律删。
   只留真正推进内容的路标（Okay so → 好，But first → 不过先说，Now → 那么）
2. **情绪词换中国人真会喊的**：awesome → 绝了、太猛了；that's insane → 离谱；no way → 不是吧；
   killer feature → 杀手锏、最狠的一点；it's a no-brainer → 闭眼入。
   别堆"非常/极其/十分"，用"挺/特别/真/太"
3. **习语换中文同类习语，绝不直译**：a piece of cake → 小菜一碟；move the needle → 真有用；
   circle back → 回头再说；on the same page → 对得上；low-hanging fruit → 最好摘的果子
4. **职场黑话翻成人话**：leverage → 用、借；bandwidth → 精力；deliverable → 要交的活；
   stakeholder → 相关人；touch base → 对一下；audit → 查一遍、盘一遍；use case → 场景
5. **量词口语化**：a/an/one 往往不是数数，中文说"放个鸡蛋"不说"放一个鸡蛋"，说"看个例子"不说"看一个例子"。
   除非明确在强调数量（"两个""三个""第一名"），否则一律用"个/点/下"化掉
6. **单位换算成有体感的**：°F → 摄氏度，miles → 公里，5'11" → 一米八，five-figure → 五位数，
   $99 → 99 美元。观众读到这个数字脑里没画面，就换算
7. **美国文化专有项补一次定位**：Super Bowl → 美国橄榄球总决赛；call US businesses → 打电话给美国商家；
   Facebook Marketplace → Facebook 上的二手交易平台。补一次就够，别每次都解释
8. **产品技术名留英文，类别词中文化**：ChatGPT、Slack、App Store、PRD、Substack 保留原名；
   但 thread → 会话，prompt → 提示词，landing page → 落地页，browser use → 浏览器操作
9. **拆掉英文句法骨架**：从句拆成短句、被动改主动、it is 开头直接说动词、There is 能删就删、
   多重"的"必须拆。`It has a remote cloud computer that runs 24-7` → `它有一台云电脑，24 小时在线`
   （不是"它有一个全天候运行的远程云电脑"）

**翻译腔红线**（出现即改）：

| 翻译腔 | 改成 |
|---|---|
| 让我们… | 咱们…、或直接动词 |
| 这是一个… | 去掉判断句，直接说 |
| 在这种情况下 | 这时候 |
| 事实上 / 实际上 | 删，或"说白了" |
| 有趣的是 / 值得一提的是 | 删 |
| 进行了一次分析 | 分析了一遍 |
| 做出了贡献 / 给予了帮助 | 帮了忙 |
| 被广泛应用于 | 到处都在用 |
| 非常 / 极其 / 十分 堆砌 | 挺 / 特别 / 真 / 太 |

**工作流程**：
- **先通读全文再动笔**：连着看十几段，搞清楚说话人是谁、在跟谁说话、情绪到哪儿了，再逐段改写。
  孤立地一句一句翻，必然翻出"外国人讲的中国话"
- 改完每条自查 5 问（playbook 第 11 节）：中国人会这么开口吗 / 有没有更短的说法 /
  有没有英文句法影子 / 专名和单位对不对 / 一口气念得顺吗。有一条不过就重写，别凑合

**字幕排版硬规则（沿用不变）**：
- **严禁破折号（—— / —）**：口语化改写掉，别靠标点转折
  - `当然还有——帮我砍掉所有账单` → `当然还有，帮我砍掉所有账单`
  - `Muse 真正的杀手级功能——其他 AI 会抄` → `Muse 真正的杀手级功能，其他 AI 会抄`
- **严禁句号。**（行中、行尾都不行）：一个语流结束就换一条字幕，句间一律用逗号
  - `然后去查我的账户。它发现` → `然后去查我的账户，它发现`
- 行尾不留任何标点（见 Step 3.5），引号/书名号尽量少用

**断句美学（TOMOAI 定稿，2026-09-29）**：
- 断句位置要**讲究**：断在**自然停顿处**，让观众扫一眼就懂；不要把语义拆悬空
- **一行字幕只负责一个完整语流**——讲完一层意思就换一条字幕，不让一条字幕"藏两句"
- **句子之间只用逗号连接**（语流是"，，，"延续的，不是被"。"打断的）；想在某个意思收尾时，就**在这里切条新字幕**，而不是留一个"。"在行里
- 一句话尽量连续，长句才拆；拆的每一段都要自洽（主语/宾语不悬空）
- **反面教材（禁止）**：
  - `跟 Comcast 有线电视的 / 真人客服砍价的` ← "的" 悬空
  - `找二手的 / 单支高尔夫球杆` ← 断在 "二手"，语义悬空
  - `我让 Muse 给 / Meta 团队发消息` ← 断在"给"
  - `把特斯拉的 / 保险降下来` ← 介词悬空
  - 宁可一行 20 字完整，也不要断成半句

### Step 3.5: 强制单行（TOMOAI 明确要求：不要两行字幕）

翻译完的字幕常常超长，被播放器自动折成两行，放进字幕框很难看。用 `oneline_srt.py` 重排：

```bash
python scripts/oneline_srt.py 中文.srt 输出.srt 18 --en 英文.srt --bi 双语.srt
```

做法：长句按标点/虚词拆成**多条**字幕（不是折成两行），时间按各条字数比例分配。

**关键经验**：
- 判断"能不能在这里断"时，中文字符 `isalpha()` 也是 True —— 必须限定 `c.isascii() and c.isalpha()`，
  否则所有中文切点都被当成英文单词而否掉，结果整句切不动，冒出 20+ 字长行。
- 切点优先级：标点 → 空格 → 虚词/代词（的、了、和、就、我们…）→ 全角括号。**找不到切点就整行保留**，
  宁可稍长也绝不切坏词（"垃圾信息" 切成 "全是垃 / 圾信息" 是事故）。
- **断句讲究**：不要断成悬空半句（见 Step 3"断句美学"）。宁可单行 20 字完整，也不要 `跟 Comcast 有线电视的 / 真人客服砍价的` 这种"的"字悬空的残句。能整句就不拆。
- ≤5 字的残片一律并入上一条（"的账单。""美元左右。" 单独蹦一行很丑）；语气词"好，"除外。
- **行尾一律不留标点**（TOMOAI 实战要求：像字幕不像句子）。逗号/句号/顿号/问号/感叹号/破折号等全部剥掉（`strip_tail`），行内标点保留；英文行（"Messenger。"→"Messenger"）同样适用。
- **破折号 0 容忍**：翻译阶段就禁用破折号（口语化改写掉），排版阶段 `strip_tail` 会连带剥掉行尾的。
  双语版英文原文有时带 `——`，中文行才会处理，处理映射写在拆解脚本里（手写逐条替换，别用通用删除，容易留下别扭空隙）。
- 切分过程会把中英之间的空格 strip 掉，输出前统一 `fix_spacing` 补回，
  并用小词典修 "FacebookMessenger" 这类被吃掉的英文词间空格。
- 参数：18 字/行是甜点值（平均会落在 13 字左右）；要更短给 14-16，但会更碎。

### Step 3.6: 手工断句模式（2026-09-30 起推荐，默认走这条）

自动切分（`oneline_srt.py`）会切出 `我正在更 / 新你董事会用的，deck`、`每条流程对，一遍` 这种**断在词中间**的事故。
原因：切点字典里的"更/对/给/把/这/个"等字常常是合成词的一部分（更新、对调、给团队）。

**正解：翻译阶段就用 `|` 把每行断成成品字幕条，脚本只做时间分配，不再自动切。**

```bash
python scripts/build_srt.py segments.json zh_translations.txt <输出目录> <文件名基名>
```

- 翻译文件：**一行 = 一个 whisper 段**，`|` 分隔该段内的字幕条
**时间轴对齐（2026-10-01 重写，专治"中文比语音快/慢"）**：

旧做法是"段内按字数比例摊开"，等于假设语音匀速 —— 英文说得快的地方中文就落后，
有停顿的地方中文就干等，于是出现"字幕早于语音出现 / 语音说完字幕还挂着"。现在改成三层：

1. **段边界用真实语音区间**：取 `words[0].start` / `words[-1].end`，而不是 `seg.start` / `seg.end`。
   whisper 的段边界常含前后静音，这是"字幕提前出现"的主因
2. **段内按英文词序列定位**：把中文条按字数比例映射到英文词序列（按词字符数累计）上的位置，
   取该词的真实时间戳。英文说得快的地方中文跟着快，有停顿的地方不硬摊。
   为抑制词时间戳在快语速段的噪声，用 `ALPHA=0.65` 与时间均分混合
3. **读速约束**：中文挂太久（< 2.4 字/秒）提前收；读不完时向后借静音区补时（不得碰到下一条）

**读速诊断（生成后必看）**：脚本会打印异常清单，例如

```
[挤 6.8字/秒 语音1.8s 建议缩到8字] 5.37s  我这几天拿它跑自己的生意
```

意思是这条中文比这段语音能承载的长，**按建议字数改短**再重跑，直到清单为空或只剩边缘值
（6-7 字/秒的短条可接受）。短条（<8 字）不报警，观众一眼能扫完。
实测：18 分钟长片首轮 23 条"挤"，按建议改完降到 4 条边缘值；148 秒短片 6 条降到 1 条。

**前提**：转写必须开 `word_timestamps=True`（`transcribe_gpu.py` 已默认开）。
没有 words 数据时脚本退回时间均分（效果打折），建议重跑转写。
- 行尾标点自动剥掉，UTF-8 BOM
- 一次出三份：`.zh.srt`（纯中文）/ `.en.srt`（英文原文）/ `.zh-en.srt`（双语，英文在上中文在下）
- 脚本自带自检输出：`max width`（应 ≤ 36 宽 ≈ 18 汉字）、`bad dur`、`overlap`（都应为空）

**断句纪律**：≤5 字的短条会闪，能整句就别拆（如"随时待命|你说开始我就上"合成一条更稳）；
长段最多拆 2-3 条；每条必须是自洽语流，禁止"的/把/给"悬空。
**宽度自检**：脚本会打印 `max width`，目标 ≤36（约 18 汉字）。超 38 的行要改——
通常是英文专名把宽度撑起来了，把专名挪走或断成两条（"过去四五个月我一直把 ChatGPT 当主力工具" 43 宽 →
改写成"这四五个月我都把 ChatGPT 当主力工具" 33 宽）。

**长视频经验（2026-09-30，18 分钟 / 221 段实测）**：
- GPU 转写 18 分钟音频约 5 分 40 秒，用 `run_in_background` 跑，别在前台等
- 221 段的翻译稿要一次写完再生成，段数必须严格对齐（脚本会 assert）；
  写完先跑一次，看 `max width` / `bad dur` / `overlap` 三项再修，比逐条肉眼复查快
- 长视频里常出现 0.2-0.8 秒的语气片段（"All right." "right?"），中文就翻成"好""到底行不行"，
  不要为了凑长度硬编内容

### Step 4: 校验输出

```bash
python scripts/validate_srt.py output.srt
```

检查项：
- 块数正确
- UTF-8 BOM 存在
- 时间轴无重叠/负时长
- 单行汉字数 ≤ 22

## 文件结构

```
skill/
├── SKILL.md
├── scripts/
│   ├── transcribe_gpu.py      # ASR 转写（GPU fp16，首选）
│   ├── transcribe_cpu.py      # ASR 转写（CPU int8 兜底）
│   ├── gen_zh_srt.py          # 中文翻译 + 断行
│   ├── oneline_srt.py         # 强制单行重排（长句拆多条，不折两行；有切坏词风险）
│   ├── build_srt.py           # 手工断句版：翻译用 | 断条，一次出 zh/en/zh-en 三份（推荐）
│   └── validate_srt.py        # 输出校验
├── references/
│   └── localization-playbook.md  # 中文本地化对照手册（Step 3 必读，11 类对照表）
└── examples/
    ├── segments.json          # 输入示例
    └── zh_translations.txt    # 翻译示例
```

## 参数说明

### transcribe_cpu.py
- `audio`: 音频文件路径（wav, 16kHz mono）
- `model_size` (optional): 模型大小，默认 `large-v3`，可选 `small`/`base`

### gen_zh_srt.py
- `segments.json`: ASR 输出
- `zh_translations.txt`: 中文翻译，每行一段
- `--output`: 输出路径，默认同目录

### validate_srt.py
- `srt_file`: 要校验的 srt 文件
- 可重复运行，自动补 BOM

## 快速开始（2026-09-30 定稿流程）

```bash
# 1) 提取音频，核对时长与视频一致
ffmpeg -y -i "$VIDEO" -vn -acodec pcm_s16le -ar 16000 -ac 1 audio.wav

# 2) GPU 转写（长视频用 run_in_background 跑）
export PATH="/path/to/your/python/site-packages/torch/lib:$PATH"
HF_HUB_OFFLINE=1 "$PY" scripts/transcribe_gpu.py audio.wav segments.json

# 3) 通读 segments.json 做本地化改写，写 zh_translations.txt（一行一段，| 断条）

# 4) 生成 + 自检
python scripts/build_srt.py segments.json zh_translations.txt <输出目录> <基名>
python scripts/validate_srt.py <输出目录>/<基名>.zh.srt
```

**动手改写前先读 `references/localization-playbook.md`**，里面是本地化的具体说法对照表。

## 注意事项

0. **中文字幕 = 本地化改写，不是翻译**（TOMOAI 2026-09-30 明确）：直译出来的"外国人讲的中国话"观众一眼看穿。
   先通读上下文再逐段改写，对照 `references/localization-playbook.md`，改完自查 5 问
0. **输出编码**：写 srt 用 `encoding="utf-8-sig"`（带 BOM），纯 utf-8 在部分 Windows 播放器乱码
0. **过短字幕**：whisper 会切出 <1s 的碎片（如 "of time."），会一闪而过 → 生成时把时长 <1.0s 的段合并到下一条
0. **同一视频一次出三份**：`<name>.zh.srt`（纯中文）/ `<name>.en.srt`（原文）/ `<name>.zh-en.srt`（双语，英文在上中文在下），用户通常只要中文，另两份顺手给
0. **voicebox ≠ ASR**：voicebox 是 TTS（文字→配音），不能反向做识别
2. **音频截断坑**：旧版 `audio.wav` 可能只有 82s 而视频 146s，务必重新提取
3. **srt 编码**：必须 UTF-8 BOM，否则 Windows 播放器显示乱码
4. **断行原则**：在标点后切，不在词中间切（"授权协议"不能拆成"授权\n协议"）

## 依赖

- ffmpeg（系统自带或独立安装）
- Python 3.10+ with venv
- faster-whisper, ctranslate2, onnxruntime（venv 内预装）
