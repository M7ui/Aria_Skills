# aria-midi — Aria Skills 执行层 CLI

零依赖 MIDI 工具包（仅 Python 标准库，Python 3.8+）。任何 Agent 可用 Bash 直接调用：JSON 进、JSON 出，退出码可编程判断。

```bash
python aria_midi.py <子命令> [参数]
# 部署后可用 PATH 垫片（由 sync_to_agents.py 生成）：
aria-midi <子命令> [参数]
```

## 子命令

| 子命令 | 功能 | 退出码 |
|--------|------|--------|
| `generate` | song.json → 标准 MIDI 文件（Type-1, TPQN=480） | 0 成功 / 1 数据错误 / 2 IO 错误 |
| `validate` | 校验 schema / 音域 / 力度 / 量化 / 重叠 | 0 通过（可含警告）/ 1 有错误 / 2 IO 错误 |
| `inspect` | 解析 .mid → 音符列表 JSON | 0 / 1 数据错误 / 2 IO 错误 |
| `scale` | 音阶/和弦：列音、和弦音、吸附、调式推测 | 0 / 2 用法错误 |
| `analyze` | 旋律质量 0–10 评分（技术分/音乐性分/结构分）+ 中文建议 | 0 / 1 数据错误 / 2 IO 错误 |
| `compare` | 风格锚定：产出 song.json 与参考 .mid 风格参数对比 | 0 / 1 数据错误 / 2 IO 错误 |

通用约定：`--input -` 从 stdin 读取（generate/validate/analyze/compare）；`--version` 打印版本；所有输出 UTF-8 JSON。

## generate

```bash
# 推荐：song.json 顶层写 "name"，--output 可省，自动派生 <输入目录>/<歌名>.mid
aria-midi generate --input 未寄出的信/song.json
#   → 未寄出的信/未寄出的信.mid

aria-midi generate --input song.json --output song.mid --bpm 120
aria-midi generate --input song.json --output song.mid --name-encoding gbk
```

**歌曲名与输出路径派生**（v1.3.0 新增）

`--output` 可省。按以下优先级决定输出路径：

| 情况 | 输出 |
|------|------|
| 给了 `--output` | 原样使用 |
| 未给，但有 `--name` 或 song.json 顶层 `name` | `<outdir>/<slug(歌名)>.mid` |
| 未给，也没有歌名 | 用法错误（退出码 2）—— 与旧行为一致，未命名作品仍须显式给 `--output` |

- `--outdir` 指定派生目录；**省略时取 `--input` 所在目录**，所以「每首歌一个目录」的布局下
  直接 `--input <歌名>/song.json` 就会写出 `<歌名>/<歌名>.mid`，不必重复敲路径
- 歌名同时写入 MIDI **序列名**（meta `0x03`），DAW/播放器会显示为曲名。
  超 64 字节截断且不切断多字节字符；**未命名作品不写该事件，输出与旧版逐字节一致**
- 文件名清洗：`<>:"/\|?*` 与控制字符替换为 `_`，去掉结尾的点与空格（Windows 会静默截断），
  超 60 字符截断。中文原样保留。清洗后为空则回退 `song`

- 输入：`song.json`（见下方 Schema）；`--bpm` **覆盖**文件内 bpm（40–300），不传则用文件值
- `--name-encoding auto|utf-8|gbk|big5|...`：音轨名/序列名编码。`auto`（默认）在 Windows 使用系统 ANSI 码页（中文系统为 GBK，与系统播放器/传统 DAW 兼容），其它平台 UTF-8
- `start_beat` 为负直接报错（退出码 1），不会静默写坏时间流
- 输出：MIDI Type-1：第 1 轨为指挥轨（序列名 + Tempo + 拍号），其后每音轨一轨（音轨名 meta + Program Change + 音符）
- Note-On/Off 按 tick 排序，同一 tick Off 先于 On（同音高衔接不丢音）
- 生成时兜底：duration ≤ 0 → 0.25 拍；pitch/velocity 越界 → 夹取到合法范围（validate 负责先报错）

## validate

```bash
aria-midi validate --input song.json            # 量化越界只警告
aria-midi validate --input song.json --strict   # 量化越界视为错误
```

检查项：
1. 顶层结构（tracks 或旧版 notes 二者必有其一）
2. pitch 0–127；velocity 1–127；BPM 40–300
3. start_beat ≥ 0、duration > 0，均为 0.25 的整数倍（strict 下为硬错误）
4. 同音轨同音高时间重叠（首尾相接合法）

输出示例：

