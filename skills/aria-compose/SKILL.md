---
name: aria-compose
description: 自然语言音乐作曲工作流——把旋律、和弦进行、编曲想法写成 song.json 音符数据并生成标准 MIDI 文件。当用户要求"写/创作/生成 一段旋律、一首歌、背景音乐、MIDI、和弦进行、lo-fi、钢琴曲、电子音乐、伴奏"或任何需要产出可播放音乐文件的请求时触发，即使用户没有明说"作曲"二字。纯乐理知识问答（不产出音乐文件）改走 aria-music-theory。
metadata:
  version: "1.3.0"
  category: music
  author: aria
  requires:
    bins: [python]
---

# aria-compose — 自然语言作曲工作流

把用户的音乐想法变成标准 MIDI 文件。**你是作曲家**，`aria_midi.py` CLI 是你的落盘与校验工具。全流程离线运行，零 LLM API 依赖。

## 输出契约（必须全部交付）

放在**以歌名命名的目录**里（见「项目布局」）：

1. `<歌名>/song.json` — 音符数据，顶层 `name` = 歌名（schema 见 references/midi-schema.md）
2. `<歌名>/<歌名>.mid` — 标准 MIDI 文件（Type-1，TPQN=480），歌名写入序列名
3. 摘要（中文）— BPM / 调式 / 段落结构 / 音轨数 / 音符数 / 使用的和弦进行

## CLI 调用规范

`aria_midi.py` 与本技能同属一个技能包（`skills/` 与 `toolkits/` 同级）。按以下顺序定位：

1. 若 PATH 中已有 `aria-midi` 命令：`aria-midi <子命令> [参数]`
2. 否则用包内相对路径：`python <SKILL.md 所在目录>/../../toolkits/aria-midi/aria_midi.py <子命令> [参数]`
   （即「技能包根目录下的 toolkits\aria-midi\aria_midi.py」。示例：本技能位于
   `C:\Users\Mark\.agents\skills\aria-compose\` 时，CLI 即
   `C:\Users\Mark\.agents\toolkits\aria-midi\aria_midi.py`；
   位于 `D:\.agent\skills\aria-compose\` 时，CLI 即 `D:\.agent\toolkits\aria-midi\aria_midi.py`）

| 子命令 | 用途 | 退出码 |
|--------|------|--------|
| `validate --input song.json [--strict]` | 校验 schema/音域/力度/量化/重叠 | 0 通过 / 1 有错误 |
| `analyze --input song.json [--chords chords.json] [--key-root C4]` | 0–10 评分 + 中文改进建议 | 0 |
| `generate --input song.json [--output x.mid] [--bpm 120] [--name 歌名] [--outdir 目录]` | 生成标准 MIDI 文件；`--output` 可省（由顶层 name 派生） | 0 / 1 / 2 |
| `inspect --input song.mid` | 解析回读 .mid 自检 | 0 / 1 |
| `scale --root C4 --type major [--list/--chord/--snap/--suggest]` | 音阶/和弦计算查表 | 0 / 2 |

另有两个独立脚本（同为 aria-midi 工具包内，非子命令）：

| 脚本 | 用途 |
|------|------|
| `plan_check.py --plan p.json [--song s.json]` / `--derive s.json` | **计划层检查**：写音符之前查结构件、写完查实现 |
| `calibrate.py --corpus-dir DIR` | 用人写语料标定结构指标分位数（包内基线即它的产物） |

## 工具调用操作细节

### 命令定位

写音符前先用以下任一方式确认 CLI 可用：

```bash
aria-midi --version
# 或
python <SKILL.md 所在目录>/../../toolkits/aria-midi/aria_midi.py --version
```

返回版本号后再进入五步工作流；若返回命令不存在，优先用第二种相对路径，不要创建替代脚本或猜其他路径。

### 必须执行的命令序列

下面用 `<歌名>/` 表示「每首歌一个目录」的布局（见「项目布局」）。目录名与 song.json 顶层的
`name` 保持一致。

```bash
# 查表：音阶和和弦一律用 CLI 算，不心算
python <SKILL.md 所在目录>/../../toolkits/aria-midi/aria_midi.py scale --root C4 --type major --list
python <SKILL.md 所在目录>/../../toolkits/aria-midi/aria_midi.py scale --root G4 --type major --chord dom7

