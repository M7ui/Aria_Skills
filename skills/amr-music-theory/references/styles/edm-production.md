# EDM Production Techniques (128 BPM)

## Drum Programming

### Kick Pattern
Standard four-on-the-floor (every quarter note):
```
Beat:  1    2    3    4
Kick:  X    X    X    X
```

**Variations:**
- **Double kick**: Add off-beat kick on "and" of 2 and 4
- **Syncopated**: Move kick on beat 3 to "and" of 2
- **Breakbeat**: Remove kick on beat 3, add on "and" of 3

### Clap/Snare Pattern
Standard backbeat (beats 2 and 4):
```
Beat:   1    &    2    &    3    &    4    &
Clap:   .    .    X    .    .    .    X    .
```

**Variations:**
- **Double clap**: Add clap on "and" of 2 and 4
- **Off-beat clap**: Move clap to "and" of 2 and 4
- **Trap clap**: Add multiple claps in 16th notes

### Hi-Hat Pattern
Standard eighth notes:
```
Beat:   1    &    2    &    3    &    4    &
HiHat:  X    .    X    .    X    .    X    .
```

**Variations:**
- **16th notes**: Fill every 16th note position
- **Syncopated**: Remove hi-hats on beats 2 and 4
- **Open hi-hat**: Replace closed hi-hat on "and" of 2

## Build-up Techniques

### Snare Roll
Linear acceleration:
```
Phase 1 (0-2 bars):  Snare every beat (4 per bar)
Phase 2 (2-4 bars):  Snare every half beat (8 per bar)
Phase 3 (4-6 bars):  Snare every quarter beat (16 per bar)
Phase 4 (6-8 bars):  Snare every eighth beat (32 per bar)
```

### Pitch Rise
Ascending pitch with velocity crescendo:
```
Notes: A3(start:0, dur:0.25, vel:70) → A3(start:0.5, dur:0.25, vel:72) → ... → C5(start:7.5, dur:0.25, vel:110)
```

### Filter Sweep
High-pass filter opening:
```
Start: Low-pass at 200Hz (muffled)
End: Low-pass at 20kHz (bright)
```

## Drop Techniques

### Impact Elements
- **Kick**: Strong on beat 1, velocity 100-120
- **Clap**: On beats 2 and 4, velocity 90-110
- **Bass**: Root note, sustained, velocity 95-115
- **Lead**: Main melody, high register, velocity 85-105

### Rhythm Patterns
**Standard drop rhythm:**
```
Beat:   1    &    2    &    3    &    4    &
Lead:   X    .    X    .    X    .    X    .
Bass:   X    .    .    .    X    .    .    .
```

**Syncopated drop:**
```
Beat:   1    &    2    &    3    &    4    &
Lead:   .    X    .    X    .    X    .    X
Bass:   X    .    .    .    X    .    .    .
```

## Bass Design

### Sub Bass
Low frequency (30-80 Hz), sine wave, minimal harmonics:
```
Notes: A3(57) or G3(55), duration 0.5-1.0, velocity 100-120
```

### Bass Pattern
Root on beat 1, fifth on beat 3:
```
Beat:   1    &    2    &    3    &    4    &
Bass:   A2   .    .    .    E3   .    .    .
```

### Wobble Bass
Modulated pitch or filter:
```
Notes: A3(57) with pitch bend or filter automation
```

## Arrangement Structure

### Standard EDM Structure
1. Intro (8 bars): Sparse, filtered
2. Build-up (8 bars): Rising energy
3. Drop (16 bars): Maximum energy
4. Breakdown (8 bars): Stripped back
5. Build-up (8 bars): Rising energy
6. Drop (16 bars): Maximum energy
7. Outro (8 bars): Fading

### Energy Curve
```
Intro: 30% → Build-up: 30% → 90% → Drop: 100% → Breakdown: 40% → Build-up: 40% → 100% → Drop: 100% → Outro: 30%
```

## Sound Design Tips

