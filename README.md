# 课代表立正 · 视频内容生产工具 v3

给定一个视频文件，自动完成六步流程，最终产出可用的字幕、文章、高光分析和标题候选。

| 步骤 | 内容 | 输出文件 | 依赖 |
|------|------|---------|------|
| 1. 转录 | Qwen3-ASR 本地转录 | `.qwen.srt` | 本地模型（完全离线） |
| 2. 字幕校对 | LLM 纠错专有名词/语气词 | `.corrected.srt` | Claude / Gemini / OpenAI |
| 3. 断句 | 每条 ≤20 字重新断句 | `.final.srt` | 本地规则（无需 API） |
| 4. 生成文章 | 提炼频道风格文章 | `.article.md` | Claude / Gemini / OpenAI |
| 5. 提取高光 | 识别视频开头高光片段，分析叙事弧 | `.highlights.md` | Claude Code CLI |
| 6. 生成标题 | 三轮 Opus 工作流，高光驱动 | `.titles.md` | Claude Code CLI |

步骤 1-3 完全本地运行，无需任何 API Key。步骤 2/4 支持 Claude、Gemini、OpenAI 任意一家。步骤 5-6 调用 Claude Code CLI（`claude` 命令），需要提前安装并登录。

---

## 使用前提

| 要求 | 说明 |
|------|------|
| **电脑** | Apple Silicon Mac（M1 / M2 / M3 / M4） |
| **Python** | 3.10 或更高版本 |
| **API Key** | Claude / Gemini / OpenAI 任选其一（步骤 2/4 用） |
| **Claude Code CLI** | 步骤 5-6 需要，`which claude` 确认已安装 |

> Windows / Intel Mac 暂不支持（转录模型 mlx-qwen3-asr 只支持 Apple Silicon）。

---

## 一次性安装

```bash
git clone https://github.com/sunyuzheng/kedaibiao-srt-v2.git
cd kedaibiao-srt-v2
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

安装时间约 3-10 分钟，mlx-qwen3-asr 首次安装后第一次运行时还会自动下载模型（约 1.5 GB）。

**配置 API Key**（项目根目录新建 `.env` 文件）：

```
ANTHROPIC_API_KEY=sk-ant-api03-...
```

也支持 OpenAI / Gemini，按需填写：

```
OPENAI_API_KEY=sk-proj-...
GOOGLE_API_KEY=AIzaSy...

# 设置默认校对模型（不填则用 claude-haiku-4-5-20251001）
DEFAULT_CORRECTION_MODEL=gemini-2.0-flash
```

---

## 使用

### 最常用：全链路处理

```bash
venv/bin/python tools/process_video.py /path/to/视频.mp4
```

运行后会询问本期嘉宾名和特有术语（直接回车跳过）。提前告知嘉宾名能大幅提高转录准确率，Qwen 会把「刘嘉」识别成「刘佳」这类同音字，提前注入就能避免。

**推荐做法：直接通过参数传入，不要等交互询问（尤其是在后台跑时）**

```bash
venv/bin/python tools/process_video.py 视频.mp4 --seeds 嘉宾名 "公司名"

# 不需要注入术语时
venv/bin/python tools/process_video.py 视频.mp4 --no-seeds
```

**防止 Mac 休眠（跑长视频时）：**

```bash
caffeinate -i venv/bin/python tools/process_video.py 视频.mp4 --seeds 嘉宾名
```

### 情况 B：已有 SRT，只补高光 + 标题

```bash
# 先提取高光
venv/bin/python tools/generate_highlights.py /path/to/视频名.final.srt

# 再生成标题（自动检测同目录的 .highlights.md）
venv/bin/python tools/generate_titles.py /path/to/视频名.article.md
```

### 情况 C：只需标题（已有 highlights）

```bash
venv/bin/python tools/generate_titles.py /path/to/视频名.article.md
```

---

## 所有参数

| 参数 | 说明 |
|------|------|
| `--seeds 名字 术语` | 注入专有名词，提高 ASR 准确率（多个用空格分隔） |
| `--no-seeds` | 跳过术语输入，直接开始 |
| `--skip-transcribe` | 跳过转录（已有 `.qwen.srt`） |
| `--skip-correct` | 跳过字幕校对 |
| `--skip-article` | 跳过文章生成 |
| `--skip-highlights` | 跳过高光提取（已有 `.highlights.md` 或不需要标题） |
| `--skip-titles` | 跳过标题生成 |
| `--model MODEL` | 指定校对用的 LLM（见下） |
| `--max-chars N` | 每条字幕最大字数（默认 20） |

**`--model` 支持的值：**

```bash
# Claude（Anthropic）
--model claude-haiku-4-5-20251001   # 默认，速度快、成本低
--model claude-sonnet-4-6           # 更准，适合难度高的音频

# Gemini（Google）
--model gemini-2.0-flash
--model gemini-2.5-pro

