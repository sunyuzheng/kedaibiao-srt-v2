#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_article.py — SRT 字幕 → 课代表立正风格文章

将精校后的字幕逐字稿转化为结构化文章，风格遵循从 6M+ 字语料提炼的 axioms：
  KS04 反直觉开场：反常识命题开头，不用"今天我们探讨..."
  KS01 具体锚点+命名框架：数字/故事引入 → 有编号的命名框架收束
  KS03 思考外化：展示推导，不直接断言结论
  KS02 自我暴露弱点：保留失败经历/错误预测，比"成功故事"更有力

用法：
  python3 tools/generate_article.py episode.final.srt
  python3 tools/generate_article.py episode.corrected.srt
  python3 tools/generate_article.py episode.final.srt --max-chars 6000

输出：episode.article.md
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


# ── 风格 Prompt（内联 axioms，不依赖外部文件）───────────────────────────────────

STYLE_BRIEF = """\
课代表立正（孙煜征）的内容风格公理（从 6M+ 字真实语料中提炼）：

**KS04 反直觉开场**
用一个直接反常识的命题开场，例如"好学生思维赚不到钱"、"上班太耽误赚钱了"、"难题≠有价值"。
绝对不用"今天我们来探讨…"、"本期节目…"、"嘉宾xxx分享了…"这类平开场。

**KS01 具体锚点 + 命名框架**
先用具体数字、真实故事或极端场景引入话题，然后提炼为有编号和命名的框架（"三个开关"、"二层模型"、"OPC框架"）。
洞察不能停留在散文状态——必须收束为一个可引用的结构。

**KS03 思考外化**
展示推导过程，而不是直接给结论。"我是这样想的"比"答案是X"更有信任感。
邀请读者参与推导，而不是接受断言。

**KS02 自我暴露弱点作为教材**
如果内容中有失败经历、错误预测、或嘉宾/主持人承认自己的问题，必须保留并放大。
"我替你踩过坑"比"这是正确答案"更有力。

**反鸡汤禁用词**
严禁出现：灯塔、基石、领航、赋能、抓手、颗粒度、认知升级、干货满满、硬核、保姆级、
重磅、揭秘、必看、深度解析、全面解读。
"""

ARTICLE_INSTRUCTION = """\
根据以下播客逐字稿，写一篇符合上述风格的文章。

文章结构要求：
1. **第一段**：一个反直觉的命题或具体冲击性场景（≤3行），不解释、不铺垫，直接抛出
2. **正文**：2-4个命名框架的核心观点，每个框架包含：
   - 具体锚点（数字、故事或场景）
   - 洞察（有名字的框架或原则）
   - 落地（这意味着什么，怎么用）
3. **结尾**：一句让人有所触动的结论（不是说教，不是"所以我们应该…"）

字数：1000-1500字（不包含标题）
格式：Markdown，节标题用 ## 命名框架

只输出文章本身，不要加"以下是文章"之类的前言。
"""


# ── SRT 文本提取 ────────────────────────────────────────────────────────────────

def srt_to_text(srt_path: Path) -> str:
    """提取 SRT 纯文本，合并成连续段落"""
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


# ── Claude CLI 调用 ─────────────────────────────────────────────────────────────

def call_claude(prompt: str, timeout: int = 300) -> str:
    """通过 claude -p 调用 Claude，返回输出文本"""
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        err = result.stderr.strip()
        raise RuntimeError(f"claude -p 失败 (exit {result.returncode}): {err[:200]}")
    return result.stdout.strip()


# ── 主函数 ──────────────────────────────────────────────────────────────────────

def generate_article(srt_path: Path, max_chars: int = 6000) -> Path:
    """SRT → 文章，返回输出文件路径"""
    output_path = srt_path.with_suffix("").with_suffix(".article.md")

    # 提取文本
    text = srt_to_text(srt_path)
    if len(text) > max_chars:
        text = text[:max_chars] + "…（已截断）"

    # 构造 prompt
    prompt = (
        STYLE_BRIEF
        + "\n\n"
        + ARTICLE_INSTRUCTION
        + "\n\n以下是本期逐字稿：\n\n---\n"
        + text
        + "\n---"
    )

    article = call_claude(prompt)
    output_path.write_text(article, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="SRT 字幕 → 课代表立正风格文章")
    parser.add_argument("srt", help="输入 SRT 文件路径（.final.srt 或 .corrected.srt）")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=6000,
        help="逐字稿截断长度（默认 6000 字符）",
    )
    args = parser.parse_args()

    srt_path = Path(args.srt).resolve()
    if not srt_path.exists():
        print(f"错误: 文件不存在: {srt_path}")
        sys.exit(1)

    print(f"  生成文章：{srt_path.name} …", flush=True)
    try:
        out = generate_article(srt_path, max_chars=args.max_chars)
        print(f"  ✓ 文章已写入：{out.name}")
    except Exception as e:
        print(f"  ✗ 失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
