# 联网查找机制 × 质量保障

> 用途：当风格不确定、用户要“真实案例/最新编曲手法”、或 analyze 分数反复不达标时，用联网检索补充依据。
> 原则：**不锁定指定网站**，用模糊关键词多次检索；所有结论必须先过质量门槛，再落入 song.json / 提示词。

## 1. 什么时候必须联网

满足任一条件就执行联网检索，不能只靠本地知识库硬写：

1. 用户点名的风格不在 `styles/` 或 pattern-library 中
2. 用户要求“真实案例”“最新/流行/现在流行”的编曲手法
3. 本地没有可参考的真实 MIDI 或完整谱例
4. `analyze` 连续两次 < 7，且建议没有明显方向
5. 需要确认某个进行/和弦外音/结构是否符合真实歌曲用法

## 2. 模糊搜索词策略

不要只搜一个精确句子。第一轮用“宽泛 + 中英文各一组”，第二轮从结果里提取新词再细化。

第一轮示例：

```text
中文：电子音乐 编曲 旋律 和弦 教程
中文：House 编曲 风格 差异 歌曲分析
英文：house music arrangement melody chord tutorial
英文：electronic music chord progression real song analysis
```

第二轮示例（按第一轮结果细化）：

```text
deep house offbeat bass chord progression tutorial
tropical house melody writing marimba chord progression
future house stab sidechain melody analysis
电子音乐 和弦外音 经过音 真实歌曲 分析
给旋律配和弦 三音 根音 五音 优先级
```

规则：

- 关键词尽量“风格 + 目标 + 动作”：`House + 旋律 + 写作/拆解`
- 每轮至少 2–3 个查询，中英文混合
- 不指定站点，但优先看结果里的课程/教程/论文/官方文档/公开数据集
- 搜到的 URL 只作为证据来源，不作为搜索上限

### 2.1 按场景选查询模板（2026-08 增强）

| 场景 | 中文模板 | 英文模板 |
|------|----------|----------|
| 新风格摸底 | `{风格} 编曲 特点 和弦 教程` / `{风格} 歌曲分析 结构` | `{genre} production tutorial chords arrangement` / `{genre} track breakdown analysis` |
| 真实案例手法 | `{歌曲/艺人} 编曲分析 和弦` | `{song} harmonic analysis` / `{artist} production techniques` |
| 旋律/乐句问题 | `旋律 乐句结构 动机发展 教程` / `起承转合 作曲` | `melody writing phrase structure tutorial` / `sentence period form songwriting` |
| analyze 不达标 | 按建议关键词搜：`级进 跳进 旋律 可唱性` / `乐句 终止式` | `stepwise motion vs leaps singable melody` / `phrase cadence half authentic` |
| 量化验证 | `旋律 评价 指标 重复 研究` | `melody evaluation metrics repetition phrase boundary research` |

要点：查「怎么写」用教程词（tutorial/教程/分析）；查「怎么量化」用研究词（metrics/evaluation/corpus/research），
论文和课程页能给可编程的阈值（如级进占比 70%、大 IOI 预测乐句边界），比泛泛的感悟帖值钱。

## 3. 来源质量门槛

每条结论必须能回答下面至少 4 项：

| 检查项 | 通过标准 |
|--------|----------|
| 作者/平台 | 有署名作者、机构、课程体系或可验证的项目主页 |
| 具体性 | 给出和弦级数、音名、拍点、音轨分工或完整编曲步骤 |
| 例证 | 有真实歌曲、公开 MIDI、谱例、音频或逐步演示 |
| 可验证 | 音高/和弦可用 `aria-midi scale --chord` 复算，MIDI 可用 `aria-decode` 回读 |
| 一致性 | 至少 2 个独立来源说法一致；冲突时保留两种并说明 |
| 时效性 | 风格方法优先近期教程；经典乐理可用长期稳定来源 |

以下来源默认降权：

- 只有标题没有内容的营销页
- 纯“万能公式”无解释的帖子
- 无法验证、无作者、无例证的 AI 摘要
- 只给付费购买链接、不给任何方法细节的页面

## 4. 三轮检索流程

### 第一轮：收集

- 用宽泛关键词找 5–10 个候选结果
- 只看标题/摘要判断相关性，不深入

### 第二轮：筛选

- 打开 3–5 个最相关结果。**Agent 有浏览器/网页抓取工具（WebFetch、agent-browser 等）时，必须打开原文深读**，
  只凭搜索摘要下结论视为未验证；没有抓取工具时降级为「多来源摘要交叉验证」并在落库记录中注明
- 深读时优先提取**可操作参数**：具体级数/音名/拍点/BPM 区间/百分比阈值/小节数，
  而不是「要有起伏」「注意呼吸」这类无法落地的描述