# 校验：每次写完/改完 song.json 都要执行
python <SKILL.md 所在目录>/../../toolkits/aria-midi/aria_midi.py validate --input <歌名>/song.json --strict

# 评分：低于 7 按 suggestions 改完重跑 validate
python <SKILL.md 所在目录>/../../toolkits/aria-midi/aria_midi.py analyze --input <歌名>/song.json --chords <歌名>/chords.json

# 生成与回读：--output 可省，由顶层 name 派生 <歌名>/<歌名>.mid
python <SKILL.md 所在目录>/../../toolkits/aria-midi/aria_midi.py generate --input <歌名>/song.json
python <SKILL.md 所在目录>/../../toolkits/aria-midi/aria_midi.py inspect --input <歌名>/<歌名>.mid
```

### 退出码与放行条件

| 退出码 | 含义 | 放行条件 |
|--------|------|----------|
| `0` | 成功 | `validate --strict` 必须为 `0`。**`analyze` 不参与放行**——它是诊断（总分在音符层面无梯度，见第 5 步） |
| `1` | 数据错误 | 不允许放行；读 `errors` / `warnings` 修正 |
| `2` | 用法/IO 错误 | 检查参数和文件路径后重试 |

### 输入输出约定

- `validate / analyze / generate` 的 `--input -` 表示从 stdin 读 song.json
- `generate` 的 `--output` 可省：song.json 顶层有 `name`（或用 `--name` 指定）时，
  输出派生为 `<输入目录>/<歌名>.mid`；两者都没有才视为用法错误（退出码 2）
- 生成前确认输出目录存在；CLI 不会自动创建目录
- 交付时保留 `<歌名>.json`、`<歌名>.chords.json`、`<歌名>.mid`、回读核对结果和中文摘要

### 项目布局（必须遵守，否则目录会乱）

**每首歌一个目录，`song.json` 顶层写 `name`。** 不要往项目根目录直接写 `song.json` ——
固定文件名会撞名，实际使用中会演变成 `sad.song.json`、`wd222.song.json` 这类前缀混战的局面。

```
<项目>/
└── <歌名>/                     # 目录名 = song.json 顶层的 name
    ├── plan.json              # 八层计划（曲式/和声/音区/织体/乐句四列/骨架/能量/动机）
    ├── song.json              # 谱面（{"name": "<歌名>", "bpm": ..., "tracks": [...]}）
    ├── chords.json            # 和弦进行（供 analyze 检查强拍匹配；可选）
    ├── <歌名>.mid             # 生成物，由 name 自动派生
    ├── build_<歌名>.py        # 生成脚本（长曲/有重复织体时用，见下）
    └── <歌名>.html            # 自包含播放器（如已生成）