```json
{
  "ok": false,
  "errors": ["[旋律] 音符#3 力度越界：0（允许 1-127）"],
  "warnings": ["[旋律] 音符#1 start_beat=0.3 不在 0.25 拍网格上"],
  "stats": {"bpm": 120, "track_count": 2, "note_count": 20, "total_beats": 32.0, "pitch_min": 36, "pitch_max": 74}
}
```

## inspect

```bash
aria-midi inspect --input song.mid
```

- 零依赖 MIDI 解析器：支持 running status、`0x9n vel=0` 记法、Tempo/音轨名/拍号 meta、SysEx 跳过
- 音轨名**自动检测编码**：UTF-8 严格解码 → 系统 ANSI 码页 → GBK/Big5/Shift-JIS → latin-1
- 纯指挥轨（无音符、无音轨名、无 Program Change）不输出
- 同音高重叠时 Note-Off 按 FIFO 与最早 Note-On 配对
- **限制**：不支持 SMPTE 时基（`division & 0x8000`）的 MIDI；速度变化只报告首个 Tempo

输出示例：

```json
{
  "format": 1, "tpqn": 480, "bpm": 120.0, "time_signature": "4/4",
  "tracks": [
    {"index": 1, "name": "旋律", "program": 0,
     "notes": [{"pitch": 67, "start_beat": 0.0, "duration": 0.5, "velocity": 95}]}
  ]
}
```

## scale

```bash
aria-midi scale --root C4 --type major --list                 # 列音阶音
aria-midi scale --root G4 --type major --chord dom7           # 列和弦音
aria-midi scale --root C4 --type major --snap 61 63 66        # 音高吸附到音阶
aria-midi scale --suggest 60,62,64,65,67,69,71                # 由音高推测调式
```

- `--root` 接受音名（"C4"、"F#3"、"Bb2"）或 MIDI 数字；`--type` 13 种音阶；`--chord` 14 种和弦
- `--snap`：吸附到最近音阶音，**等距时优先高邻音**（F# 在 C 大调 → G）
- `--suggest`：按覆盖率排序返回前 5 个候选调式

## analyze

```bash
aria-midi analyze --input song.json                      # 基础分析（默认评旋律轨）
aria-midi analyze --input song.json --chords chords.json  # 含强拍和弦音匹配率
aria-midi analyze --input song.json --key-root C4 --key-type major  # 含出界音符检查
aria-midi analyze --input song.json --track 旋律          # 按名称指定评分音轨
aria-midi analyze --input song.json --all-tracks          # 合并全部音轨（旧行为）
aria-midi analyze --input song.json --style arpeggio      # 豁免跳进约束（jazz/arpeggio/blues/edm/lofi）
```

评分维度（0–10，基础分 2.0）：

| 维度 | 分值 | 说明 |
|------|------|------|
| 强拍和弦音匹配率 | ≤1.5 | 规则 2；无和弦定义退回全音符匹配率 |
| **级进占比** | ≤2.5 | 规则 5 核心：级进占比 ≥60% 拿满，<40% 视为旋律断裂 |
| 时值多样性 | ≤1.5 | ≥3 种时值拿满 |
| 力度动态范围 | ≤1.0 | 极差 ≥20 拿满 |
| 呼吸空间 | ≤1.0 | 连续无休止占比越低越高 |
| 动机发展 | ≤0.5 | 有动机重复（规则 1）加分 |

惩罚项：级进占比 <40%（跳进为主）扣 2.0；跳进是级进 2 倍以上扣 1.5（`--style` 豁免跳进型风格）。

**旋律轨隔离**：默认只评「平均音高最高的轨」（通常是旋律轨），避免低音/伴奏轨的分解音污染级进与呼吸统计。`--track` 显式指定、`--all-tracks` 回退旧行为。

输出：`{score, technical_score, musicality_score, passed, summary, details{...}, suggestions[]}`。details 含 `analyzed_track`（评分轨）、`analyzed_notes`（评分音符数）、`total_notes`（全曲）、`step_ratio`（级进占比）、`motif_reuse`（动机重复）、`chord_tone_rate`（全音符）与 `strong_beat_chord_tone_rate`（强拍单独统计）。suggestions 为中文，可直接指导修改 song.json。

### 技术分 / 音乐性分

总分 `score` 之外，另拆两个子分（各 0–10），避免「技术指标刷分」掩盖旋律断裂：

