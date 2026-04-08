# 课代表视频处理工具 v3

把视频拖进去，自动完成六步流程：转录 → 字幕校对 → 断句 → 文章 → 高光提取 → 标题生成。

**六步流程一览：**

| 步骤 | 内容 | 依赖 |
|------|------|------|
| 1. 转录 | Qwen3-ASR 本地转录，输出 `.qwen.srt` | 本地模型（离线） |
| 2. 字幕校对 | Claude 纠错专有名词/语气词，输出 `.corrected.srt` | Anthropic API |
| 3. 断句 | 每条 ≤20 字重新断句，输出 `.final.srt` | 本地规则 |
| 4. 生成文章 | 提炼频道风格文章，输出 `.article.md` | Claude API |
| 5. 提取高光 | 识别/格式化视频开头高光片段，输出 `.highlights.md` | Claude Code CLI |
| 6. 生成标题 | 三轮 Opus 工作流（高光驱动），输出 `.titles.md` | Claude Code CLI |

> 步骤 1-4 只需 Anthropic API Key。步骤 5-6 还需要安装 **Claude Code CLI**（`claude` 命令）。

---

## 使用前提

| 要求 | 说明 |
|------|------|
| **电脑** | Mac（M1 / M2 / M3 / M4 芯片，即 Apple Silicon） |
| **Python** | 3.10 或更高版本 |
| **API Key** | Anthropic API Key（校对步骤需要，转录不需要） |

> Windows / Intel Mac 暂不支持（转录模型 mlx-qwen3-asr 只支持 Apple Silicon）。

---

## 一次性安装（只做一次）

**第一步：下载代码**

```bash
git clone https://github.com/sunyuzheng/kedaibiao-srt-v2.git
cd kedaibiao-srt-v2
```

**第二步：创建虚拟环境**

```bash
python3 -m venv venv
```

**第三步：安装依赖**

```bash
venv/bin/pip install -r requirements.txt
```

安装时间约 3-10 分钟，mlx-qwen3-asr 会自动下载模型（约 1.5 GB），需要保证网络畅通。

**第四步：配置 API Key**

在项目根目录新建一个 `.env` 文件（注意文件名以点开头），按需填写（用哪家填哪家）：

```
# Claude（Anthropic）
ANTHROPIC_API_KEY=sk-ant-api03-...

# ChatGPT（OpenAI）
OPENAI_API_KEY=sk-proj-...

# Gemini（Google）
GOOGLE_API_KEY=AIzaSy...

# 可选：设置默认使用的模型（否则默认用 Claude Haiku）
DEFAULT_CORRECTION_MODEL=gemini-2.0-flash
```

> `.env` 文件不会被上传到 GitHub，只存在你本地。

---

## 每次使用

**基础用法（最常用）：**

```bash
venv/bin/python tools/process_video.py /path/to/视频.mp4
```

运行后会先询问本期嘉宾名和特殊术语（直接回车跳过也可以）：

```
┌─────────────────────────────────────────────────────────┐
│  转录前：请输入本期嘉宾名、公司名、特有术语（可选）      │
│  这些词会注入 ASR 引导解码，提高专有名词准确率          │
│  直接回车跳过                                            │
└─────────────────────────────────────────────────────────┘
  输入术语（回车结束）: 刘嘉
  ✓ 已添加：刘嘉
  输入术语（回车结束）: Superlinear Academy
  ✓ 已添加：Superlinear Academy
  输入术语（回车结束）:        ← 直接回车结束
```

**输入嘉宾名很重要**：Qwen 语音识别会把「刘嘉」识别成「刘佳」这类同音字，提前告知嘉宾名能大幅提高准确率。

---

## 输出文件

工具完成后，在**视频同目录**生成以下文件：

| 文件 | 说明 | 用途 |
|------|------|------|
| `视频名.qwen.srt` | Qwen 原始转录，未校对 | 备份，一般不用 |
| `视频名.corrected.srt` | Claude 校对后的字幕 | 备份 |
| `视频名.final.srt` | 最终字幕，每条 ≤20字断句 | **导入剪辑软件用这个** |
| `视频名.article.md` | 频道风格文章 | 内容归档，也是标题生成的输入 |
| `视频名.highlights.md` | 视频开头高光片段（中心命题+受众分析+叙事弧） | 标题锚点 |
| `视频名.titles.md` | 最终标题候选（8-10个）+ 封面建议 | **取标题用这个** |
| `视频名_title_ws/` | 标题生成中间文件（round0/round1） | 调试用，可删 |

---

## 常用参数

**直接通过命令行传入嘉宾名（跳过交互询问）：**

```bash
venv/bin/python tools/process_video.py 视频.mp4 --seeds 刘嘉 "Superlinear Academy" 鸭哥
```