# OpenAI
--model gpt-4o
--model gpt-4o-mini
```

---

## 输出文件

所有文件生成在**视频同目录**：

| 文件 | 说明 | 用途 |
|------|------|------|
| `视频名.qwen.srt` | Qwen 原始转录，未校对 | 备份 |
| `视频名.corrected.srt` | Claude 校对后字幕 | 备份 |
| `视频名.final.srt` | 最终字幕，≤20字/条 | **导入剪辑软件用这个** |
| `视频名.article.md` | 频道风格文章 | 内容归档；也是标题生成的输入 |
| `视频名.highlights.md` | 高光分析（中心命题+受众+叙事弧） | 标题锚点 |
| `视频名.titles.md` | 最终标题候选 + 封面建议 | **取标题用这个** |
| `视频名_title_ws/` | 标题中间文件（round0/round1） | 调试用，可删 |

---

## 关键设计：高光如何驱动标题

### 高光检测逻辑（`generate_highlights.py`）

`generate_highlights.py` 会先检测 SRT 末尾是否有编辑者手动追加的高光字幕——特征是时间戳重置为 `00:00:xx`（从主内容的 `00:30:xx` 跌回零）。检测到的话，优先用这些亲选片段进行分析，比 AI 盲扫质量高。检测不到时，再用分区采样扫全文。

**手动追加高光的做法**：把高光片段对应的 SRT 字幕行直接复制到 `.final.srt` 文件末尾即可，时间戳保持原视频中的位置不变（都以 `00:00:xx` 开头）。

### 三轮标题工作流（`generate_titles.py`）

| 轮次 | 角色 | 做什么 |
|------|------|--------|
| Round 0 | 资深编辑 | 理解高光 + 内容，发散生成标题候选，角度跟着内容走 |
| Round 1 | 独立评审 | 对比 `data/top_titles.txt`（频道 Top 25 真实高播标题）校准判断，找盲区 |
| Round 2 | 终审编辑 | 按 Round 1 指令补强，选出最终 6-10 个 + 封面建议 |

**标题和高光的分工**：标题不描述高光本身，而是描述高光背后更大的问题。高光让观众感觉「这期有料」，标题创造点击动机，两者不重复。

**封面建议策略**：
- 访谈视频：从嘉宾原话提炼 3 句金句，每句让人看到都想知道来龙去脉；可以轻微 paraphrase 但不夸大
- 单口视频：3-10 字冲击文字，标题做延伸阐释

---

## 时间参考

| 视频时长 | 转录 | 校对 | 断句 | 文章 | 高光 | 标题 | **合计** |
|---------|------|------|------|------|------|------|---------|
| 30 分钟 | 6-10 分钟 | 2-3 分钟 | <1 分钟 | 3-5 分钟 | 3-5 分钟 | 10-15 分钟 | **~25-40 分钟** |
| 60 分钟 | 15-20 分钟 | 4-6 分钟 | <1 分钟 | 4-6 分钟 | 3-5 分钟 | 10-15 分钟 | **~40-55 分钟** |
| 90 分钟 | 25-35 分钟 | 6-10 分钟 | <1 分钟 | 5-8 分钟 | 3-5 分钟 | 10-15 分钟 | **~50-75 分钟** |

步骤 1 用本地模型（离线，不收费）；步骤 2/4 用 Claude API（一期视频通常 < ¥1）；步骤 5/6 调用 Claude Code CLI 运行 Opus，费用稍高（每期约 ¥3-8）。

---

## 数据目录（`data/`）

| 文件 | 说明 |
|------|------|
| `guideline_kedaibiao.md` | 频道 Guideline：受众定位、标题策略、高光选取原则、封面设计逻辑——高光和标题生成都会读这个文件 |
| `top_titles.txt` | 频道 Top 25 真实高播标题，Round 1 评审的外部基准 |
| `channel_vocab.json` | 频道词汇表（人名、品牌名、技术术语），从历史字幕提炼，注入 ASR 热词 |
| `correction_candidates.json` | 高置信度替换规则（数字格式等），规则层直接执行 |

---

## 工具说明

| 脚本 | 功能 |
|------|------|
| `tools/process_video.py` | 主入口，6步流程一体化 |
| `tools/correct/correct_srt.py` | 字幕校对引擎（可单独调用） |
| `tools/resplit_srt.py` | 断句工具（可单独调用） |
| `tools/generate_article.py` | 文章生成（可单独调用） |
| `tools/generate_highlights.py` | 高光提取（可单独调用） |
| `tools/generate_titles.py` | 标题三轮工作流（可单独调用） |

---

## 常见问题

**Q：运行时报 `未安装 mlx-qwen3-asr`？**  
A：确认用的是 `venv/bin/python`，而不是系统自带的 `python3`。如果确认无误还是报错，手动安装：`venv/bin/pip install mlx-qwen3-asr`。

**Q：报错 `ANTHROPIC_API_KEY` 未找到？**  
A：检查项目根目录是否有 `.env` 文件，以及 Key 是否正确粘贴（不要有多余空格）。

**Q：高光分析选错了角度？**  
A：在 SRT 文件末尾手动追加高光字幕（见上方「高光检测逻辑」），系统会优先使用编辑者亲选的片段。

**Q：嘉宾名转录还是错了？**  
A：`--seeds` 里的名字必须是书面正确写法（如「刘嘉」而非「刘佳」）。校对阶段会在全文中查找并报告该名字的出现次数，如果提示「未找到」，说明 Qwen 转录用了另一个写法，需手动查找修改。

**Q：`.final.srt` 断句位置不对？**  
A：调整 `--max-chars` 参数（默认 20 字），或在剪辑软件里手动微调。

**Q：标题生成卡住不动？**  
A：步骤 5-6 调用 `claude -p` CLI，需要 Claude Code 已登录。运行 `claude --version` 确认已安装，运行 `claude -p "test"` 确认已登录。
