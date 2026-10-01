<div align="center">

# TOMOAI Skills

#### 自媒体创作者自己每天在用的 AI Skill 合集

[![License](https://img.shields.io/badge/License-MIT-3B82F6?style=for-the-badge)](./LICENSE)
[![Skills](https://img.shields.io/badge/Skills-2-10B981?style=for-the-badge)](#-skills)

![Claude Code](https://img.shields.io/badge/Claude_Code-Skill-D97706?style=flat-square&logo=anthropic&logoColor=white)
![Codex](https://img.shields.io/badge/Codex-Skill-10B981?style=flat-square&logo=openai&logoColor=white)
![WorkBuddy](https://img.shields.io/badge/WorkBuddy-Skill-3B82F6?style=flat-square)
![Cursor](https://img.shields.io/badge/Cursor-Skill-9B59B6?style=flat-square)

</div>

都是自己做了、自己跑了、自己迭代过的东西，不是看完一篇文章随手写的提示词。每一个 skill 都是先用真实业务跑通，再开源出来的。

这里的每个 Skill 都是 Agent 能直接加载的结构化指令集，遵循开放标准。Claude Code、Codex、WorkBuddy、Cursor 等 40+ 支持该标准的 Agent 都能装。

你的 Agent 不支持 Skill 也没关系：把对应目录的 `SKILL.md` 全文下载下来，当成项目规则文件（或直接贴进对话）让 Agent 照着执行，效果一致。

---

## 📋 Skills

| 名字 | 一句话 | 链接 |
|---|---|---|
| ✍️ [**tomoai-aiheadline**](./skills/tomoai-aiheadline) | 微信公众号爆款标题生成器：10 步流水线严格走完，9000+ 条真实爆款对标提炼的两流派模型 | [查看](./skills/tomoai-aiheadline/SKILL.md) |
| 🎬 [**tomoai-subtitle-extract**](./skills/tomoai-subtitle-extract) | 视频字幕提取 + 中文「本地化改写」（不是翻译）：faster-whisper 转写 + 九条改写规则 + 单行字幕排版 | [查看](./skills/tomoai-subtitle-extract/SKILL.md) |

> 后续会陆续加入视频导演、带货视频、AIGC 检测、中文去 AI 味等方向。

---

## 📦 安装方式

### 方式一：在支持 Skills 的 Agent 里直接说

```
帮我安装这个 skill：https://github.com/NEKOINEKOI/tomoai-skills/tree/main/skills/tomoai-aiheadline
```

```
帮我安装这个 skill：https://github.com/NEKOINEKOI/tomoai-skills/tree/main/skills/tomoai-subtitle-extract
```

Agent 会自己 clone 到对应目录，不用你操心路径。

### 方式二：手动复制

下载对应 skill 目录下的 `SKILL.md`（以及它引用的 `references/` 和 `examples/`），放进你 Agent 的 skills 目录即可。

---

## 🌟 关于

我是 TOMOAI，做 AI 自媒体内容，做 AI 工具，也做潮玩品牌 monada。

这些 skill 都是我自己每天在用的。开源出来如果对你有帮助，给个 ⭐ 就行。

---

<div align="center">

MIT License · 自由使用 / 修改 / 再分发

Made by [@NEKOINEKOI](https://github.com/NEKOINEKOI)

</div>
