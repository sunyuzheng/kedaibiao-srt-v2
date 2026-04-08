#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_highlights.py — 从 SRT 逐字稿提取高光片段 v2

核心逻辑：
  1. 优先检测 SRT 末尾追加的真实高光字幕（00:00:xx 时间戳，编辑者亲手选定）
     如果存在，用它作为权威高光来源进行分析
  2. 不存在时，用分区采样全文扫描

高光的目标：
  - 3-5 段精选片段（理想 3 段），放到视频开头 30-90 秒
  - 让观众感受到"这期很值"
  - 为标题提供具体的素材支撑
  - 访谈优先选嘉宾说的话；单口选主播的核心论断

用法：
  python3 tools/generate_highlights.py episode.final.srt
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


# ── SRT 解析工具 ───────────────────────────────────────────────────────────────

def srt_to_text(srt_path: Path) -> str:
    """提取 SRT 全文纯文本"""
    content = srt_path.read_text(encoding="utf-8")
    lines = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r"^\d+$", line):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->", line):
            continue
        lines.append(line)
    return " ".join(lines)


def extract_appended_highlights(srt_path: Path) -> str:
    """
    检测 SRT 末尾是否有追加的真实高光字幕。

    特征：主内容时间戳在 00:01:xx 以后，高光字幕追加在末尾但时间戳
    重置为 00:00:xx（编辑者从视频开头截取后追加到 SRT 文件末尾）。

    返回高光文本，或空字符串（未检测到）。
    """
    content = srt_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # 找最后一段 00:00:xx 时间戳出现的位置
    # 策略：找到 SRT 中最后一个 00:00 开头的时间戳行
    last_00_pos = -1
    for i, line in enumerate(lines):
        if re.match(r"^00:00:\d{2}[,\.]\d{3}\s*-->", line.strip()):
            last_00_pos = i

    if last_00_pos == -1:
        return ""

    # 验证：这个 00:00 块出现在主内容（>00:01:xx）之后
    # 如果文件前 10% 就有 00:00 块，那可能就是正常的视频开头，不是追加的高光
    if last_00_pos < len(lines) * 0.3:
        return ""

    # 提取从该位置开始的所有文本
    texts = []
    for line in lines[last_00_pos:]:
        line = line.strip()
        if not line:
            continue
        if re.match(r"^\d+$", line):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->", line):
            continue
        texts.append(line)

    return " ".join(texts)


def sample_content(text: str, max_chars: int = 14000) -> str:
    """分区采样确保覆盖视频全程"""
    if len(text) <= max_chars:
        return text
    chunk = max_chars // 4
    total = len(text)
    parts = []
    labels = ["【视频前段】", "【视频中前段】", "【视频中后段】", "【视频后段】"]
    for i in range(4):
        start = int(i * total / 4)
        end = min(start + chunk, total)
        parts.append(labels[i] + "\n" + text[start:end])
    return "\n\n[...省略...]\n\n".join(parts)


# ── Claude CLI ────────────────────────────────────────────────────────────────

