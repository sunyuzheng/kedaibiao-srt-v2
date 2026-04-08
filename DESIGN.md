# kedaibiao-srt v2 · 设计文档

> 综合两个项目的经验：kedaibiao-channel（历史批量处理）和 kedaibiao-srt（新视频处理）

---

## 一、两个项目在做什么

### kedaibiao-channel（历史存量）
- **位置**：`/Users/sunyuzheng/Desktop/AI/content/kedaibiao-channel/`
- 689 个历史视频的下载、转录、校对、上传到 Transistor 播客平台
- 有 **171 个视频同时具备 Qwen 转录 + 人工精校字幕**（gold pair 数据集）
- 从这 171 对里提炼出了 **13,562 条错误对**（error_notebook.jsonl）
- 有完整的评估框架：CER + Precision + 候选词 Recall

### kedaibiao-srt（新视频）
- **位置**：`/Users/sunyuzheng/Desktop/AI/content/kedaibiao-srt/`
- 新录制视频的一体化处理：拖入视频 → 转录 → 校对 → 下载字幕
- 校对引擎 correct_srt.py v3：六层流程（全局上下文 + 风险打分 + 滑窗校对 + 二次审核 + 音频复查）

---

## 二、两种校对策略的对比结果

| 项目 | 策略 | CER 改善 | Precision | 回归率 |
|------|------|----------|-----------|--------|
| kedaibiao-channel v7 | 候选词驱动，LLM 只对 flags 表态 | **+1.50pp** | **91.2%** | 0% |
| kedaibiao-srt v3 | 全局上下文 + LLM 自由改写 | +0.06~0.59pp | 未测 | 未测 |

**v7 的简单保守策略反而比 v3 的复杂六层策略好 3 倍以上。**

原因分析：
- v3 让 LLM 自由改写，带来了误改（把对的改错）
- v3 的全局上下文提炼是从已经出错的 Qwen 文本里反推，先天有偏
- v7 只改有证据支持的已知错误模式，坏情况几乎全可追溯

---

## 三、现有数据资产（可直接利用）

### 3.1 错误知识库（kedaibiao-channel/logs/）

| 文件 | 内容 | 价值 |
|------|------|------|
| `error_notebook.jsonl` | 13,562 条 Qwen→人工 错误对，含上下文 | 最核心的 ground truth |
| `error_notebook_stats.json` | 按频率排列的 top-100 错误对 | 快速了解哪些错最高频 |
| `error_guide.md` | 864行，含示例的错误模式说明 | 供 LLM 理解上下文用 |
| `few_shot_examples.jsonl` | 60 条精选示例 | 供 LLM few-shot 用 |
| `correction_candidates.json` | 12 条高置信度替换规则 | 规则级直接执行（数字格式）|

### 3.2 Top 高频错误对（可做成规则的）

| 错误方向 | 频次 | 类型 | 可规则化？ |
|----------|------|------|------------|
| 它↔他 | 169次双向 | 指代代词 | 否（需上下文） |
| 就↔这 | 83次双向 | 语气词 | 否（需上下文） |
| 在↔再 | 61次双向 | 虚词 | 否（需上下文） |
| 边↔面 | 69次双向 | 方位词 | 否（需上下文） |
| 嘛↔吗 | 57次双向 | 语气词 | 否（需上下文） |
| **亚→鸭** | 21次单向 | **嘉宾名** | **是（高置信度）**|
| 百分之十→10% | 26次 | 数字格式 | **是（规则直接换）** |
| 百分之百→100% | 20次 | 数字格式 | **是（规则直接换）** |
| 两百→200 | 34次 | 数字格式 | **是（含 boundary guard）** |
| 两千→2000 | 15次 | 数字格式 | **是（含 boundary guard）** |

核心发现：**代词混淆（它/他/她/那/这）必须靠 LLM 判断，不能规则化。数字格式和确定性嘉宾名可以规则化。**

### 3.3 171 对 Qwen+人工 SRT（最未开发的资产）

当前只用了其中 2025+ 日期的子集做错题本。还没做过：
- **从人工精校 SRT 中提炼「频道词汇表」**：所有视频里出现过的正确形式（人名、品牌名、技术术语）
- **按视频主题聚类**：不同嘉宾带来不同的术语集合，需要区分

---

## 四、核心问题诊断

### 4.1 最高优先级的漏洞：新嘉宾/新术语

v7（和 v3）都无法解决的问题：**第一次出现的正确词形**。

