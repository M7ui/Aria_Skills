# song.json / chords.json 数据规范（midi-schema）

`aria_midi.py` 的 `generate` / `validate` / `analyze` 均以以下 JSON 为输入。

## song.json — 音符数据

```json
{
  "bpm": 120,
  "time_signature": { "numerator": 4, "denominator": 4 },
  "tracks": [
    {
      "name": "旋律",
      "channel": 0,
      "program": 0,
      "notes": [
        { "pitch": 67, "start_beat": 0.0, "duration": 0.5, "velocity": 95 }
      ]
    }
  ]
}
```

### 顶层字段

| 字段 | 类型 | 约束 | 默认 |
|------|------|------|------|
| `name` | string | **可选**。歌曲名。`generate` 用它派生输出文件名 `<歌名>.mid`，并写成 MIDI 序列名（meta `0x03`，DAW/播放器显示为曲名）。`--name` 可覆盖。文件名会清洗非法字符（`<>:"/\|?*`、控制字符、结尾点/空格），超长截断到 60 字符 | 无 |
| `bpm` | number | 40–300 | 120 |
| `time_signature` | object | numerator ≥1；denominator 为 2 的幂（非幂时生成回退 4/4） | 4/4 |
| `tracks` | array | 至少 1 轨；每轨含 `notes` | 必填 |
| `notes` | array | **旧版格式**：与 tracks 二选一，等价于单轨「Piano」 | — |

> **命名与目录约定**：每首歌放独立目录，`song.json` 顶层写 `name`。这样
> `aria-midi generate --input <歌名>/song.json` 会直接产出 `<歌名>/<歌名>.mid`，
> 不必再敲 `--output`。详见 SKILL.md「项目布局」。

### track 字段

| 字段 | 类型 | 约束 | 默认 |
|------|------|------|------|
| `name` | string | 写入 MIDI 时截断 64 字节（不切断多字节字符）；默认 Windows 用系统 ANSI 码页（中文系统 GBK）、其它平台 UTF-8，可用 `--name-encoding` 覆盖 | Track N |
| `channel` | int | 0–15 | 按音轨顺序 0,1,2… |
| `program` | int | 0–127（GM 音色） | 0（大钢琴） |
| `notes` | array of note | 见下 | 必填 |

### note 字段

| 字段 | 类型 | 约束 | 默认 |
|------|------|------|------|
| `pitch` | int | 0–127（推荐旋律 36–96） | — |
| `start_beat` | number | ≥0，0.25 的整数倍 | 0 |
| `duration` | number | >0，0.25 的整数倍 | 1 |
| `velocity` | int | 1–127 | 100 |

### 约束速查（validate 检查项）

- **量化**：start_beat / duration 非 0.25 倍数 → 默认警告；`--strict` 下视为错误
- **重叠**：同一音轨内同音高音符时间重叠 → 错误（相邻首尾相接合法）
- **音域**：pitch 0–127；力度 1–127；BPM 40–300
- **时值下限**：duration ≤ 0 非法；生成时 duration*TPQN < 1 tick 会自动兜底为 0.25 拍

## chords.json — 和弦进行（供 analyze 检查强拍匹配）

```json
{
  "chords": [
    { "root": 60, "type": "maj", "start_beat": 0,  "duration": 4 },
    { "root": 67, "type": "maj", "start_beat": 4,  "duration": 4 },
    { "root": 69, "type": "min", "start_beat": 8,  "duration": 4 },
    { "root": 65, "type": "maj", "start_beat": 12, "duration": 4 }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `root` | int 或音名 | MIDI 编号（60）或音名（"C4"） |
| `type` | string | 14 种和弦类型（见 aria-music-theory 速查） |
| `start_beat` | number | 和弦起始拍 |
| `duration` | number | 和弦持续拍数 |

## GM 常用音色表（program 编号）

| 编号 | 音色 | 编号 | 音色 |
|------|------|------|------|
| 0 | 大钢琴 | 32 | 原声贝斯 |
| 24 | 尼龙弦吉他 | 33 | 电贝斯（指弹） |
| 25 | 钢弦吉他 | 48/49 | 弦乐组 |
| 80 | 方波 Lead | 88 | 温暖 Pad |
| 114 | 钢鼓（Tropical House） | | |

## 音域分工建议

| 音轨 | MIDI 音域 | program 建议 |
|------|-----------|--------------|
| 低音 | 36–50 | 32 / 33 |
| 和弦 | 48–67 | 0 / 48 |
| 旋律 | 60–84 | 0 / 80 |
| 铺底 | 55–72 | 88 |
