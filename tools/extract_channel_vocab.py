#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_channel_vocab.py — 从 kedaibiao-channel 的历史数据提取频道词汇表

策略：
  1. 从 error_notebook.jsonl 的 human 侧提取多字符正确形式（品牌名、人名、术语）
  2. 从人工精校 SRT 提取高频英文专有名词（大写开头且 ≥3 个视频出现）
  3. 合并成 channel_vocab.json，供转录时 context= 注入和校对时规则替换用

输出：data/channel_vocab.json

用法：
  python3 tools/extract_channel_vocab.py
  python3 tools/extract_channel_vocab.py --min-videos 2 --min-errors 3
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ── 配置 ─────────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
_CHANNEL = Path("/Users/sunyuzheng/Desktop/AI/content/kedaibiao-channel")
_ERROR_NOTEBOOK = _CHANNEL / "logs" / "error_notebook.jsonl"
_CHANNEL_CANDIDATES = _ROOT / "data" / "correction_candidates.json"

ARCHIVE_DIRS = [
    _CHANNEL / "archive" / "有人工字幕",
    _CHANNEL / "archive" / "会员视频",
]
OUTPUT = _ROOT / "data" / "channel_vocab.json"

# 词汇表阈值
MIN_VIDEO_COUNT = 3    # 英文专有名词：至少在几个视频的人工SRT里出现
MIN_ERROR_COUNT = 5    # 错误映射：至少出现几次
MIN_TERM_LEN = 2       # 最短词长（字符数）

# 常见英文词过滤列表（不是频道专有词）
_COMMON_EN = frozenset("""
the a an in on at to of is it as be or and for but not so by
we me he she they you your our my his her its their
do did does doing done have has had get got go going
ai ok dr mr ms yeah right yes no oh well so now
just like when what where how why who which this that
one two three also very much more most about after
work works working make makes let us can will be
""".split())

# ─────────────────────────────────────────────────────────────────────────────

_TS_RE = re.compile(r"\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}")
# 英文专有名词：首字母大写，或全大写缩写，长度≥2
_EN_PROPER = re.compile(r"\b([A-Z][A-Za-z0-9\-\.]{1,}|[A-Z]{2,})\b")


