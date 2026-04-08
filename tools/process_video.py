#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
process_video.py v3 — 视频转录 + 字幕校对 + 文章 + 高光 + 标题一体化入口

六步流程：
  1. Qwen3-ASR 转录
  2. Claude 字幕校对
  3. 断句处理
  4. 生成频道风格文章
  5. 提取视频高光片段（NEW：扫描全片选 3-5 个高光，供标题锚定）
  6. 生成播客标题（高光驱动，三轮 claude-opus-4-6 工作流）

用法：
  python3 tools/process_video.py video.mp4
  python3 tools/process_video.py video.mp4 --skip-transcribe
  python3 tools/process_video.py video.mp4 --seeds 刘嘉 "Superlinear Academy"
  python3 tools/process_video.py video.mp4 --model claude-sonnet-4-6
  python3 tools/process_video.py video.mp4 --no-seeds
  python3 tools/process_video.py video.mp4 --skip-article
  python3 tools/process_video.py video.mp4 --skip-highlights   # 跳过高光提取
  python3 tools/process_video.py video.mp4 --skip-titles
"""

import argparse
import json
import sys
import time
from pathlib import Path

_TOOLS = Path(__file__).parent
_ROOT  = _TOOLS.parent
sys.path.insert(0, str(_TOOLS / "correct"))

AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".mp4", ".mov", ".flac", ".ogg", ".webm"}
QWEN_MODEL = "Qwen/Qwen3-ASR-1.7B"
QWEN_LANG  = "Chinese"
_VOCAB_FILE = _ROOT / "data" / "channel_vocab.json"


def load_channel_context() -> str:
    """从 channel_vocab.json 读取预构建的 hotwords context 字符串"""
    if _VOCAB_FILE.exists():
        try:
            vocab = json.loads(_VOCAB_FILE.read_text(encoding="utf-8"))
            return vocab.get("hotwords_context", "")
        except Exception:
            pass
    return ""


def build_transcribe_context(channel_ctx: str, episode_seeds: list[str]) -> str:
    """把频道 context + 本期 seeds 合并成传给 Qwen3-ASR context= 的字符串"""
    parts = []
    if channel_ctx:
        parts.append(channel_ctx)
    if episode_seeds:
        parts.append("本期嘉宾/术语：" + "、".join(episode_seeds))
    return "\n".join(parts)


def ask_episode_seeds() -> list[str]:
    """交互式询问本期嘉宾名和特有术语"""
    print()
    print("┌─────────────────────────────────────────────────────────┐")
    print("│  转录前：请输入本期嘉宾名、公司名、特有术语（可选）      │")
    print("│  这些词会注入 ASR 引导解码，提高专有名词准确率          │")
    print("│  直接回车跳过                                            │")
    print("└─────────────────────────────────────────────────────────┘")
    seeds = []
    while True:
        try:
            val = input("  输入术语（回车结束）: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not val:
            break
        seeds.append(val)
        print(f"  ✓ 已添加：{val}")
    return seeds


def transcribe(video_path: Path, context: str = "") -> Path:
    """Qwen3-ASR 转录，输出 <stem>.qwen.srt"""
    qwen_srt = video_path.with_suffix("").with_suffix(".qwen.srt")
    if qwen_srt.exists():
        print(f"  [跳过] 已存在 {qwen_srt.name}")
        return qwen_srt

    try:
        from mlx_qwen3_asr import Session
    except ImportError:
        print("错误: 未安装 mlx-qwen3-asr，请运行: pip install mlx-qwen3-asr")
        sys.exit(1)

    if context:
        print(f"  Context 注入（前100字）: {context[:100]}…", flush=True)

    print(f"  加载 Qwen3-ASR 模型…", flush=True)
    t0 = time.time()
    session = Session(QWEN_MODEL)

    print(f"  转录中: {video_path.name}", flush=True)
    kwargs = dict(
        language=QWEN_LANG,
        return_chunks=True,
        verbose=False,
    )
    if context:
        kwargs["context"] = context

    result = session.transcribe(str(video_path), **kwargs)
    elapsed = time.time() - t0
    chunks = result.chunks or []

    _write_srt(chunks, qwen_srt)
    dur = chunks[-1]["end"] if chunks else 0
    ratio = dur / elapsed if elapsed > 0 else 0
    print(f"  ✓ 转录完成  {len(chunks)} 句  {elapsed:.0f}s  ({ratio:.1f}x 实时)")
    return qwen_srt


def _write_srt(chunks: list, srt_path: Path) -> None:
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, chunk in enumerate(chunks, 1):
            start = _fmt_ts(chunk["start"])
            end   = _fmt_ts(chunk["end"])
            text  = chunk["text"].strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")


def _fmt_ts(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms,    60_000)
    s, ms = divmod(ms,     1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def correct(qwen_srt: Path, episode_seeds: list[str], model: str) -> Path | None:
    from correct_srt import correct_file
    t0 = time.time()
    print(f"  校对中…", flush=True)
    result = correct_file(
        qwen_srt,
        episode_seeds=episode_seeds,
        model=model,
        verbose=False,
    )
    elapsed = time.time() - t0
    if result:
        print(f"  ✓ 校对完成  {elapsed:.0f}s")
    else:
        print(f"  ✗ 校对失败")
    return result


def resplit(corrected_srt: Path, max_chars: int = 20) -> Path | None:
    sys.path.insert(0, str(_TOOLS))
    from resplit_srt import resplit_srt
    t0 = time.time()
    print(f"  断句处理（≤{max_chars}字/条）…", flush=True)
    try:
        result = resplit_srt(corrected_srt, max_chars=max_chars)
        elapsed = time.time() - t0
        n = sum(1 for line in result.read_text(encoding="utf-8").split("\n\n") if line.strip())
        print(f"  ✓ 断句完成  {n} 条  {elapsed:.0f}s")
        return result
    except Exception as e:
        print(f"  ✗ 断句失败: {e}")
        return None


def article(final_srt: Path) -> Path | None:
    sys.path.insert(0, str(_TOOLS))
    from generate_article import generate_article
    t0 = time.time()
    print(f"  生成文章…", flush=True)
    try:
        result = generate_article(final_srt)
        elapsed = time.time() - t0
        print(f"  ✓ 文章完成  {elapsed:.0f}s  → {result.name}")
        return result
    except Exception as e:
        print(f"  ✗ 文章生成失败: {e}")
        return None


def highlights(srt_path: Path) -> Path | None:
    sys.path.insert(0, str(_TOOLS))
    from generate_highlights import generate_highlights
    t0 = time.time()
    print(f"  提取高光片段…", flush=True)
    try:
        result = generate_highlights(srt_path)
        elapsed = time.time() - t0
        print(f"  ✓ 高光完成  {elapsed:.0f}s  → {result.name}")
        return result
    except Exception as e:
        print(f"  ✗ 高光提取失败: {e}")
        return None


def titles(content_path: Path) -> Path | None:
    sys.path.insert(0, str(_TOOLS))
    from generate_titles import generate_titles
    t0 = time.time()
    print(f"  生成标题（三轮，高光驱动）…", flush=True)
    try:
        result = generate_titles(content_path)
        elapsed = time.time() - t0
        print(f"  ✓ 标题完成  {elapsed:.0f}s  → {result.name}")
        return result
    except Exception as e:
        print(f"  ✗ 标题生成失败: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="视频转录 + 字幕校对 + 文章 + 标题 v2")
    parser.add_argument("video", help="视频文件路径")
    parser.add_argument("--skip-transcribe", action="store_true")
    parser.add_argument("--skip-correct", action="store_true")
    parser.add_argument("--skip-article", action="store_true",
                        help="跳过文章生成")
    parser.add_argument("--skip-highlights", action="store_true",
                        help="跳过高光提取")
    parser.add_argument("--skip-titles", action="store_true",
                        help="跳过标题生成")
    parser.add_argument("--seeds", nargs="*", default=None,
                        help="本期嘉宾/术语（跳过交互式询问）")
    parser.add_argument("--no-seeds", action="store_true",
                        help="跳过 seeds 输入（不询问也不注入）")
    parser.add_argument("--model", default="claude-haiku-4-5-20251001")
    parser.add_argument("--max-chars", type=int, default=20,
                        help="断句：每条字幕最大字符数（默认 20）")
    args = parser.parse_args()

    video_path = Path(args.video).resolve()
    if not video_path.exists():
        print(f"错误: 文件不存在: {video_path}")
        sys.exit(1)

    print(f"\n{'='*55}")
    print(f"视频: {video_path.name}")
    print(f"流程: 转录 → 校对 → 断句 → 文章 → 高光 → 标题")
    print(f"{'='*55}")

    # ── 决定 episode_seeds ───────────────────────────────────────────────────
    if args.no_seeds:
        episode_seeds = []
    elif args.seeds is not None:
        episode_seeds = [s.strip() for s in args.seeds if s.strip()]
        if episode_seeds:
            print(f"\n种子术语：{episode_seeds}")
    else:
        episode_seeds = ask_episode_seeds()
        if episode_seeds:
            print(f"  种子术语已确认：{episode_seeds}")

    # ── 1. 转录 ───────────────────────────────────────────────────────────────
    if not args.skip_transcribe:
        print("\n[1/5] Qwen3-ASR 转录")
        channel_ctx = load_channel_context()
        context = build_transcribe_context(channel_ctx, episode_seeds)
        qwen_srt = transcribe(video_path, context=context)
    else:
        qwen_srt = video_path.with_suffix("").with_suffix(".qwen.srt")
        if not qwen_srt.exists():
            print(f"错误: --skip-transcribe 但找不到 {qwen_srt.name}")
            sys.exit(1)
        print(f"\n[1/5] 转录 (已跳过) → {qwen_srt.name}")

    # ── 2. 校对 ───────────────────────────────────────────────────────────────
    corrected_srt = None
    if not args.skip_correct:
        print("\n[2/5] Claude 字幕校对 + 全文扫描")
        corrected_srt = correct(qwen_srt, episode_seeds, model=args.model)
    else:
        corrected_srt = video_path.with_suffix("").with_suffix(".corrected.srt")
        if not corrected_srt.exists():
            corrected_srt = None
        print(f"\n[2/5] 校对 (已跳过)")

    # ── 3. 断句 ───────────────────────────────────────────────────────────────
    print(f"\n[3/5] 断句处理")
    final_srt = None
    if corrected_srt and corrected_srt.exists():
        final_srt = resplit(corrected_srt, max_chars=args.max_chars)
    else:
        print("  (无校对文件，跳过)")
        # 降级：用 corrected 或 qwen 作为来源
        for candidate in [
            video_path.with_suffix("").with_suffix(".final.srt"),
            video_path.with_suffix("").with_suffix(".corrected.srt"),
            video_path.with_suffix("").with_suffix(".qwen.srt"),
        ]:
            if candidate.exists():
                final_srt = candidate
                break

    # ── 4. 生成文章 ───────────────────────────────────────────────────────────
    article_path = None
    if not args.skip_article:
        print(f"\n[4/6] 生成频道风格文章")
        src = final_srt or corrected_srt or qwen_srt
        if src and src.exists():
            article_path = article(src)
        else:
            print("  (无可用 SRT，跳过)")
    else:
        candidate = video_path.with_suffix("").with_suffix(".article.md")
        if candidate.exists():
            article_path = candidate
        print(f"\n[4/6] 文章生成 (已跳过)")

    # ── 5. 提取高光 ───────────────────────────────────────────────────────────
    highlights_path = None
    if not args.skip_highlights:
        print(f"\n[5/6] 提取视频高光片段")
        src = final_srt or corrected_srt or qwen_srt
        if src and src.exists():
            highlights_path = highlights(src)
        else:
            print("  (无可用 SRT，跳过)")
    else:
        # 检查是否已有高光文件
        stem = video_path.with_suffix("").stem
        candidate = video_path.parent / f"{stem}.highlights.md"
        if candidate.exists():
            highlights_path = candidate
        print(f"\n[5/6] 高光提取 (已跳过)")

    # ── 6. 生成标题 ───────────────────────────────────────────────────────────
    if not args.skip_titles:
        print(f"\n[6/6] 生成播客标题（高光驱动）")
        # 优先用 article，其次 final_srt — highlights 会通过文件名自动检测
        src = article_path or final_srt or corrected_srt or qwen_srt
        if src and src.exists():
            titles(src)
        else:
            print("  (无可用来源，跳过)")
    else:
        print(f"\n[6/6] 标题生成 (已跳过)")

    print(f"\n{'='*55}")
    for suf in [".qwen.srt", ".corrected.srt", ".final.srt",
                ".article.md", ".highlights.md", ".titles.md"]:
        p = video_path.with_suffix("").with_suffix(suf)
        if suf == ".highlights.md":
            # highlights 文件名不带 video 后缀，单独处理
            stem = video_path.with_suffix("").stem
            p = video_path.parent / f"{stem}.highlights.md"
        print(f"  {'✓' if p.exists() else '✗'} {p.name}")
    print()


if __name__ == "__main__":
    main()