```

```bash
# 命名一次，路径全自动 —— 无需再敲 --output
aria-midi generate --input 未寄出的信/song.json
#   → 未寄出的信/未寄出的信.mid（歌名同时写入 MIDI 序列名，DAW 里显示为曲名）
```

**诊断产物默认不落盘。** 回读核对、事件明细、解码结果都是「看一眼就扔」的中间物，
占体积的绝大多数（实测一次作曲过程中它们能占 87%）。优先用管道：

```bash
aria-decode decode --input 未寄出的信/未寄出的信.mid --output - | head -c 400
aria-midi inspect --input 未寄出的信/未寄出的信.mid        # 直接打到 stdout
```

确实需要留存时才写进歌曲目录，命名 `<歌名>.qa.json`，并在交付时说明它是可再生的。

### 长曲用生成脚本，不要手搓 JSON

超过约 16 小节、或伴奏有重复织体时，**写一个 `build_<歌名>.py` 生成 song.json**，而不是
手写几百个 JSON 对象。理由：

- **重复织体压成函数** —— 32 小节的左手伴奏可压缩成几行模式定义，改整段织体只需动几个数
- **返修成本低** —— 改一处重跑即可，不必在几百行 JSON 里定位
- **不会破坏网格** —— 手改 JSON 极易写出非 0.25 倍数的时值，得靠 validate 逐个报错才发现

脚本只做「音符 → song.json」的序列化，**不做乐理计算**（音阶和弦一律用 `aria-midi scale` 查表）、
不做校验、不写 MIDI —— 那些都交给工具链。短曲（如 4 小节）直接手写 song.json 即可。

### 生成后质检

`inspect` 只回读音符/音轨名/Tempo/拍号。需要检查 Tempo 变化、CC、弯音、歌词或 SysEx 时，用同一技能包内的 `aria-decode`：

```bash
python <SKILL.md 所在目录>/../../toolkits/aria-decode/aria_decode.py decode --input <歌名>.mid --output -
```

核对 `global.bpm`、`global.duration_sec`、`notes` 数量与 song.json 是否一致，不一致必须回到生成步骤排查。这一步默认走 stdout，不要落盘。

## 联网查找机制（写音符前）

遇到以下情况，先读 `references/web-research-guide.md` 并执行联网模糊检索：

1. 用户要求真实歌曲案例 / 最新编曲手法 / 特定新风格
2. 本地风格库没有对应子风格
3. `analyze` 连续两次低于 7，且本地建议不足以定位问题

检索规则：

- **不指定网站**：用中英文模糊关键词各搜 1–3 轮，再从结果中提取新词细化
- 至少筛选 3 个可验证来源；音阶/和弦用 `aria-midi scale --chord` 复算
- 有 MIDI 时用 `aria-decode` 拆解，不直接照抄文字
- 把检索词、采用来源、落库结论写进最终摘要
- 网络不可用时按 `references/web-research-guide.md` §7 离线降级，并在摘要标记

## 五步工作流

### 第 1 步：确认需求
明确：风格（流行/EDM/爵士/Tropical House…）、BPM、调式（默认 C major）、长度（默认 8 小节）、音轨需求（旋律/低音/和弦）。用户没说就选合理默认，但**不要每首都 C major + 120 BPM + I–V–vi–IV**；根据情绪选非常规组合，并在最终摘要中说明。

### 第 2 步：读知识库（写音符前必读）
- 先读 `references/composition-rules.md`（段落规范 + 和弦规范 + 7 大规则）
- 再读 `references/pattern-library.md`（**模式库**：和弦进行配方 / 伴奏织体 / 节奏律动 / 旋律发展技法 / 结构模板 / 情绪参数映射）
- 写旋律/配和弦前再读 `references/melody-chord-writing.md`（强拍和弦音骨架 / 和弦外音分型 / 真实编曲案例）
- 按风格读 `../aria-music-theory/references/styles/` 对应文件：流行→`pop-music.md`、电子→`edm-production.md` + `electronic-arrangement.md`、爵士→`jazz-improvisation.md`、Tropical House→`tropical-house.md`、G-House 暗黑→`g-house.md`、通用技巧→`techniques.md`
- 写 House / 拆 MIDI 前读 `../aria-music-theory/references/house-melody-analysis.md` + `examples/midi/` 真实案例
- 再读 `../aria-music-theory/references/theory-arrangement.md`（乐理功能 + 声部进行 + 风格化编曲提示词模板）
- 用 CLI 查表，不要心算：
  ```bash
  aria-midi scale --root C4 --type major --list        # 音阶音
  aria-midi scale --root G4 --type major --chord dom7  # 和弦音
  ```

### 第 3 步：写 `plan.json`（八层计划）→ 跑计划检查

**先写计划，再写音符。** 计划层是梯度的来源：没有目标，就只剩"满足禁令"。
字段与完整示例见 `references/plan-schema.md`；人写作品里提取出的可执行语法见
`references/human-grammar.md`（九条，含"动机只要三个音""每小节固定位置呼吸"等可直接抄的写法）。

1. **曲式**：2–5 段，每段给 `label` 与 `function`（establish/develop/contrast/climax/release）
2. **和声**：逐小节声明进行；**每段末尾标注终止式**（正格/半/变格/阻碍）。和声可以放心循环——
   实测 Wait Day 的实质和声是 G–Am 交替、F-G-Am-G 循环 12 遍，仍然好听；缺陷是"各层同周期"
   而不是"循环"本身
3. **音区**：给每个声部声明 `band`；**多声部时间隔 ≥7 半音**（机写常见毛病是旋律与伴奏相撞）
4. **织体**：≥2 种，且密度随段落变化（不是常数）
5. **乐句四列**（**本层最关键**）：每句写下 `start` / `goal` / `breath` / `cadence`——
   起音、**目标音**、呼吸点、终止音。目标音是让"该往哪走"变得可见的唯一手段
6. **骨架**：声明全曲最高音 `climax:{bar,note}`
7. **能量**：逐段 `level`，至少一处起伏
8. **动机**：定义级数 `degrees` + 出现排期 `appearances`，**≥2 次出现且含 ≥1 次非原样**
   （transpose/invert/retrograde/augment/truncate…）

```bash
aria-midi plan_check --plan <歌名>/plan.json          # 计划层：门必须全过
```
门的划分与理由见 `plan-schema.md`；**凡"统计位置/风格选择"类一律只作提示**——
实测 Wait Day 在"全 4 倍数段落""29% 高潮""单声部""终止音不交替"四项上都会被误伤，
所以它们进的是提示栏。

> 已有旧作想补计划：`plan_check --derive <歌名>/song.json --chords <歌名>/chords.json --out <歌名>/plan.json`

### 第 4 步：写 song.json（照着计划实现，不是照着规则凑）
- 每个音都在实现计划：**强拍落和弦音**、乐句走向 `goal`、在 `breath` 处留空当、句末落 `cadence`
- 骨架音先定死（每句的起音/目标音/终止音），再填其余音符——**先骨架后填充**
- 动机按 `appearances` 排期出现，每次至少变一个元素
- 所有 start_beat / duration 必须是 0.25 的整数倍

**规则速查仍是默认值，但不再当门**（详版见 composition-rules.md；证伪清单见 anti-formula.md §5）：
动机驱动 / 强拍和弦音 / 节奏呼吸 / 力度弧线 / 跳级平衡 / 段落对比 / 人性化。
有意打破时读 `references/anti-formula.md`，每次只打破 1–2 条，并在摘要中记录
`打破规则：X，目的：Y`。

写完音符，**再查一次计划有没有被实现**：
```bash
aria-midi plan_check --plan <歌名>/plan.json --song <歌名>/song.json
# 查：骨架音/目标音是否真的出现、呼吸点是否真是空隙、最高音是否等于声明值、
#     声部是否落在音区带内、动机首次陈述是否按计划级数出现
# 注意：用 --derive 反推的计划自查必然通过（它就是从那些音符抄的）——
#       实现层要有牙齿，计划必须是独立写下的
```

### 第 5 步：验证 → 生成 → 自检（**analyze 是诊断，不是闸门**）
```bash
aria-midi validate --input <歌名>/song.json --strict     # ← 唯一的硬闸：必须 0 errors
aria-midi analyze  --input <歌名>/song.json --chords <歌名>/chords.json --key-root C4 --baseline
# ⚠️ 放行条件里**没有分数**。总分在音符层面是平的：把一个旋律音在 ±7 半音内遍历 15 个候选，
#    实测总分一分不动（四拍恒 8.0 / 余温恒 9.0 / 未寄出的信恒 10.0）。零梯度的分数
#    既不能指方向，也不该当闸门——它只用来读 details 与 suggestions。
# 看什么：
#   1) --baseline 的 role=diagnostic 三项落点（breaths_per_beat / step_share /
#      breath_position_consistency）。落在 p05~p95 之外才提示，**并且只在两端都是病时才提**
#      （breaths_per_beat=0 是四拍的病，>0.5 是霓虹夜行的病；实测 Wait Day 0.11 落在区间内）
#      ⚠️ 名字里带 window_ 的指标按 4 拍窗口算——语料里没有可识别的真实小节，
#         非 4/4 的作品请按"窗口"读，不要按"小节"读
#   2) details 里的线条四项：sounding_ratio / scalar_run_mean / continuity_points /
#      phrase_ending_alternation
#   3) role=style 与 role=convention_dependent 的指标**一律不判**——已知好作品会落在分布外
#      （Wait Day 在 6 项指标上超出 p05~p95），拿它们当闸门会误伤
# 真正的放行条件：validate 0 错误 + 人耳听过（见下）
aria-midi generate --input <歌名>/song.json             # --output 可省，派生 <歌名>/<歌名>.mid
aria-midi inspect  --input <歌名>/<歌名>.mid             # 核对音符数/BPM 往返一致
# 与参考人写作品对风格（风格敏感时）：aria-midi compare --input <歌名>/song.json --reference examples/midi/xxx.mid
```

**最终判据是耳朵。** `analyze` 无法判断"好不好听"（见 composition-rules.md §7 与
anti-formula.md §5）：交付前用 `aria-roll` 出 HTML，至少自己听一遍；有条件时按
"旋律性 / 结构感 / 自然度"三个维度与一首真实作品盲听对比，**别只给"好不好听"一个总评**。

### 第 6 步：风格锚定（对标真实案例，风格敏感时执行）
```bash
# 产出与 examples/midi/ 的真实案例对比，验证风格是否跑偏
aria-midi compare --input <歌名>/song.json --reference examples/midi/tropical-demo.mid
# 判「风格偏离」→ 按 dimensions 里偏离的维度（尤其 step_ratio 级进占比）回第 3 步调整
# 参考案例清单：deephouse-demo.mid(126) / tropical-demo.mid(112) / lofi-demo.mid(75)
```

## 作曲规则速查（详版见 references/composition-rules.md）

> 默认规则 + 豁免清单见 `references/anti-formula.md`。

1. **动机驱动**：短动机 × 变奏发展，禁止连续上下行音阶
2. **和弦音停留**：强拍必须是和弦音；非和弦音只作弱拍经过音
3. **节奏呼吸**：每 1–2 拍后休止；乐句间 0.5–1 拍呼吸
4. **力度弧线**：乐句内钟形/线性弧线，动态范围 ≥15
5. **跳级平衡**：≥4 半音大跳后反向级进解决
6. **段落对比**：副歌比主歌更高、更响、更密
7. **人性化**：相邻音符力度不同；每次重复至少变 1 个元素

## 质量检查清单（交付前逐项打勾）

**计划层（写音符之前）**
- [ ] `plan_check --plan <歌名>/plan.json` **门全过**；不通过就回第 3 步改计划，别去改音符
- [ ] 乐句四列齐全，特别是**每句都有 `goal`（目标音）**——没有目标就只能约束满足
- [ ] 动机 ≥2 次出现且含一次非原样（transpose/invert/…），排期写进了 `appearances`

**实现层（写完音符之后）**
- [ ] `validate --strict` 通过（0 errors）——**唯一的硬闸**
- [ ] `plan_check --plan <歌名>/plan.json --song <歌名>/song.json` 实现层全过
      （骨架音/目标音真的出现、呼吸点是真空隙、最高音等于声明值、声部在音区带内）
- [ ] `analyze --baseline` 跑过：`role=diagnostic` 三项没有落在 p05~p95 之外（落在外面才需要看，
      且只在"两端都是病"时才算问题）；`role=style` / `convention_dependent` 一律不判
- [ ] **人耳听过**：`aria-roll` 出 HTML 自己听一遍；有条件时与真实作品盲听对比三个维度

**参考（只读，不作门）**
- [ ] 线条四项：`sounding_ratio` ≥0.8、`scalar_run_mean` ≤1.5、`continuity_points` ≥2.5、连奏率 ≥0.75
- [ ] 没有踩反模式（§3.5.3 六条 + anti-formula.md §5 证伪清单）
- [ ] 强拍和弦音命中率 `chord_tone_rate` ≥ 60%
- [ ] `generate` + `inspect` 往返：音符数、BPM、时长一致
- [ ] 产物落在 `<歌名>/` 目录里（`plan.json` / `song.json` / `chords.json` / `.mid` / `.html`）、
      `song.json` 顶层有 `name`；没有往项目根目录丢 `song.json`
- [ ] 诊断产物（回读/事件明细/解码结果）未落盘，或已落盘但标注为可再生
- [ ] 摘要包含 BPM / 调式 / 段落 / 音轨 / 和弦进行 / 乐句图式 / 动机与再现位置

## 最小示例

用户："写 4 小节 C 大调旋律" → 建目录 `小星星/`，先写 `小星星/chords.json`（C 全曲），再写 `小星星/song.json`：

```json
{
  "name": "小星星",
  "bpm": 120,
  "tracks": [{
    "name": "旋律",
    "channel": 0,
    "program": 0,
    "notes": [
      {"pitch": 67, "start_beat": 0.0, "duration": 0.5, "velocity": 95},
      {"pitch": 69, "start_beat": 1.0, "duration": 0.75, "velocity": 100},
      {"pitch": 72, "start_beat": 2.0, "duration": 1.0, "velocity": 105},
      {"pitch": 64, "start_beat": 3.5, "duration": 0.5, "velocity": 80}
    ]
  }]
}
```

完整范例（流行副歌 / EDM Build-up / 爵士 Walking Bass，含低音轨）见 references/examples.md。

## 常见报错修复

| validate/analyze 报错 | 修法 |
|----------------------|------|
| 音高越界 | 限定 36–96 旋律区（绝对范围 0–127） |
| 力度越界 | 改到 1–127 |
| 非 0.25 量化（off grid） | start/duration 改为 0.25 的整数倍 |
| 同音高重叠 | 缩短前音符或后移后音符 |
| chord_tone_rate 低 | 把强拍音符移到和弦音上 |
| 力度范围小 | 重新设计力度弧线（极差 ≥15） |
| 连奏过多/无休止 | 乐句间插入 0.5–1 拍空隙 |

## Reference Files

| 文件 | 何时读 |
|------|--------|
| `references/composition-rules.md` | 每次写音符前必读（段落+和弦+7 规则+**§3.5 情感线与线条**+§7 阈值局限+清单） |
| `references/pattern-library.md` | **规划结构时必读**（进行配方/织体/节奏/旋律技法/结构模板/情绪映射） |
| `references/melody-chord-writing.md` | **写旋律/配和弦时必读**（强拍和弦音、和弦外音、真实歌曲与编曲案例） |
| `references/web-research-guide.md` | 风格未知 / 真实案例 / analyze 不达标时必读：模糊联网检索与质量门槛 |
| `references/midi-schema.md` | 不确定 JSON 字段/约束/GM 音色时 |
| `references/examples.md` | 需要完整范例参考时 |
| `references/plan-schema.md` | **写 plan.json 时必读**（八层字段 + 门/提示的划分 + 反向验收） |
| `references/human-grammar.md` | **写旋律前必读**（从真实作品提取的九条可执行语法） |
| `references/anti-formula.md` | 写第二稿时必读：打破公式、制造记忆点 |
| `../aria-music-theory/references/styles/*.md` | 按风格需要（流行/EDM/爵士/Tropical/通用） |
| `../aria-music-theory/references/electronic-arrangement.md` | 写电子音乐前必读：EDM 乐理 + 舞曲结构 + 提示词模板 |
| `../aria-music-theory/references/house-melody-analysis.md` | 写 House 前必读：真实 MIDI 拆解 + 多风格旋律对照 |
| `../aria-music-theory/references/theory-arrangement.md` | 配和弦/写多轨/做风格化编曲前必读 |
