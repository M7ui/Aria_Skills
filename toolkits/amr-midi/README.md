# amr-midi — AMIDI Skills 执行层 CLI

零依赖 MIDI 工具包（仅 Python 标准库，Python 3.8+）。任何 Agent 可用 Bash 直接调用：JSON 进、JSON 出，退出码可编程判断。

```bash
python amr_midi.py <子命令> [参数]
# 部署后可用 PATH 垫片（由 sync_to_agents.py 生成）：
amr-midi <子命令> [参数]
```

## 子命令

| 子命令 | 功能 | 退出码 |
|--------|------|--------|
| `generate` | song.json → 标准 MIDI 文件（Type-1, TPQN=480） | 0 成功 / 1 数据错误 / 2 IO 错误 |
| `validate` | 校验 schema / 音域 / 力度 / 量化 / 重叠 | 0 通过（可含警告）/ 1 有错误 / 2 IO 错误 |
| `inspect` | 解析 .mid → 音符列表 JSON | 0 / 1 数据错误 / 2 IO 错误 |
| `scale` | 音阶/和弦：列音、和弦音、吸附、调式推测 | 0 / 2 用法错误 |
| `analyze` | 旋律质量 0–10 评分 + 中文建议 | 0 / 1 数据错误 / 2 IO 错误 |

通用约定：`--input -` 从 stdin 读取（generate/validate/analyze）；`--version` 打印版本；所有输出 UTF-8 JSON。

## generate

```bash
amr-midi generate --input song.json --output song.mid --bpm 120
amr-midi generate --input song.json --output song.mid --name-encoding gbk
```

- 输入：`song.json`（见下方 Schema）；`--bpm` **覆盖**文件内 bpm（40–300），不传则用文件值
- `--name-encoding auto|utf-8|gbk|big5|...`：音轨名编码。`auto`（默认）在 Windows 使用系统 ANSI 码页（中文系统为 GBK，与系统播放器/传统 DAW 兼容），其它平台 UTF-8
- `start_beat` 为负直接报错（退出码 1），不会静默写坏时间流
- 输出：MIDI Type-1：第 1 轨为指挥轨（Tempo + 4/4 拍号），其后每音轨一轨（音轨名 meta + Program Change + 音符）
- Note-On/Off 按 tick 排序，同一 tick Off 先于 On（同音高衔接不丢音）
- 生成时兜底：duration ≤ 0 → 0.25 拍；pitch/velocity 越界 → 夹取到合法范围（validate 负责先报错）

## validate

```bash
amr-midi validate --input song.json            # 量化越界只警告
amr-midi validate --input song.json --strict   # 量化越界视为错误
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
amr-midi inspect --input song.mid
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
amr-midi scale --root C4 --type major --list                 # 列音阶音
amr-midi scale --root G4 --type major --chord dom7           # 列和弦音
amr-midi scale --root C4 --type major --snap 61 63 66        # 音高吸附到音阶
amr-midi scale --suggest 60,62,64,65,67,69,71                # 由音高推测调式
```

- `--root` 接受音名（"C4"、"F#3"、"Bb2"）或 MIDI 数字；`--type` 13 种音阶；`--chord` 14 种和弦
- `--snap`：吸附到最近音阶音，**等距时优先高邻音**（F# 在 C 大调 → G）
- `--suggest`：按覆盖率排序返回前 5 个候选调式

## analyze

```bash
amr-midi analyze --input song.json                      # 基础分析
amr-midi analyze --input song.json --chords chords.json  # 含强拍和弦音匹配率
amr-midi analyze --input song.json --key-root C4 --key-type major  # 含出界音符检查
```

评分维度（0–10）：**强拍(第1、3拍)和弦音匹配率**（≤2 分，规则 2 核心指标；无和弦定义时退回全音符匹配率）、时值多样性（≤2 分）、力度动态范围（≤1 分）、呼吸空间（≤1 分）、基础分 5。

输出：`{score, summary(优秀/良好/一般/需要改进), details{...}, suggestions[]}`。details 含 `chord_tone_rate`（全音符）与 `strong_beat_chord_tone_rate`（强拍单独统计）两个口径。suggestions 为中文，可直接指导修改 song.json。

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
