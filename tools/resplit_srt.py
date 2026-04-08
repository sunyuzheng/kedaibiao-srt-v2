#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
resplit_srt.py — 把 SRT 条目断成 ≤N 字的显示友好格式

断句优先级：
  1. 句末标点（。！？）—— 最优先，保证语义完整
  2. 子句标点（，；、：）—— 次优先
  3. 空格（中英混排的英文词边界）
  4. 强制截断（极端情况兜底）

时间戳按字符数比例插值（中文每字等权，英文字符按实际长度）。

用法：
  python3 tools/resplit_srt.py input.corrected.srt              # → input.final.srt
  python3 tools/resplit_srt.py input.corrected.srt --max-chars 25
  python3 tools/resplit_srt.py input.corrected.srt -o out.srt
"""

import re
import sys
from pathlib import Path

DEFAULT_MAX_CHARS = 20

# ── 时间戳解析 / 格式化 ───────────────────────────────────────────────────────

_TS_RE = re.compile(
    r"(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)"
)


def _parse_ts(ts_line: str) -> tuple[float, float]:
    m = _TS_RE.search(ts_line)
    if not m:
        return 0.0, 0.0
    h1, m1, s1, ms1, h2, m2, s2, ms2 = [int(x) for x in m.groups()]
    start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
    end   = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
    return start, end


def _fmt_ts(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    h,  ms = divmod(ms, 3_600_000)
    m,  ms = divmod(ms,    60_000)
    s,  ms = divmod(ms,     1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_range(t_start: float, t_end: float) -> str:
    return f"{_fmt_ts(t_start)} --> {_fmt_ts(t_end)}"


# ── 文本断句 ──────────────────────────────────────────────────────────────────

def split_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """
    将 text 切成每段 ≤ max_chars 字符的列表。
    尽量在标点处切，保持语义完整。
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    segments: list[str] = []

    # 第一刀：在句末标点后切（保留标点）
    sentence_parts = re.split(r"(?<=[。！？])", text)
    sentence_parts = [p.strip() for p in sentence_parts if p.strip()]

    for part in sentence_parts:
        if len(part) <= max_chars:
            segments.append(part)
            continue

        # 第二刀：在子句标点后切
        clause_parts = re.split(r"(?<=[，；、：])", part)
        clause_parts = [p.strip() for p in clause_parts if p.strip()]

        buf = ""
        for cp in clause_parts:
            if len(buf) + len(cp) <= max_chars:
                buf += cp
            else:
                if buf:
                    segments.append(buf)
                # cp 本身还是太长 → 按空格切（中英混排）
                if len(cp) > max_chars:
                    words = cp.split(" ")
                    word_buf = ""
                    for w in words:
                        candidate = (word_buf + " " + w).strip()
                        if len(candidate) <= max_chars:
                            word_buf = candidate
                        else:
                            if word_buf:
                                segments.append(word_buf)
                            # 单词本身超长 → 强制截断
                            while len(w) > max_chars:
                                segments.append(w[:max_chars])
                                w = w[max_chars:]
                            word_buf = w
                    buf = word_buf
                else:
                    buf = cp
        if buf:
            segments.append(buf)

    return segments if segments else [text]


# ── SRT 解析（轻量版，不依赖 correct_srt）────────────────────────────────────

def _parse_srt(path: Path) -> list[dict]:
    content = path.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n{2,}", content.strip())
    chunks = []
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue
        ts_line = next((l for l in lines if "-->" in l), "")
        text_lines = [l for l in lines
                      if not l.strip().isdigit() and "-->" not in l]
        text = " ".join(text_lines).strip()
        if not text or not ts_line:
            continue
        chunks.append({"timestamp": ts_line, "text": text})
    return chunks


# ── 主函数 ────────────────────────────────────────────────────────────────────

def resplit_srt(
    input_path: Path,
    output_path: Path | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> Path:
    """
    读取 input_path (.corrected.srt 或 .qwen.srt)，
    将每条断成 ≤ max_chars 字符，时间戳按字符比例插值，
    写入 output_path（默认为 input_path 同目录的 .final.srt）。
    """
    if output_path is None:
        stem = input_path.name
        for suf in (".corrected.srt", ".qwen.srt", ".srt"):
            if stem.endswith(suf):
                stem = stem[: -len(suf)]
                break
        output_path = input_path.parent / f"{stem}.final.srt"

    chunks = _parse_srt(input_path)
    result: list[dict] = []

    for chunk in chunks:
        t_start, t_end = _parse_ts(chunk["timestamp"])
        segments = split_text(chunk["text"], max_chars)

        if len(segments) <= 1:
            result.append(chunk)
            continue

        total_chars = sum(len(s) for s in segments)
        if total_chars == 0:
            result.append(chunk)
            continue

        duration = max(t_end - t_start, 0.0)
        t_cursor = t_start
        for seg in segments:
            ratio = len(seg) / total_chars
            t_seg_end = t_cursor + duration * ratio
            result.append({
                "timestamp": _fmt_range(t_cursor, t_seg_end),
                "text": seg,
            })
            t_cursor = t_seg_end

    with open(output_path, "w", encoding="utf-8") as f:
        for i, c in enumerate(result, 1):
            f.write(f"{i}\n{c['timestamp']}\n{c['text']}\n\n")

    return output_path


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="SRT 断句工具")
    parser.add_argument("input", help="输入 SRT 文件路径")
    parser.add_argument("-o", "--output", default=None, help="输出路径（默认 .final.srt）")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS,
                        help=f"每条最大字符数（默认 {DEFAULT_MAX_CHARS}）")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"错误：文件不存在 {input_path}")
        sys.exit(1)

    out = resplit_srt(
        input_path,
        output_path=Path(args.output).resolve() if args.output else None,
        max_chars=args.max_chars,
    )
    print(f"✓ {len(list(open(out).read().split('\n\n')))-1} 条 → {out.name}")


if __name__ == "__main__":
    main()
