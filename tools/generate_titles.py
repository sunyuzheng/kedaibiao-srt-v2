#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_titles.py — 课代表立正播客标题三轮生成工作流 v3

核心变化（相比 v2）：
  - 新增高光驱动：优先从 {stem}.highlights.md 读取高光片段作为标题锚点
  - 标题必须与高光对齐——标题创造期待，高光在开头证实这个期待值得
  - Round 1 使用频道真实高播标题作外部基准（不是模型自评）
  - 三轮全程使用 claude-opus-4-6，timeout 900s

用法：
  python3 tools/generate_titles.py episode.article.md        # 自动检测同目录 highlights
  python3 tools/generate_titles.py episode.final.srt         # 降级用 SRT
  python3 tools/generate_titles.py episode.article.md --round 0
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

# ── 路径 ────────────────────────────────────────────────────────────────────────

_REPO_DATA = Path(__file__).parent.parent / "data"
_GUIDELINE = _REPO_DATA / "guideline_kedaibiao.md"
_TOP_TITLES = _REPO_DATA / "top_titles.txt"


# ── 资源加载 ────────────────────────────────────────────────────────────────────

def load_guideline() -> str:
    if _GUIDELINE.exists():
        return _GUIDELINE.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Guideline 不存在: {_GUIDELINE}")


def load_top_titles() -> str:
    if _TOP_TITLES.exists():
        return _TOP_TITLES.read_text(encoding="utf-8").strip()
    return ""


def find_highlights(content_path: Path, stem: str) -> str:
    """自动检测同目录下是否有 {stem}.highlights.md"""
    h_path = content_path.parent / f"{stem}.highlights.md"
    if h_path.exists():
        return h_path.read_text(encoding="utf-8")
    return ""


# ── SRT 文本提取 ────────────────────────────────────────────────────────────────

def srt_to_text(srt_path: Path, max_chars: int = 6000) -> str:
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
    text = " ".join(lines)
    return text[:max_chars] + "…（已截断）" if len(text) > max_chars else text


# ── Claude CLI ──────────────────────────────────────────────────────────────────