例子：
- 「刘嘉」vs「刘佳」：Qwen 听到 jiā 写成了同音字，系统没有任何先验知道这里该是哪个字
- 「Dr. Sun」vs「Dr. 孙」：英文名被 Qwen 转成汉字，没有规则能反向纠正
- 「Superlinear Academy」vs「Superlillian Academy」：Qwen 完全乱造，需要知道正确名字

**这个问题的正确解决方式：在转录之前输入，而不是在转录之后纠错。**

### 4.2 次优先级的漏洞：频道累积术语没有形成词表

171 个视频的人工精校字幕里，正确写法已经存在：鸭哥、课代表立正、Statsig、Superlinear、桑提亚……但这些词没有被系统性提取出来作为热词库。

### 4.3 错题集注入 LLM 的价值评估

**`error_guide.md` 注入 LLM system prompt：价值有限。**
- 代词混淆（它/他）：LLM 不用 guide 也会判断
- 语气词（嘛/吗）：LLM 判断能力足够，不需要提示
- 频道专有词（鸭哥）：静态列表无法覆盖新嘉宾

**`correction_candidates.json` 作为规则执行：有价值。**
- 12条数字格式规则，高置信度，不需要 LLM
- 应该在转录完成后、LLM 校对前，直接规则替换

**结论：停止把 error_guide 注入 LLM prompt。把 candidates 的执行提前到规则层。LLM 只处理上下文判断类问题。**

---

## 五、从 171 对数据中提取频道词汇表（最高价值的工程任务）

这是当前最未开发的资产，也是最能改善新视频处理质量的杠杆点。

### 5.1 目标

从 171 个人工精校 SRT 中提取：
1. **频道固定词汇**：在 ≥3 个视频中都出现的术语（鸭哥、Statsig、Superlinear、桑提亚）
2. **Qwen 容易出错但人工字幕有正确形式的词**：从 error_notebook 对应的 human 侧提取
3. **英文术语正确拼写**：人工字幕里的英文词，这是 Qwen 最容易写错的

### 5.2 实现思路（新脚本：`extract_channel_vocab.py`）

```python
# 从所有人工精校 SRT 中提取词汇
# 步骤：
# 1. 扫描所有 .zh.srt 文件
# 2. 提取所有英文词（正则：[A-Za-z][A-Za-z0-9\-\.]*）
# 3. 提取所有人名候选（大写开头的中文2-3字词）
# 4. 按出现频率排序
# 5. 与 Qwen 版本对比，找出哪些词在 Qwen 里写法不同

# 输出：channel_vocab.json
{
  "persistent_terms": [      # 频道固定词汇，可直接做 hotwords
    "鸭哥", "Statsig", "Superlinear", "桑提亚", "课代表立正"
  ],
  "english_corrections": [   # 英文词的 Qwen 写法 → 正确写法 mapping
    {"qwen": "Superlillian", "correct": "Superlinear"},
    {"qwen": "Static", "correct": "Statsig"}
  ],
  "name_corrections": [      # 人名 mapping
    {"qwen": "亚哥", "correct": "鸭哥"},
    ...
  ]
}
```

### 5.3 如何使用这个词汇表

**在转录时：** 把 `persistent_terms` 作为 initial_prompt 的一部分传给 Qwen3-ASR

**在校对时：** 把 `english_corrections` 和 `name_corrections` 作为高置信度规则，规则层直接执行，不走 LLM

---

## 六、v2 流程设计

```
┌─────────────────────────────────────────────────────────┐
│  准备阶段（每期视频开始前）                               │
│                                                         │
│  1. channel_vocab.json（从171对数据提取，一次性生成）    │
│  2. 用户输入：本期嘉宾名 + 特有术语                      │
│     → 合并成本次的 episode_seeds                        │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  转录阶段                                                │
│                                                         │
│  Qwen3-ASR(initial_prompt=episode_seeds) → .qwen.srt   │
│  → 后处理：correction_candidates.json 规则替换          │
│    （数字格式，不走LLM，100%确定性）                     │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  校对阶段（LLM，候选词驱动，v7 策略）                    │
│                                                         │
│  1. 全文实体一致性检查                                   │
│     → 找出同一名字的不同写法（如刘嘉/刘佳各出现几次）    │
│     → 少数服从多数 + seeds 优先，统一形式                │
│  2. 候选词扫描 → flags                                   │
│     LLM 逐 flag 表态（KEEP/修改），给出理由              │
│  3. 验证层：拒绝幻觉，拒绝大幅改写                       │
│  4. 生成校对报告（改了什么/为什么/哪些还不确定）          │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  输出                                                    │
│  → .corrected.srt                                       │
│  → correction_report.txt（人读的，不是机器用的）         │
└─────────────────────────────────────────────────────────┘
```