def call_claude(prompt: str, timeout: int = 900) -> str:
    result = subprocess.run(
        ["claude", "-p", "--model", "claude-opus-4-6", prompt],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        err = result.stderr.strip()
        raise RuntimeError(f"claude -p 失败 (exit {result.returncode}): {err[:200]}")
    return result.stdout.strip()


# ── Prompts ───────────────────────────────────────────────────────────────────

HIGHLIGHTS_FROM_ACTUAL = """\
你是课代表立正频道的内容编辑。

## 任务背景

以下是编辑者已经亲手选定的视频高光片段的逐字内容（从视频开头 30-90 秒截取）。
这是真实使用的开场钩子，不是 AI 推荐的。

你的任务是：
1. 分析这些高光的主题和叙事弧线
2. 判断视频类型（访谈/单口）和主发言人
3. 格式化为标准高光输出，让标题生成步骤能用

## 实际高光文本

{highlights_text}

---

## 完整内容（背景参考）

{content_sample}

---

## 输出要求

### 第一步：中心命题

用一句话说出这期内容最想让观众相信或感受到的东西。
不是"讲了什么话题"，而是"这期的核心论点是什么"。

### 第二步：受众分析

这期内容的核心命题，能触达哪些人群？
- 频道现有受众（AI/职场/创业圈）
- 还有哪些更广泛的人群也会关心这个命题？

### 第三步：格式化高光输出

**视频类型**：[访谈 / 单口]
**主发言人**：[嘉宾姓名/描述 / "主播孙煜征"]

---

### Highlight 1

**引用**：「[从实际高光文本中截取最有力的原话，20-80字]」
**叙事位置**：[这段在整体高光弧线里起什么作用：起/承/转/合]
**为什么有力**：[一句话]
**好奇钩子**：[观众会想问的问题]

### Highlight 2 / 3 ...

（同格式，从实际高光文本中提取，不要虚构内容）

---

### 高光叙事弧

用 2-3 句话描述这几段高光组合在一起，向观众传递了什么情绪/认知旅程。
"""

HIGHLIGHTS_FROM_SCAN = """\
你是课代表立正频道的内容编辑，专门负责为视频选取开场高光片段。

## 任务背景

这期视频开头 30-90 秒会播放精选高光，目的是：
1. 让刚点进来的观众立刻感受到"这期很值"
2. 制造信息缺口——听完某句话后，观众想知道"为什么？怎么来的？后来呢？"
3. 为标题提供素材锚点

## 选高光的核心逻辑

**一组好的高光应该有叙事弧线，不只是个别精彩时刻的堆砌。**

理想结构：起（钩子/冲突）→ 承（深化/背景）→ 合（洞见/悬念）

每段高光需满足：
- 原话引用（不是总结，不是改写）
- 制造信息缺口：听完想知道更多
- 单独成立，但几段合起来讲一个更大的故事

访谈：优先嘉宾的话；单口：选主播的核心论断

---

## 第一步：中心命题

先用一句话说出这期内容最想让观众相信/感受到什么。

## 第二步：受众扩展

这期内容的核心命题，除了频道现有受众外，还能触达哪些更广泛的人群？

## 第三步：扫描全文，选出最终 3-5 个高光

扫描范围：全文（前/中/后段都要看，好高光可能在任何位置）

选择优先级：
1. 服务中心命题 > 个别戏剧性
2. 嘉宾/主播亲身故事 > 观点陈述
3. 有具体细节的 > 抽象的
4. 组合后有叙事弧线 > 孤立的金句

---

## 输出格式

**视频类型**：[访谈 / 单口]
**主发言人**：[嘉宾姓名/描述 / "主播孙煜征"]

**中心命题**：[一句话]
**受众扩展**：[除现有受众外还有哪些人群]

---

### Highlight 1

**位置**：[前段/中段/后段]
**引用**：「[20-80字原话]」
**叙事位置**：[起/承/转/合]
**为什么有力**：[一句话]
**好奇钩子**：[观众会问的问题]

...

### 高光叙事弧

[2-3句话描述这组高光合在一起传递的情绪/认知旅程]

---

## 本期内容

{content}
"""


# ── 主逻辑 ────────────────────────────────────────────────────────────────────

def generate_highlights(srt_path: Path) -> Path:
    stem = srt_path.with_suffix("").stem
    for suffix in (".final", ".corrected", ".qwen", ".article"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    output_path = srt_path.parent / f"{stem}.highlights.md"

    # 读取内容
    if srt_path.suffix == ".md":
        full_text = srt_path.read_text(encoding="utf-8")
        actual_highlights = ""
    else:
        full_text = srt_to_text(srt_path)
        actual_highlights = extract_appended_highlights(srt_path)

    if actual_highlights:
        print(f"    ✓ 检测到编辑者亲选的高光字幕（{len(actual_highlights)} 字），优先使用")
        content_sample = sample_content(full_text, max_chars=8000)
        prompt = HIGHLIGHTS_FROM_ACTUAL.format(
            highlights_text=actual_highlights,
            content_sample=content_sample,
        )
    else:
        print(f"    ! 未检测到追加高光，扫描全文选取")
        content = sample_content(full_text, max_chars=14000)
        prompt = HIGHLIGHTS_FROM_SCAN.format(content=content)

    print("    高光分析中…", flush=True)
    result = call_claude(prompt, timeout=900)
    output_path.write_text(result, encoding="utf-8")
    print(f"    ✓ {output_path.name} 已写入")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="从 SRT 提取/分析视频高光片段 v2")
    parser.add_argument("content", help="输入文件：.final.srt / .corrected.srt / .article.md")
    args = parser.parse_args()

    srt_path = Path(args.content).resolve()
    if not srt_path.exists():
        print(f"错误: 文件不存在: {srt_path}")
        sys.exit(1)

    print(f"  高光提取：{srt_path.name} …", flush=True)
    try:
        out = generate_highlights(srt_path)
        print(f"  ✓ 高光已写入：{out.name}")
    except Exception as e:
        print(f"  ✗ 失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