- 提取：和弦进行、旋律规则、节奏型、段落结构、真实案例
- 每篇至少记下 2 条可执行要点

### 第三轮：交叉验证

- 用第二条不同的查询找同一主题的另外 2 个来源
- 冲突时记录：来源 A 说 X，来源 B 说 Y，选择依据是什么
- 音阶/和弦必须用 CLI 复算，不直接抄文字

## 5. 证据落库与提示词接入

把检索结果转成明确的编曲决策，写进 `song.json` 和交付摘要：

```text
联网检索记录：
- 检索词：House 编曲 旋律 和弦 教程 / house melody arrangement
- 采用来源：2 篇教程 + 1 个公开 MIDI 分析（列出标题/作者/URL）
- 落库结论：
  1. 和弦：Am7–Fmaj7–C–G7，每 2 小节换一个
  2. 旋律：Hook 从 0.75 反拍进入，2 小节原样重复一次
  3. 节奏：Kick 正拍，低音/Stab 反拍
  4. 验证：aria-midi scale --chord 已复算；真实 MIDI 已用 aria-decode 拆解
- 未采用结论与原因：来源 B 的连续 16 分旋律不符合本曲 126 BPM Deep House 听感
```

## 6. 质量红线

- 不整段复刻真实歌曲旋律；只学结构、节奏、和声规律
- 不把单篇文章当作唯一真理；风格判断至少 2 个来源
- 不把网页文字直接写进 JSON；先转成音高、拍点、力度
- 不跳过 CLI 验证：音阶/和弦用 `scale --chord`，MIDI 用 `aria-decode`
- 最终交付摘要必须列出：检索词、采用来源、落库结论、未采用结论

## 7. 离线降级

联网不可用时：

1. 用本地知识库和 `examples/midi/` 真实 MIDI 完成创作
2. 摘要注明 `联网检索：未完成（网络不可用），依据本地知识库`
3. 不把未联网验证的“新风格断言”写成事实；标记为待验证
4. 网络恢复后，按本指南补一轮检索并回填来源

## 8. 实战示范：乐句结构调研（2026-08，可作为执行模板）

需求：增强「模块化旋律结构」知识，需要可落地的乐句组织规则与可编程检测指标。

```text
检索记录：
- 第 1 轮（宽泛）：
  英：melodic coherence repetition variation phrase structure songwriting tutorial sentence period
  中：旋律 乐句结构 动机发展 起承转合 作曲教程 连贯性
- 第 2 轮（量化指标）：
  英：melody evaluation metrics phrase boundary detection long note rest n-gram repetition MIR
- 采用来源（6 个，已过 §3 质量门槛）：
  1. Motifkit《Musical Phrase Structure Explained (Period & Sentence)》——period=同头+半终止/全终止；sentence=呈示+重复+碎片化 continuation
  2. MUSIC 375《Songwriting: Analysis and Craft》——motif(2–5 音 building block) vs hook(4–8 小节完整实体) 层级；模进/音区变奏/节奏伸缩
  3. Secrets of Songwriting（2 篇）——AABA/AAAB/ABAB/AABC 图式 + 真实歌曲对照；「听众记形状不记音高」
  4. 李民雄《起承转合》（华音网）——四句体功能（起呈示/承巩固/转对比/合归结）；转句结构分裂；顶真
  5. Empirical Musicology《Is Melody "Dead"?》——压缩率测重复度；大 IOI 是乐句边界强预测因子（Pearce et al. 2010）
  6. arXiv 2608.19061——m-types：音程方向×IOI 比值联合表征，Simpson's D 测重复
- 落库结论：
  1. composition-rules.md 新增「规则 1 补充—模块化乐句结构」（四级组装 + 四大图式 + 三板斧）
  2. pattern-library.md §4.2 新增起承转合/顶真 + §4.2.1 流行重复图式表
  3. aria-midi analyze 1.2.0 新增 structure_score：乐句切分（休止≥0.5 拍/长音≥2 拍）、
     跨乐句轮廓复用（前 2 音程方向相同）、高潮位置（35%–90%）、终止稳定性（--key-root 时）
- 未采用与原因：Narmour IR 五原则完整实现（离散步数评分对短旋律噪声大，仅保留「大跳反解」已有规则）；
  GZIP 压缩率测重复（对 <50 音的短旋律不稳定，用 n-gram 轮廓复用替代）
```

这个示范同时说明：教程类来源（1–4）负责「怎么写」进入提示词，研究类来源（5–6）负责「怎么量化」进入工具——
一次调研同时喂提示词和 CLI，是本包联网机制的完整用法。