def call_claude(prompt: str, timeout: int = 900) -> str:
    result = subprocess.run(
        ["claude", "-p", "--model", "claude-opus-4-6", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        err = result.stderr.strip()
        raise RuntimeError(f"claude -p 失败 (exit {result.returncode}): {err[:200]}")
    return result.stdout.strip()


# ── Round 0：内容理解 + 高光驱动标题广撒网 ──────────────────────────────────────

ROUND0_WITH_HIGHLIGHTS = """\
你是课代表立正频道的资深标题编辑，深度理解频道受众心理。

## 频道 Guideline（你的判断基准）

{guideline}

---

## 视频高光片段（视频开头会展示的内容）

{highlights}

---

## 完整内容（背景参考）

{content}

---

## 你的任务

### Step 1：中心命题 + 受众扩展

**中心命题**：用一句话说出这期内容最想让观众相信/感受到什么。
不是"讲了什么话题"，而是"这期的核心论点/洞见"。

**受众扩展**：这个核心命题能触达哪些人？
- 频道现有受众（科技/职场/创业圈人群）
- 更广泛的潜在受众（命题涉及的更大议题是什么？谁会关心？）

标题应该能同时打动现有受众，也能吸引新的潜在受众进来。

### Step 2：标题与高光的关系

标题和高光的分工：
- **高光**（视频开头）：让观众看完前60秒感觉"这期有料，我要看完"
- **标题**：创造点击动机——不描述高光本身，而是描述高光背后更大的问题

**不能做的**：标题直接剧透高光里的答案或关键信息
**应该做的**：标题让人想看高光；高光让人想看完整视频

### Step 3：多角度广撒网（≥25 个候选标题）

基于 Guideline 里的六个入口，至少生成 25 个候选标题：
- 以高光内容和完整内容为依据（不发明内容里没有的事）
- 覆盖不同情绪：好奇 / 不安 / 认同 / 挑战
- 考虑不同受众入口：现有受众 AND 扩展受众
- **特别尝试**：[身份/权威] + [震撼陈述] + [核心问题] 这个结构——当内容有强力信源时特别有效

## 输出格式

## 中心命题
[一句话]

## 受众分析
- 现有受众：[谁，为什么关心]
- 扩展受众：[谁，这个命题如何触达他们]

## 标题与高光关系
[2-3句]

## 入口 1：命名听众已经有的问题
- 候选标题...

## 入口 2：指出一个普遍的误判
- 候选标题...

## 入口 3：一个具体的故事或时刻
- 候选标题...

## 入口 4：一个可以被命名的框架或概念
- 候选标题...

## 入口 5：揭示一个结构性的矛盾
- 候选标题...

## 入口 6：切开大问题的一个精准切口
- 候选标题...
"""

ROUND0_WITHOUT_HIGHLIGHTS = """\
你是课代表立正频道的资深标题编辑，拥有对该频道受众心理的深刻理解。

## 频道 Guideline（必读，是你的判断基准）

{guideline}

---

## 本期内容

{content}

---

## 你的任务

### Step 1：理解内容核心

用 3-4 句话回答：
- 这期内容最核心的洞见或反常识点是什么？
- 最有张力的故事或时刻是什么？
- 这期内容的独特性在哪里？

### Step 2：多角度广撒网（≥25 个候选标题）

基于 Guideline 里的六个入口，生成至少 25 个候选标题：
- 每个入口至少 3-4 个
- 每个标题必须有内容真实依据
- 追求多样性，不同情绪、不同受众切入点
- 不限格式（问句/陈述均可）

## 输出格式

## 内容核心价值
[3-4句]

## 入口 1：命名听众已经有的问题
- 候选标题...

（以此类推，六个入口全部输出）
"""


# ── Round 1：外部基准对比 + 差距分析 ──────────────────────────────────────────

ROUND1_PROMPT = """\
你是课代表立正频道的独立标题评审。

## 频道定位与受众（快速提示）

频道：帮听众把说不清楚的问题想清楚。主播人设：真的想清楚了再说的人。
受众：已经做得不错但感觉卡住的人，想要底层框架，反感说教和结论先行。
好标题三要素：制造真实好奇心 / 预告内容值得时间 / 让转发者显得清醒有判断。
失败模式：结论当标题 / 宽泛好事承诺 / 说教语气 / AI公文感。

---

## 频道真实高播标题（这是听众真正点击的东西——用它校准你的判断）

{top_titles}

---

{highlights_section}

## Round 0 候选标题

{round0}

---

## 评审任务

### Step 1：对比高播标准，选出 Top 12

把每个候选与上方高播标题做比较：如果这个标题出现在频道里，它能达到高播标题的吸引力吗？

选出 Top 12，每个给一句话理由（不超过15字）。

### Step 2：差距诊断

不要只说"缺少某种风格"，要说明：
- 这期内容最有价值的角度，在 Round 0 里有没有被充分探索？
- 有没有标题已经很接近，但某一个词用得不精准/不够有力？直接说哪个词、改成什么
- Round 0 整体有没有系统性问题（太抽象？太长？太多结论型？太依赖开头内容？）
{highlight_alignment_check}

### Step 3：给 Round 2 的具体指令（2-4条）

每条指令必须具体可执行：
- "利用内容里 X 这个细节重新生成" 而不是 "更具体"
- 如果有特别接近但差一口气的标题，直接引用原标题 + 说改哪里

## 输出格式

## Top 12
| 排名 | 标题 | 理由 |
|------|------|------|
...

## 差距诊断
[几段话]

## Round 2 指令
1. ...
2. ...
"""


# ── Round 2：补强 + 最终选题 ──────────────────────────────────────────────────

ROUND2_PROMPT = """\
你是课代表立正频道的终审编辑。这是最终决定。

{highlights_section}

## Round 0 全部候选

{round0}

## Round 1 评审（Top 12 + 差距诊断 + 指令）

{round1}

---

## 终审任务

### Step 1：按 Round 1 指令补充新标题

针对每条指令生成 3-5 个新标题，填补角度盲区。

### Step 2：最终 8-10 个标题 + 封面建议

从所有候选中最终选出 8-10 个。

**选择标准（按优先级）：**
1. **诚实性**：标题描述的东西，视频里确实有，且不剧透高光里的关键信息
2. **真实好奇心**：说出一个真的想知道答案的问题或悬念
3. **受众覆盖**：8-10个覆盖不同受众入口，包括扩展受众
4. **转发测试**：有独立判断的30多岁职场人愿意分享给想留印象的人

**禁止出现：** 结论全说完 / 宽泛好事承诺 / 说教语气

### Step 3：封面建议（前 5 个标题各一条）

封面和标题各司其职，互补而不重复：
- **标题**：建立认知期待，说清楚"这期讲什么问题，为什么值得点"
- **封面**：0.5 秒情绪锚点，"这个人有话要说"

**访谈视频封面策略**（主发言人是嘉宾时）：
从嘉宾原话中提炼/微调 **3 句金句**放在封面上。
选句标准：看到这句话，观众会想"我一定要知道这句话是在什么情况下说的"。
- 不是嘉宾观点摘要，而是让人必须点进来才能读懂完整含义的悬念型表达
- 可以轻微 paraphrase（压缩句子、删去主语），但不能夸大或背离原意
- 三句合在一起，给观众传递"这个嘉宾说话有分量"的印象

**单口视频封面策略**（主发言人是主播孙煜征时）：
封面主文字 **3-10 字**，有冲击力，是全期最强的判断或最刺痛的问题。
标题在封面文字基础上做延伸和阐释——封面一把刀，标题补上下文。

## 输出格式

## 补充标题
（按 Round 1 指令分组）

## 最终 8-10 个标题

| 排名 | 标题 | 入口 | 一句话说明 |
|------|------|------|-----------|
| 1 | ... | 入口X | ... |
...

## 封面建议（前 5 个标题）

### 标题 1「...」的封面
- 封面类型：[访谈/单口]
- 封面主内容：
  - 访谈：金句一「...」 / 金句二「...」 / 金句三「...」
  - 单口：「...」（3-10字）
- 画面：[谁在画面里，什么表情/状态/背景]
- 配合逻辑：[封面做什么，标题做什么，两者如何互补]

### 标题 2「...」的封面
...

## Runner-up（3-5个值得保留的备选）
- 标题（为什么没进前10）
"""


# ── 工作流 ───────────────────────────────────────────────────────────────────────

def run_round0(content: str, highlights: str, workspace: Path) -> Path:
    out = workspace / "round0_candidates.md"
    guideline = load_guideline()

    if highlights:
        prompt = ROUND0_WITH_HIGHLIGHTS.format(
            guideline=guideline, highlights=highlights, content=content
        )
    else:
        prompt = ROUND0_WITHOUT_HIGHLIGHTS.format(
            guideline=guideline, content=content
        )

    print("    Round 0：理解内容 + 多角度生成候选…", flush=True)
    result = call_claude(prompt, timeout=900)
    out.write_text(result, encoding="utf-8")
    print(f"    ✓ {out.name} 已写入")
    return out


def run_round1(round0: Path, highlights: str, workspace: Path) -> Path:
    out = workspace / "round1_review.md"
    r0 = round0.read_text(encoding="utf-8")
    top_titles = load_top_titles()

    if highlights:
        highlights_section = f"## 视频高光片段\n\n{highlights}\n\n---\n"
        highlight_alignment_check = "\n- Round 0 有没有标题与高光内容对齐但又不剧透高光？（这是最重要的一类标题）"
    else:
        highlights_section = ""
        highlight_alignment_check = ""

    prompt = ROUND1_PROMPT.format(
        top_titles=top_titles,
        highlights_section=highlights_section,
        round0=r0,
        highlight_alignment_check=highlight_alignment_check,
    )

    print("    Round 1：外部基准对比 + 差距诊断…", flush=True)
    result = call_claude(prompt, timeout=900)
    out.write_text(result, encoding="utf-8")
    print(f"    ✓ {out.name} 已写入")
    return out


def run_round2(round0: Path, round1: Path, highlights: str, final_out: Path) -> Path:
    r0 = round0.read_text(encoding="utf-8")
    r1 = round1.read_text(encoding="utf-8")

    if highlights:
        highlights_section = f"## 视频高光片段（标题必须与这些内容对齐）\n\n{highlights}\n\n---\n"
    else:
        highlights_section = ""

    prompt = ROUND2_PROMPT.format(
        highlights_section=highlights_section, round0=r0, round1=r1
    )

    print("    Round 2：补强 + 最终选题…", flush=True)
    result = call_claude(prompt, timeout=900)
    final_out.write_text(result, encoding="utf-8")
    print(f"    ✓ {final_out.name} 已写入")
    return final_out


# ── 主流程 ──────────────────────────────────────────────────────────────────────

def generate_titles(content_path: Path, stop_at_round: int = 2) -> Path:
    stem = content_path.with_suffix("").stem
    for suffix in (".article", ".final", ".corrected"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break

    base_dir = content_path.parent
    workspace = base_dir / f"{stem}_title_ws"
    workspace.mkdir(exist_ok=True)
    final_out = base_dir / f"{stem}.titles.md"

    # 读取主内容
    if content_path.suffix == ".md":
        content = content_path.read_text(encoding="utf-8")
        if len(content) > 6000:
            content = content[:6000] + "…（已截断）"
    else:
        content = srt_to_text(content_path, max_chars=6000)

    # 自动检测高光文件
    highlights = find_highlights(content_path, stem)
    if highlights:
        print(f"    ✓ 发现高光文件 {stem}.highlights.md，高光驱动模式启动")
    else:
        print(f"    ! 未找到高光文件，使用完整内容模式")

    r0 = run_round0(content, highlights, workspace)
    if stop_at_round == 0:
        return r0

    r1 = run_round1(r0, highlights, workspace)
    if stop_at_round == 1:
        return r1

    return run_round2(r0, r1, highlights, final_out)


def main() -> None:
    parser = argparse.ArgumentParser(description="课代表立正播客标题三轮生成 v3（高光驱动）")
    parser.add_argument("content", help="输入文件：.article.md 或 .final.srt")
    parser.add_argument(
        "--round", type=int, default=2, choices=[0, 1, 2],
        help="停在第几轮（0=只生成候选，1=+评审，2=完整）",
    )
    args = parser.parse_args()

    content_path = Path(args.content).resolve()
    if not content_path.exists():
        print(f"错误: 文件不存在: {content_path}")
        sys.exit(1)

    print(f"  标题生成：{content_path.name} …", flush=True)
    try:
        out = generate_titles(content_path, stop_at_round=args.round)
        print(f"  ✓ 标题已写入：{out.name}")
    except Exception as e:
        print(f"  ✗ 失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