def parse_srt_text(path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    lines = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.isdigit() or _TS_RE.search(line):
            continue
        lines.append(line)
    return " ".join(lines)


def find_srt_pairs() -> list[tuple[Path, Path]]:
    pairs = []
    human_suffixes = (".zh.srt", ".en-zh.srt", ".zh-Hans.srt", ".zh-Hant.srt")
    for base in ARCHIVE_DIRS:
        if not base.exists():
            continue
        for qwen in sorted(base.rglob("*.qwen.srt")):
            folder = qwen.parent
            stem = qwen.name.replace(".qwen.srt", "")
            for suf in human_suffixes:
                candidate = folder / (stem + suf)
                if candidate.exists():
                    pairs.append((qwen, candidate))
                    break
    return pairs


def extract_english_proper_nouns(pairs: list[tuple[Path, Path]], min_videos: int) -> dict:
    """
    从人工精校 SRT 提取大写开头的英文专有名词（≥min_videos 个视频出现）。
    这些词是频道常用的品牌/术语，Qwen 容易拼错。
    """
    term_videos: dict[str, set] = defaultdict(set)
    for qwen_path, human_path in pairs:
        text = parse_srt_text(human_path)
        for m in _EN_PROPER.finditer(text):
            word = m.group()
            if word.lower() in _COMMON_EN:
                continue
            if len(word) < MIN_TERM_LEN:
                continue
            term_videos[word].add(str(human_path))
    return {term: len(vids) for term, vids in term_videos.items()
            if len(vids) >= min_videos}


def extract_from_error_notebook(min_count: int) -> tuple[dict, dict, dict]:
    """
    从 error_notebook.jsonl 提取：
    - multi_char_map: 多字符词的 qwen→correct（含数字格式、多字词）
    - name_brand_map: 人名/品牌词
    - bidirectional_skip: 双向混淆的单字词（需要上下文，不能规则化）

    返回 (multi_char_map, name_brand_map, single_char_unidirectional)
    """
    if not _ERROR_NOTEBOOK.exists():
        print(f"  警告：找不到 {_ERROR_NOTEBOOK}")
        return {}, {}, {}

    pair_count: Counter = Counter()
    pair_meta: dict = {}

    with open(_ERROR_NOTEBOOK, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                q, h = e["qwen"], e["human"]
                pair_count[(q, h)] += 1
                pair_meta[(q, h)] = e.get("category", "other")
            except Exception:
                continue

    multi_char: dict = {}
    name_brand: dict = {}
    single_unidirectional: dict = {}

    for (q, h), cnt in pair_count.items():
        if cnt < min_count:
            continue
        # 跳过明显无意义的（单个字母替换）
        if len(q) <= 1 and len(h) <= 1:
            reverse = pair_count.get((h, q), 0)
            if reverse >= min_count:
                continue  # 双向单字符混淆，需要上下文
            # 单向单字符：也可以收集
            single_unidirectional[q] = {"correct": h, "count": cnt,
                                         "category": pair_meta.get((q, h), "other")}
            continue

        cat = pair_meta.get((q, h), "other")
        entry = {"correct": h, "count": cnt, "category": cat}

        # 人名/品牌判断：category 包含 name/brand，或 correct 含大写英文字母
        if cat in ("name", "brand") or re.search(r"[A-Z]{2}", h):
            name_brand[q] = entry
        else:
            # 多字符词（含数字格式如百分之十→10%）
            if len(q) >= 2 or len(h) >= 2:
                # 双向检查：如果双向都高频，需要上下文
                reverse_cnt = pair_count.get((h, q), 0)
                if reverse_cnt >= min_count and len(q) <= 2 and len(h) <= 2:
                    continue  # 双向短词混淆
                multi_char[q] = entry

    return multi_char, name_brand, single_unidirectional


def load_existing_candidates() -> dict:
    """加载 kedaibiao-channel 已验证的 correction_candidates.json"""
    if not _CHANNEL_CANDIDATES.exists():
        return {}
    try:
        return json.loads(_CHANNEL_CANDIDATES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_hotwords_context(vocab: dict) -> str:
    """
    构建传给 Qwen3-ASR context= 参数的字符串。
    格式：自然语言段落，包含频道关键词，引导 ASR 解码倾向于生成这些词。
    """
    parts = ["以下是本频道相关词汇，供参考："]

    # 英文专有名词（Top 20，按出现频率）
    en_terms = sorted(vocab.get("english_proper_nouns", {}).items(),
                      key=lambda x: -x[1])
    if en_terms:
        top_en = [t for t, _ in en_terms[:25]]
        parts.append("英文品牌/术语：" + " ".join(top_en))

    # 频道已知人名纠错（human 侧）
    name_corrects = [v["correct"] for v in
                     vocab.get("name_brand_corrections", {}).values()
                     if v.get("count", 0) >= 8]
    if name_corrects:
        parts.append("嘉宾/人名参考：" + "、".join(name_corrects[:15]))

    return "\n".join(parts)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-videos", type=int, default=MIN_VIDEO_COUNT)
    parser.add_argument("--min-errors", type=int, default=MIN_ERROR_COUNT)
    args = parser.parse_args()

    print("扫描 SRT 配对…")
    pairs = find_srt_pairs()
    print(f"  找到 {len(pairs)} 对 Qwen+人工 SRT")

    print(f"提取英文专有名词（首字母大写，≥{args.min_videos} 个视频）…")
    en_proper = extract_english_proper_nouns(pairs, args.min_videos)
    print(f"  {len(en_proper)} 个英文专有词")

    print(f"从 error_notebook 提取纠错映射（≥{args.min_errors} 次）…")
    multi_char, name_brand, single_uni = extract_from_error_notebook(args.min_errors)
    print(f"  多字符纠错：{len(multi_char)} 条")
    print(f"  人名/品牌纠错：{len(name_brand)} 条")
    print(f"  单字符单向纠错：{len(single_uni)} 条（供参考，不直接规则化）")

    print("加载已验证的 correction_candidates…")
    existing = load_existing_candidates()
    print(f"  {len(existing)} 条已验证规则")

    vocab = {
        "meta": {
            "source_pairs": len(pairs),
            "min_video_count": args.min_videos,
            "min_error_count": args.min_errors,
        },
        "english_proper_nouns": en_proper,
        "name_brand_corrections": name_brand,
        "multi_char_corrections": multi_char,
        "single_char_unidirectional": single_uni,
        "verified_candidates": existing,  # 来自 kedaibiao-channel 已验证的规则
    }
    vocab["hotwords_context"] = build_hotwords_context(vocab)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ 写入 {OUTPUT}")

    print("\n=== 英文专有名词（Top 20）===")
    for term, cnt in sorted(en_proper.items(), key=lambda x: -x[1])[:20]:
        print(f"  {cnt:3d}x  {term}")

    print("\n=== 人名/品牌纠错（Top 15）===")
    for q, info in sorted(name_brand.items(), key=lambda x: -x[1]["count"])[:15]:
        print(f"  {info['count']:3d}x  {q!r:20s} → {info['correct']!r}")

    print("\n=== 多字符纠错（Top 20）===")
    for q, info in sorted(multi_char.items(), key=lambda x: -x[1]["count"])[:20]:
        print(f"  {info['count']:3d}x  {q!r:20s} → {info['correct']!r}  ({info['category']})")

    print("\n=== Hotwords context ===")
    print(vocab["hotwords_context"])


if __name__ == "__main__":
    main()