**只校对，跳过转录（已有 `.qwen.srt` 时）：**

```bash
venv/bin/python tools/process_video.py 视频.mp4 --skip-transcribe
```

**不输入嘉宾名，直接跑：**

```bash
venv/bin/python tools/process_video.py 视频.mp4 --no-seeds
```

**调整每条字幕最大字数（默认 20）：**

```bash
venv/bin/python tools/process_video.py 视频.mp4 --max-chars 25
```

**切换 LLM 提供商（支持 Claude / OpenAI / Gemini）：**

```bash
# Claude（默认）
venv/bin/python tools/process_video.py 视频.mp4 --model claude-haiku-4-5-20251001
venv/bin/python tools/process_video.py 视频.mp4 --model claude-sonnet-4-6

# OpenAI
venv/bin/python tools/process_video.py 视频.mp4 --model gpt-4o
venv/bin/python tools/process_video.py 视频.mp4 --model gpt-4o-mini

# Google Gemini
venv/bin/python tools/process_video.py 视频.mp4 --model gemini-2.0-flash
venv/bin/python tools/process_video.py 视频.mp4 --model gemini-2.5-pro
```

工具根据模型名前缀自动识别提供商（`claude-*` / `gpt-*` / `gemini-*`）。

**设置默认模型（不想每次加 --model）：**

在 `.env` 文件里加一行：

```
DEFAULT_CORRECTION_MODEL=gemini-2.0-flash
```

---

## 时间参考

| 视频时长 | 转录时间（约） | 校对时间（约） |
|---------|-------------|--------------|
| 15 分钟 | 3-5 分钟 | 1-2 分钟 |
| 35 分钟 | 8-12 分钟 | 3-5 分钟 |
| 106 分钟 | 25-35 分钟 | 8-15 分钟 |

转录用本地模型（离线，不收费）；校对用 Claude API（计费，但费用很低，一期节目通常 < ¥1）。

---

## 常见问题

**Q：安装时报错 `pip install` 失败？**  
A：确认 Python 版本 ≥ 3.10：`python3 --version`。如果版本太低，用 Homebrew 更新：`brew install python@3.12`。

**Q：运行时报 `未安装 mlx-qwen3-asr`？**  
A：确认用了 `venv/bin/python`，而不是系统自带的 `python3`。

**Q：报错 `ANTHROPIC_API_KEY` 未找到？**  
A：检查项目根目录是否有 `.env` 文件，以及文件里 Key 是否正确粘贴（不要有多余空格）。

**Q：嘉宾名还是转录错了？**  
A：`--seeds` 参数里的词必须和嘉宾的书面正确名字一致。如果用了 `--seeds 刘嘉`，系统会在校对阶段检查并报告全文里「刘嘉」出现了几次。如果提示「未找到」，说明 Qwen 转录用的是另一个写法，此时需要手动查找并修改。

**Q：`.final.srt` 的断句位置不对？**  
A：调整 `--max-chars` 参数（默认 20 字）；或者直接在剪辑软件里手动微调。

---

## 常用参数（跳过某些步骤）

```bash
# 跳过转录（已有 .qwen.srt）
venv/bin/python tools/process_video.py 视频.mp4 --skip-transcribe

# 跳过文章生成
venv/bin/python tools/process_video.py 视频.mp4 --skip-article

# 跳过高光提取（不需要标题，或手动写了 .highlights.md）
venv/bin/python tools/process_video.py 视频.mp4 --skip-highlights

# 只要字幕，跳过文章/高光/标题
venv/bin/python tools/process_video.py 视频.mp4 --skip-article --skip-highlights --skip-titles
```

---

## 工具说明

| 脚本 | 功能 |
|------|------|
| `tools/process_video.py` | 主入口，6步流程一体化 |
| `tools/correct/correct_srt.py` | 字幕校对引擎（可单独调用） |
| `tools/resplit_srt.py` | 断句工具（可单独调用） |
| `tools/generate_article.py` | 文章生成（可单独调用） |
| `tools/generate_highlights.py` | 高光提取（可单独调用） |
| `tools/generate_titles.py` | 标题生成，三轮 Opus 工作流（可单独调用） |
| `data/channel_vocab.json` | 频道词汇表（从历史字幕提炼）|

技术设计文档见 [DESIGN.md](DESIGN.md)。

**单独调用高光/标题（对已有 SRT 补跑）：**

```bash
# 单独跑高光
venv/bin/python tools/generate_highlights.py /path/to/视频名.final.srt

# 单独跑标题（自动检测同目录的 .highlights.md）
venv/bin/python tools/generate_titles.py /path/to/视频名.article.md
```
