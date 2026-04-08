# 课代表字幕自动校对工具 v2

把视频拖进去，自动转录 + 校对，输出可直接导入剪辑软件的 `.srt` 字幕文件。

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

在项目根目录新建一个 `.env` 文件（注意文件名以点开头），写入：

```
ANTHROPIC_API_KEY=你的key粘贴在这里
```

API Key 格式类似 `sk-ant-api03-...`，从 Anthropic Console 获取。

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

工具完成后，在**视频同目录**生成三个文件：

| 文件 | 说明 | 用途 |
|------|------|------|
| `视频名.qwen.srt` | Qwen 原始转录，未校对 | 备份，一般不用 |
| `视频名.corrected.srt` | Claude 校对后的字幕 | 备份 |
| `视频名.final.srt` | 最终字幕，每条 ≤20字断句 | **导入剪辑软件用这个** |

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

**使用更强的 Claude 模型（默认是 haiku，最快最便宜；sonnet 更准但慢）：**

```bash
venv/bin/python tools/process_video.py 视频.mp4 --model claude-sonnet-4-6
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

## 工具说明

| 脚本 | 功能 |
|------|------|
| `tools/process_video.py` | 主入口，转录 + 校对 + 断句一体化 |
| `tools/correct/correct_srt.py` | 校对引擎（可单独调用） |
| `tools/resplit_srt.py` | 断句工具（可单独调用） |
| `data/channel_vocab.json` | 频道词汇表（从171期历史字幕提炼）|

技术设计文档见 [DESIGN.md](DESIGN.md)。