- `technical_score` 技术分：强拍和弦音（≤3）+ 时值多样（≤2.5）+ 力度范围（≤2）+ 呼吸空间（≤2.5）——衡量「写对了没」
- `musicality_score` 音乐性分：级进占比（≤6，核心）+ 动机发展（≤4），断裂/跳进过度另扣——衡量「好听吗」
- `passed`：`technical ≥ 6 且 musicality ≥ 6` 才为 true，作为放行开关（比单一 `score ≥ 7` 更严格）

### 结构分（v1.2.0 新增，连贯性维度）

`structure_score`（0–10，独立第三栏，不参与 `passed`）检查模块化乐句结构，
对应 composition-rules.md「规则 1 补充」的四级组装（动机→乐节→乐句→乐段）：

| 检测项 | 分值 | 判定 |
|--------|------|------|
| 乐句切分 | ≤3 | 按休止 ≥0.5 拍 / 长音 ≥2 拍切句（大 IOI 是乐句边界的强预测因子，Pearce et al. 2010）；2–8 句拿满，只切出 1 句扣分并给建议 |
| 跨乐句轮廓复用 | ≤3 | 乐句开头 2 个音程方向相同的对数 > 0（period/起承转合/AABA 的「同头」特征） |
| 高潮位置 | ≤2 | ≥16 拍时，全曲最高音出现在 35%–90% 区间拿满；<30% 报「高潮太早」 |
| 终止稳定性 | ≤2 | 仅传 `--key-root` 时启用：末乐句落主音拿满；倒数乐句不落属音/上主音给半终止建议 |

输出位置：顶层 `structure_score`；`details.structure` 含 `phrase_count` / `phrase_lengths` /
`phrase_endings_pc` / `contour_reuse_pairs` / `climax_position` / `final_on_tonic`。
结构建议直接进 `suggestions`。使用建议：`analyze --chords chords.json --key-root C4` 一起传，结构分 < 6 时先修乐句计划再改音符。

## compare（风格锚定）

把产出与真实案例 `.mid` 做风格参数对比，用于「我写的这首像不像目标风格」的自检。

```bash
aria-midi compare --input song.json --reference examples/midi/tropical-demo.mid
```

对比维度（产出旋律轨 vs 参考旋律轨）：BPM、级进占比、音域跨度、力度范围、音符密度、短音占比。输出 `{similarity(0-1), verdict(风格匹配/偏离), dimensions{...}}`。

判定：6 个维度匹配占比 = `similarity`；**级进占比严重偏离（>0.2）或 similarity <0.6 → 判「风格偏离」**（级进占比是区分可唱旋律与琶音/断裂的头号指标）。

```bash
aria-midi compare --input tropical_loop.json --reference examples/midi/tropical-demo.mid  # 风格匹配
aria-midi compare --input piano_piece.json  --reference examples/midi/tropical-demo.mid  # 风格偏离（级进占比 19% vs 62%）
```

## 数据 Schema

### song.json

```json
{
  "bpm": 120,
  "time_signature": {"numerator": 4, "denominator": 4},
  "tracks": [
    {"name": "旋律", "channel": 0, "program": 0,
     "notes": [{"pitch": 67, "start_beat": 0.0, "duration": 0.5, "velocity": 95}]}
  ]
}
```

| 字段 | 约束 |
|------|------|
| bpm | 40–300（默认 120） |
| tracks[] | 至少 1 轨；channel 0–15（默认按序）；program 0–127 GM（默认 0） |
| notes[].pitch | 0–127（推荐旋律 36–96） |
| notes[].start_beat | ≥0，0.25 的整数倍 |
| notes[].duration | >0，0.25 的整数倍 |
| notes[].velocity | 1–127（默认 100） |

旧版格式 `{"notes": [...]}`（无 tracks）等价于单轨「Piano」。

### chords.json

```json
{"chords": [{"root": 60, "type": "maj", "start_beat": 0, "duration": 4}]}
```

`root` 可用音名；`type` 为 14 种和弦类型之一。

## 已知限制

- `analyze` 将所有音轨合并统计（与上游应用行为一致）：多轨时跳进/级进、休止统计包含低音等伴奏轨
- `inspect` 不支持 SMPTE 时基；速度变化只报告首个 Tempo
- `generate` 拍号分母须为 2 的幂，否则回退 4/4
- 不生成 running status 压缩（兼容性优先）
- 音轨名按所选编码截断 64 字节（从尾部逐字截断，不切断多字节字符）

## 测试

```bash
python tests/run_tests.py   # 23 个用例：往返一致性 / 校验错误 / 音阶 / 分析 / 编码 / BPM 覆盖
```