### Layering
- **Kick**: Layer sub (50-100 Hz) + click (2-5 kHz)
- **Clap**: Layer noise + tonal snap
- **Lead**: Layer saw + square + noise

### Processing
- **Compression**: Fast attack, medium release on drums
- **EQ**: Cut mud (200-400 Hz), boost presence (2-5 kHz)
- **Reverb**: Short decay on drums, long on pads
- **Delay**: Sync to tempo (1/4 or 1/8 note)

## MIDI Note Reference

### Common EDM Pitches
- **Sub bass**: A1(33), G1(31), C2(36)
- **Bass**: A2(45), G2(43), C3(48)
- **Lead**: A4(69), G4(67), C5(72)
- **Chords**: Am(57,60,64), C(60,64,67), F(65,69,72)

### Velocity Guide
- **Kick**: 100-120
- **Clap**: 90-110
- **Hi-hat**: 60-80 (closed), 80-100 (open)
- **Lead**: 80-100
- **Bass**: 90-110

## Chord Progressions (和弦进行配方)

| 名称 | 级数 | C 小调示例（MIDI） | 场景 |
|------|------|-------------------|------|
| Drop 万能 | i–VI–III–VII | Cm(60,63,67)→Ab(68,72,75)→Eb(63,67,70)→Bb(70,74,77) | 128 BPM 大气流行 EDM，每和弦 1 小节 |
| 史诗上扬 | VI–VII–i（–VI） | Ab→Bb→Cm→Ab | Uplifting Trance/Big Room 胜利感 |
| 静态 Vamp | i 或 i–VII | Cm ↔ Bb 各 4–8 小节 | Deep House/Minimal 催眠律动 |
| Progressive 亮色 | i7–III–v7–IV | Cm7(60,63,67,70)→Eb→Gm7(67,70,74,77)→Fm(65,68,72) | add9 电子氛围感 |

Breakdown 用长音 sus 和弦挂起（Csus2 = 60,62,67 持续 2–4 小节）再落回 drop。

## Sidechain 泵动感的 MIDI 表达

真实侧链压缩是音量自动化；纯 MIDI 用「每拍 16 分重触发 + 力度锯齿」模拟：
```
铺底和弦每拍 4 个 16 分（0.25）重触发：
@0.0:0.25 vel 50 → @0.25:0.25 vel 72 → @0.5:0.25 vel 92 → @0.75:0.25 vel 108
（每拍重复「洼-爬-爬-峰」锯齿，泵动深度≈抽低 40–60%）
```
注意：同音高重触发前必须先结束前一个音符（首尾相接合法）。

## Snare Roll 的 0.25 网格替代方案

经典 1/4→1/8→1/16→1/32 阶梯中，32 分超出 0.25 网格，替代配方：
- **三阶爬升**：第 1 小节四分（力度 60→75）→ 第 2 小节八分（70→90）→ 第 3 小节十六分全格（85→115）
- **32 分听感 = 双轨错位**：轨 A 打 @0/@0.5/@1…，轨 B 打 @0.25/@0.75/@1.25…，合起来 0.125 间隔，两轨力度同步爬升 80→115
- 叠加 pitch rise（16 分半音上行 A3→C5，力度 70→110）

## 结构能量曲线（含参数）

| 段落 | 小节数 | 音域 | 力度 | 密度 | 手法 |
|------|--------|------|------|------|------|
| Intro | 8–16 | 氛围音/动机片段 | 60–75 | ★–★★ | 过滤效果、稀疏 |
| Breakdown | 16–32 | 65–74 主旋律 | 70–85 | ★★★ | 可换新旋律 |
| Build-up | 8–16 | 上升 riser | 渐强 70→120 | ★★→★★★★ | **撤掉底鼓** + snare roll + riser |
| Drop | 16–32 | 60–72 lead hook | 100–127 | ★★★★★ | 全鼓 + bass + lead |
| Outro | 8–16 | 渐弱 | 100→50 | ★★→★ | 逐层抽离 |

完整进行/织体/节奏配方库见 amr-compose 的 references/pattern-library.md。
