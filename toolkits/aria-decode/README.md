# aria-decode — 零依赖 MIDI → JSON 无损解码器

Aria 技能包子工具（v1.0.1）：把任意 `.mid` 文件**无损解码**为结构化 JSON，覆盖全部 MIDI 事件类型。仅 Python 标准库（3.8+），可复制到任何目录直接运行。

```
python <本包目录>/aria_decode.py decode --input <file.mid> [--output <file.json>] [--no-events] [--no-notes]
# 或把 bin 加入 PATH 后直接：
aria-decode decode --input song.mid
```

## 特性

| 特性 | 说明 |
|------|------|
| 无损解码 | 全部事件类型：meta（音轨名/歌词/Marker/拍号/调号/Tempo/SMPTE Offset…）、通道事件（Note/CC/弯音/Program/触后）、SysEx、系统实时消息 |
| 双时基 | PPQN 与 SMPTE 均支持（SMPTE 含 29.97 drop-frame 换算） |
| 精确秒时间 | Tempo 变化跨轨共享、逐事件换算 `time`（秒），音符含 `start_time`/`end_time` |
| 人性化字段 | GM 音色名（128）、标准 CC 控制器名、音高名（C4 等）自动映射 |
| 中文编码 | 音轨名/歌词 GBK/Big5/Shift-JIS/UTF-8 逐级回退解码 |
| JSON 进出 | 退出码 0=成功 / 1=数据错误 / 2=用法错误 |

## 应用场景

- **逆向分析**：拿到别人导出的 `.mid`，快速看清音轨、通道、音色、Tempo、CC 与弯音是怎么编排的
- **格式转换/迁移**：MIDI 事件无损落成 JSON 后，可被其他工具、脚本或 Agent 继续处理
- **生成后质检**：`aria-midi generate` 产出的文件用 `decode` 回读，核对 Tempo/音符/CC 是否与 song.json 一致
- **事件级调试**：检查歌词、Marker、SysEx、系统消息、拍号/调号等 `inspect` 不保留的细节

## 与 aria-midi inspect 的区别

- `aria-midi inspect`：**有损**——只提取音符/音轨名/Program/Tempo/拍号，丢弃通道、CC、弯音、歌词等细节，且不支持 SMPTE。
- `aria-decode`：**无损**——保留每一个事件的类型与数据，另附跨轨音符汇总，适合逆向分析、格式转换、质检。

## 用法

```
aria-decode decode --input <file.mid> [--output <file.json>] [--no-events] [--no-notes]
```

| 选项 | 说明 |
|------|------|
| `--input` | 输入 MIDI 文件（`-` 表示 stdin） |
| `--output` | 输出 JSON 文件（默认 stdout，`-` 同上） |
| `--no-events` | 不输出逐事件明细，仅头部/全局/音符汇总（体积最小） |
| `--no-notes` | 不输出音符汇总，仅事件明细 |
| `--version` | 输出版本号 |

### 示例

```bash
# 完整解码（默认）
aria-decode decode --input song.mid

# 快速概览：仅头部 + 全局 + 音符
aria-decode decode --input song.mid --no-events

# 只留事件明细
aria-decode decode --input song.mid --no-notes

# 写文件 + stdin 管道
aria-decode decode --input song.mid --output song.json
cat song.mid | aria-decode decode --input - > song.json
```

## 输出结构

```json
{
  "ok": true,
  "file": "song.mid",
  "decoder": "aria-decode 1.0.1",
  "header": { "format": 1, "track_count": 3, "division_type": "tpqn", "tpqn": 480 },
  "global": {
    "bpm": 120.0, "time_signature": "4/4", "key_signature": null,
    "duration_ticks": 15360, "duration_sec": 16.0
  },
  "tracks": [
    {
      "index": 0, "name": "旋律", "channel": 0, "program": 0,
      "event_count": 27, "note_count": 12,
      "events": [
        { "tick": 0, "time": 0.0, "delta": 0, "type": "meta", "meta": "track_name", "name": "旋律" },
        { "tick": 0, "time": 0.0, "delta": 0, "type": "tempo", "bpm": 120.0, "us_per_beat": 500000 },
        { "tick": 0, "time": 0.0, "delta": 0, "type": "control_change", "channel": 0, "controller": 7, "controller_name": "Channel Volume (MSB)", "value": 100 },
        { "tick": 480, "time": 0.5, "delta": 480, "type": "note_on", "channel": 0, "pitch": 67, "pitch_name": "G4", "velocity": 95 },
        { "tick": 720, "time": 0.75, "delta": 240, "type": "note_off", "channel": 0, "pitch": 67, "pitch_name": "G4", "velocity": 0 },
        { "tick": 720, "time": 0.75, "delta": 0, "type": "pitch_bend", "channel": 0, "value": 8192, "semitones": 0.0 },
        { "tick": 720, "time": 0.75, "delta": 0, "type": "meta", "meta": "end_of_track" }
      ]
    }
  ],
  "notes": [
    { "track": 0, "channel": 0, "pitch": 67, "pitch_name": "G4",
      "start_tick": 0, "start_beat": 0.0, "start_time": 0.0,
      "end_tick": 240, "duration_ticks": 240, "duration": 0.5, "end_time": 0.25,
      "velocity": 95 }
  ],
  "warnings": []
}
```

### 事件类型一览

| type | 说明 |
|------|------|
| `meta` | `meta` 字段区分：`track_name` / `lyrics` / `marker` / `tempo` / `time_signature` / `key_signature` / `smpte_offset` / `channel_prefix` / `midi_port` / `end_of_track` / `sequencer_specific` / `unknown` 等 |
| `note_on` / `note_off` | `channel` / `pitch` / `pitch_name` / `velocity`（vel=0 记法自动归类为 note_off） |
| `control_change` | `controller` / `controller_name` / `value` |
| `pitch_bend` | `value`（0–16383）/ `semitones`（±2） |
| `program_change` | `program` / `program_name`（GM） |
| `poly_aftertouch` / `channel_pressure` | 触后 |
| `sys_exclusive` / `sys_exclusive_continue` | 原始数据 hex |
| `timing_clock` / `start` / `continue` / `stop` / `active_sensing` / `song_position` / `song_select` / `tune_request` / `mtc_quarter_frame` | 系统消息 |

### 字段说明

- 所有事件均含 `tick`（绝对 tick）、`time`（绝对秒，含 Tempo 变化）、`delta`（相对 tick）
- `notes` 为跨轨音符汇总，含 `track` / `channel` / `pitch_name` / `start_beat` / `duration`（以拍为单位）/ 秒时间戳
- `tracks[].channel` 为轨内出现频率最高的通道；`program` 为轨内最后一次 Program Change

## 测试

```
python tests/run_tests.py
```

22 个用例 35 项断言：事件解码、running status、vel=0 记法、重叠音符、Tempo 跨轨时间轴、SMPTE（24/30fps）、GBK 音轨名、歌词/Marker、退出码、stdin、UTF-8 stdout、`--no-events`/`--no-notes`、SysEx 等。

## 已知限制

- 严格无损为事件级还原；音符聚合按 (channel, pitch) 配对，未闭合音符在 EOT 处强制收尾并计入 `warnings`
- 文本事件解码为最佳猜测（UTF-8 → GBK → Big5 → Shift-JIS → latin-1），多编码混用文件可能失真
- `fps_actual` 对 29fps 记法按 29.97 换算；drop-frame 时间码的时间轴修正未实现

## 许可

MIT（见仓库根目录 LICENSE）。
