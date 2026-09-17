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
| `0` | 成功 | `validate` 必须为 `0`；`analyze` 还需 `score >= 7` |
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

### 第 3 步：规划结构（套用模式库）
1. **段落**（3–5 段）：按 pattern-library.md §5 选结构模板（流行 ABABCB / AABA / EDM 能量曲线 / Lo-fi 循环），标注各段小节数、音域、力度、密度
2. **和弦进行**：按情绪查 pattern-library.md §1.7 决策表 → 选 §1 配方（如欢快流行用 I–V–vi–IV、日系抒情用 4536、悲伤用 i–VII–VI–V），写入 `chords.json`（供 analyze 检查强拍匹配）
3. **乐句模块化规划**（连贯性的关键，2026-08 联网调研增强）：每段内部按「动机 → 乐节 → 乐句 → 乐段」四级搭建，先把乐句计划写成表格再写音符：
   - **选乐句图式**：起承转合四句体（a–a'–b–a'，华语/民谣默认）/ Period 4+4（前句半终止、后句全终止，同头异尾）/ Sentence 2+2+4（动机+模进+碎片化终止）/ AABA·AAAB·ABAB·AABC（流行乐句重复图式）——配方见 pattern-library.md §4.2/§4.2.1
   - **定乐句终止点**：逐句写下结束音——问句落属音/上主音（开放），答句与末句落主音（收束）；全曲最后一音必须是主音长音（≥2 拍）
   - **标高潮位置**：全曲最高音落在 50%–80% 处（拱形轮廓），主歌不得提前用掉
   - **同头原则**：相邻乐句共享前 2–3 音的音程走向，只改结尾（analyze 的 contour_reuse_pairs 会检查这一点）；可用「顶真」——后句第一音 = 前句结束音
4. **织体与节奏**：从 §2 选伴奏织体（Alberti/琶音/半分解/柱式/stride/oom-pah/waltz/八度低音）、从 §3 选节奏律动（流行切分/爵士 comping/EDM 鼓组）
5. **音轨分工**：低音 36–50 / 和弦 48–67 / 旋律 60–84，逐轨完成（先旋律后低音）

### 第 4 步：写 song.json（动机式作曲）
严格按 composition-rules.md 的 7 大规则逐个音符写：
- 先发明 2–5 音动机，再发展（重复→移调→变奏）
- 强拍（4/4 的第 1、3 拍）必须落在当前和弦的和弦音上
- 每 1–2 拍后留 0.25–0.5 拍休止；乐句间留 0.5–1 拍呼吸
- 力度成弧线（乐句内极差 ≥15），相邻音符力度不可相同
- 大跳（≥4 半音）后反向级进解决；时值至少混用 3 种
- 所有 start_beat / duration 必须是 0.25 的整数倍

规则是默认值，不是判决：有意打破时读 `references/anti-formula.md`，每次只打破 1–2 条，并在摘要中记录 `打破规则：X，目的：Y`。

### 第 5 步：验证 → 生成 → 自检（循环直到达标）
```bash
aria-midi validate --input <歌名>/song.json --strict     # 必须 0 errors
aria-midi analyze  --input <歌名>/song.json --chords <歌名>/chords.json --key-root C4
# 放行条件：score ≥ 7 且 passed=true（技术分与音乐性分都要 ≥6），缺一回到第 4 步
# 连贯性条件：structure_score ≥ 6（1.2.0 起新增的第三栏：乐句切分/轮廓复用/高潮位置/终止稳定），
#   低于 6 优先看 details.structure 与 suggestions——通常是「只切出 1 个乐句」「乐句同头缺失」
#   「末句没落主音」三类问题，回第 3 步修乐句计划比重写音符省力
# 传 --key-root 才会检查终止稳定性（末句落主音/倒数句半终止），调式从第 1 步的需求来
# 跳进型风格（爵士/琶音/蓝调/EDM/Lo-fi）用 --style jazz 等显式豁免级进占比约束，
# 不要在 melodic 模式下靠「保留并记录理由」硬扛跳进扣分
aria-midi generate --input <歌名>/song.json             # --output 可省，派生 <歌名>/<歌名>.mid
aria-midi inspect  --input <歌名>/<歌名>.mid             # 核对音符数/BPM 往返一致
```

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

- [ ] `validate --strict` 通过（0 errors）
- [ ] `analyze` 分数 ≥ 7 且无未处理建议；`structure_score` ≥ 6
- [ ] 乐句计划已执行：每段选定乐句图式（起承转合/period/sentence/AABA 系），逐句终止点符合「问句开放、答句收束、末句主音」
- [ ] 每个音轨音域符合分工（低音 36–50 / 和弦 48–67 / 旋律 60–84）
- [ ] 强拍音符落在 chords.json 定义的和弦音上（chord_tone_rate ≥ 60%）
- [ ] 全曲至少 2 处明显休止；力度极差 ≥ 15；最高音在 50%–80% 处
- [ ] `generate` + `inspect` 往返：音符数、BPM、时长一致
- [ ] 产物落在 `<歌名>/` 目录里、`song.json` 顶层有 `name`；没有往项目根目录丢 `song.json`
- [ ] 诊断产物（回读/事件明细/解码结果）未落盘，或已落盘但标注为可再生
- [ ] 摘要包含 BPM / 调式 / 段落 / 音轨 / 和弦进行 / 乐句图式

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
| `references/composition-rules.md` | 每次写音符前必读（段落+和弦+7 规则+清单） |
| `references/pattern-library.md` | **规划结构时必读**（进行配方/织体/节奏/旋律技法/结构模板/情绪映射） |
| `references/melody-chord-writing.md` | **写旋律/配和弦时必读**（强拍和弦音、和弦外音、真实歌曲与编曲案例） |
| `references/web-research-guide.md` | 风格未知 / 真实案例 / analyze 不达标时必读：模糊联网检索与质量门槛 |
| `references/midi-schema.md` | 不确定 JSON 字段/约束/GM 音色时 |
| `references/examples.md` | 需要完整范例参考时 |
| `references/anti-formula.md` | 写第二稿时必读：打破公式、制造记忆点 |
| `../aria-music-theory/references/styles/*.md` | 按风格需要（流行/EDM/爵士/Tropical/通用） |
| `../aria-music-theory/references/electronic-arrangement.md` | 写电子音乐前必读：EDM 乐理 + 舞曲结构 + 提示词模板 |
| `../aria-music-theory/references/house-melody-analysis.md` | 写 House 前必读：真实 MIDI 拆解 + 多风格旋律对照 |
| `../aria-music-theory/references/theory-arrangement.md` | 配和弦/写多轨/做风格化编曲前必读 |
