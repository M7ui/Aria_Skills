# 完整作曲范例（examples）

三个风格各一例，均可直接作为 song.json 使用。更多风格细节见 `../amr-music-theory/references/styles/`。

## 范例 1 — 流行副歌 Hook（8 小节，C 大调，120 BPM，C-G-Am-F）

设计思路：五声上行动机 + 切分节奏；强拍落和弦音；力度钟形弧线；动机重复带变奏；第 3.5–4.0 拍留休止；结尾弱收。

```json
{
  "bpm": 120,
  "tracks": [
    {
      "name": "旋律",
      "channel": 0,
      "program": 0,
      "notes": [
        {"pitch": 67, "start_beat": 0.0, "duration": 0.5, "velocity": 95},
        {"pitch": 67, "start_beat": 0.75, "duration": 0.25, "velocity": 80},
        {"pitch": 69, "start_beat": 1.0, "duration": 0.75, "velocity": 105},
        {"pitch": 72, "start_beat": 2.0, "duration": 0.5, "velocity": 100},
        {"pitch": 71, "start_beat": 2.75, "duration": 0.5, "velocity": 85},
        {"pitch": 72, "start_beat": 3.5, "duration": 0.5, "velocity": 90},
        {"pitch": 67, "start_beat": 4.0, "duration": 0.5, "velocity": 95},
        {"pitch": 67, "start_beat": 4.75, "duration": 0.25, "velocity": 80},
        {"pitch": 69, "start_beat": 5.0, "duration": 0.5, "velocity": 105},
        {"pitch": 74, "start_beat": 5.75, "duration": 0.5, "velocity": 100},
        {"pitch": 72, "start_beat": 6.5, "duration": 1.0, "velocity": 110},
        {"pitch": 64, "start_beat": 7.75, "duration": 0.5, "velocity": 75}
      ]
    },
    {
      "name": "低音",
      "channel": 1,
      "program": 32,
      "notes": [
        {"pitch": 36, "start_beat": 0.0, "duration": 4.0, "velocity": 90},
        {"pitch": 43, "start_beat": 4.0, "duration": 4.0, "velocity": 85},
        {"pitch": 45, "start_beat": 8.0, "duration": 4.0, "velocity": 85},
        {"pitch": 41, "start_beat": 12.0, "duration": 4.0, "velocity": 85},
        {"pitch": 36, "start_beat": 16.0, "duration": 4.0, "velocity": 90},
        {"pitch": 43, "start_beat": 20.0, "duration": 4.0, "velocity": 85},
        {"pitch": 45, "start_beat": 24.0, "duration": 4.0, "velocity": 85},
        {"pitch": 41, "start_beat": 28.0, "duration": 4.0, "velocity": 85}
      ]
    }
  ]
}
```

为什么好听：✓ 切分节奏（不全在正拍）✓ 强拍是和弦音（G4 是 C 和弦五音，C5 是根音）✓ 力度弧线 80→105→75 ✓ 动机重复带变奏（第二遍 A4→D5 延伸）✓ 3.5–4.0 过渡留白 ✓ 结尾弱收。

## 范例 2 — EDM 铺垫段 Build-up（4 小节，A 小调，128 BPM）

设计思路：密度 ×2 ×4 递增 + 音高阶梯上行 + 力度线性爬升，最后冲向 Drop。

```json
{
  "bpm": 128,
  "tracks": [
    {
      "name": "Lead",
      "channel": 0,
      "program": 80,
      "notes": [
        {"pitch": 57, "start_beat": 0.0, "duration": 0.25, "velocity": 70},
        {"pitch": 57, "start_beat": 0.5, "duration": 0.25, "velocity": 72},
        {"pitch": 60, "start_beat": 1.0, "duration": 0.25, "velocity": 76},
        {"pitch": 60, "start_beat": 1.25, "duration": 0.25, "velocity": 78},
        {"pitch": 60, "start_beat": 1.5, "duration": 0.25, "velocity": 80},
        {"pitch": 60, "start_beat": 1.75, "duration": 0.25, "velocity": 82},
        {"pitch": 64, "start_beat": 2.0, "duration": 0.25, "velocity": 84},
        {"pitch": 64, "start_beat": 2.25, "duration": 0.25, "velocity": 86},
        {"pitch": 67, "start_beat": 2.5, "duration": 0.25, "velocity": 90},
        {"pitch": 67, "start_beat": 2.75, "duration": 0.25, "velocity": 92},
        {"pitch": 69, "start_beat": 3.0, "duration": 0.25, "velocity": 96},
        {"pitch": 69, "start_beat": 3.25, "duration": 0.25, "velocity": 98},
        {"pitch": 72, "start_beat": 3.5, "duration": 0.25, "velocity": 105},
        {"pitch": 72, "start_beat": 3.75, "duration": 0.25, "velocity": 110}
      ]
    }
  ]
}
```

## 范例 3 — 爵士 Walking Bass（8 小节，C 大调，ii-V-I）

设计思路：四分音符平稳走步 + 半音经过音（F#→G）+ 乐段间简化对比，最后落在主音 C2。

```json
{
  "bpm": 120,
  "tracks": [
    {
      "name": "Bass",
      "channel": 0,
      "program": 33,
      "notes": [
        {"pitch": 38, "start_beat": 0.0, "duration": 1.0, "velocity": 90},
        {"pitch": 41, "start_beat": 1.0, "duration": 0.5, "velocity": 85},
        {"pitch": 42, "start_beat": 1.5, "duration": 0.5, "velocity": 75},
        {"pitch": 43, "start_beat": 2.0, "duration": 1.0, "velocity": 88},
        {"pitch": 41, "start_beat": 3.0, "duration": 0.5, "velocity": 80},
        {"pitch": 40, "start_beat": 3.5, "duration": 0.5, "velocity": 75},
        {"pitch": 38, "start_beat": 4.0, "duration": 1.0, "velocity": 90},
        {"pitch": 43, "start_beat": 5.0, "duration": 1.0, "velocity": 82},
        {"pitch": 47, "start_beat": 6.0, "duration": 1.0, "velocity": 85},
        {"pitch": 43, "start_beat": 7.0, "duration": 1.0, "velocity": 78},
        {"pitch": 36, "start_beat": 8.0, "duration": 2.0, "velocity": 88},
        {"pitch": 40, "start_beat": 10.0, "duration": 2.0, "velocity": 82},
        {"pitch": 43, "start_beat": 12.0, "duration": 2.0, "velocity": 85},
        {"pitch": 36, "start_beat": 14.0, "duration": 2.0, "velocity": 80}
      ]
    }
  ]
}
```

说明：1–2 小节 Dm7（ii，D-F-G 走步）、3–4 小节 G7（V）、5–8 小节 Cmaj7（I，节奏放宽为二分音符）；F#2 是半音经过音，落在弱位。