---

## 七、错题集的新定位

不是注入 LLM prompt 的 system instruction，而是：

| 用途 | 内容 | 机制 |
|------|------|------|
| **规则层直接执行** | 数字格式（百分之十→10%）| correction_candidates.json，转录后规则替换 |
| **高置信度候选词** | 亚→鸭，Static→Statsig 等 | candidates 扩展，LLM 对 flag 表态 |
| **LLM 参考上下文** | 它/他/她 类代词混淆的上下文例句 | 少量注入 prompt（只放最有价值的5-8条），不是全量 |
| **eval 基准** | 29个视频的 GOOD/BAD 判定 | precision_eval.py |

---

## 八、Qwen3-ASR 的 initial_prompt 验证

需要验证：`mlx-qwen3-asr` 是否支持 `initial_prompt` 或 `hotwords` 参数。

```python
# 测试方案
from mlx_qwen3_asr import Session
session = Session("Qwen/Qwen3-ASR-1.7B")

# 尝试1：initial_prompt
result = session.transcribe(
    audio_path,
    language="Chinese",
    initial_prompt="本期嘉宾刘嘉，Superlinear Academy，课代表立正",
)

# 尝试2：如果不支持，看是否有 hotwords 参数
result = session.transcribe(
    audio_path,
    language="Chinese",
    hotwords=["刘嘉", "Superlinear Academy", "课代表立正"],
)

# 如果都不支持：转录后规则替换（精确匹配 hotwords 的变体）
```

---

## 九、文件计划

### 新建脚本

| 脚本 | 功能 | 优先级 |
|------|------|--------|
| `tools/extract_channel_vocab.py` | 从 171 对数据提取频道词汇表 | **P0** |
| `tools/transcribe_with_seeds.py` | 封装 Qwen 转录 + hotwords + 规则替换 | P0 |
| `tools/check_entity_consistency.py` | 全文实体一致性检查 | P1 |

### 复用/修改

| 脚本 | 来源 | 改动 |
|------|------|------|
| `tools/correct/correct_srt.py` | kedaibiao-channel v7 | 加入 entity enforcement，去掉 error_guide 注入 |
| `tests/eval_quality.py` | kedaibiao-srt | 加入时间对齐比较（只比较两边都有内容的段落）|
| `logs/correction_candidates.json` | 两个项目合并 | 合并数字格式规则 + 频道词汇 |

### 数据路径

```
# 源数据（不复制，直接引用）
CHANNEL_ARCHIVE = "/Users/sunyuzheng/Desktop/AI/content/kedaibiao-channel/archive/"
ERROR_NOTEBOOK  = "/Users/sunyuzheng/Desktop/AI/content/kedaibiao-channel/logs/error_notebook.jsonl"

# v2 输出
CHANNEL_VOCAB   = "/Users/sunyuzheng/Desktop/AI/content/kedaibiao-srt-v2/data/channel_vocab.json"
```

---

## 十、优先级排序

| 优先级 | 任务 | 预期收益 | 难度 |
|--------|------|----------|------|
| **P0** | 写 `extract_channel_vocab.py`，从171对数据提取词汇表 | 建立频道词汇先验 | 中（1天）|
| **P0** | 验证 Qwen3-ASR 的 initial_prompt/hotwords 支持 | 直接消灭新嘉宾同音字问题 | 低（半天）|
| **P0** | 在 UI/CLI 加「本期嘉宾+术语」输入入口 | 流程级改善 | 低（2小时）|
| **P1** | 基于 channel_vocab 扩展 correction_candidates | 覆盖频道高频正确词 | 低（半天）|
| **P1** | 全文实体一致性检查 | 兜底：转录后还有变体就扫一遍 | 中（1天）|
| **P1** | 把 correction_candidates 执行提前到转录后（去掉 LLM 中介）| 数字格式 100% 准确 | 低（2小时）|
| **P2** | 精简 LLM prompt，去掉 error_guide 全量注入 | 减少干扰 | 低（2小时）|
| **P2** | eval 改进：时间对齐比较 | 评估数字更可信 | 中（1天）|

---

## 十一、已知不做的事

- 不换 ASR 模型（Qwen 已够好，问题在术语注入，不在模型）
- 不做 diarization（多说话人识别）——当前内容不需要
- 不做端到端重训（数据量不够，维护成本太高）
- 不重做 v3 六层流程（已证明 v7 保守策略效果更好）
