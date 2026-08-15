---
name: aria-music-theory
description: 音乐理论知识与风格技法问答——音阶、和弦、和弦进行、编曲手法、风格特征（流行/EDM/爵士/Tropical House）的查询与解释。当用户询问"什么是 ii-V-I、布鲁斯音阶有哪些音、怎么写 Drop、如何配和弦、这是什么调式、这段旋律是什么调"等乐理/编曲问题时触发。需要实际产出音乐文件（写歌/生成 MIDI）时改走 aria-compose。
metadata:
  version: "1.0.0"
  category: music
  author: aria
  requires:
    bins: [python]
---

# aria-music-theory — 乐理与风格知识问答

回答乐理与编曲问题。**知识在 references/styles/ 下，计算用 `aria_midi.py scale` 子命令验证**，不要心算音程与音名。

## 知识路由表（先查表，再读文件）

| 用户问题 | 读 references/styles/ 哪个文件 |
|----------|-------------------------------|
| 通用作曲技巧：休止、动机、力度、呼吸 | `techniques.md` |
| 流行歌曲：和弦进行、hook、配器 | `pop-music.md` |
| 电子舞曲：鼓组、Drop、Build-up、Sidechain | `edm-production.md` |
| 爵士：ii-V-I、voicing、即兴、Walking Bass | `jazz-improvisation.md` |
| Tropical House / Kygo 风格 | `tropical-house.md` |

## 音阶速查（音程：半音数，0=根音）

| 音阶 | 音程 |
|------|------|
| major 大调 | 0,2,4,5,7,9,11 |
| minor 自然小调 | 0,2,3,5,7,8,10 |
| harmonic_minor 和声小调 | 0,2,3,5,7,8,11 |
| melodic_minor 旋律小调 | 0,2,3,5,7,9,11 |
| pentatonic_major 大调五声 | 0,2,4,7,9 |
| pentatonic_minor 小调五声 | 0,3,5,7,10 |
| blues 布鲁斯 | 0,3,5,6,7,10 |
| dorian 多利亚 | 0,2,3,5,7,9,10 |
| phrygian 弗里几亚 | 0,1,3,5,7,8,10 |
| lydian 利底亚 | 0,2,4,6,7,9,11 |
| mixolydian 混合利底亚 | 0,2,4,5,7,9,10 |
| locrian 洛克里亚 | 0,1,3,5,6,8,10 |
| whole_tone 全音 | 0,2,4,6,8,10 |

## 和弦速查（音程：半音数，0=根音）

| 和弦 | 音程 | 和弦 | 音程 |
|------|------|------|------|
| maj | 0,4,7 | min | 0,3,7 |
| dim | 0,3,6 | aug | 0,4,8 |
| maj7 | 0,4,7,11 | min7 | 0,3,7,10 |
| dom7 | 0,4,7,10 | m7b5 | 0,3,6,10 |
| dim7 | 0,3,6,9 | sus4 | 0,5,7 |
| sus2 | 0,2,7 | maj9 | 0,4,7,11,14 |
| min9 | 0,3,7,10,14 | add9 | 0,4,7,14 |

## 用 CLI 计算验证（不要心算）

CLI 定位：优先用 PATH 中的 `aria-midi` 命令；否则用包内相对路径
`python <本 SKILL.md 所在目录>/../../toolkits/aria-midi/aria_midi.py`（skills/ 与 toolkits/ 同级）。

```bash
aria-midi scale --root C4 --type minor --list          # 列音阶音
aria-midi scale --root G4 --type major --chord dom7    # 列和弦音
aria-midi scale --root C4 --type major --snap 61 63 66 # 调式吸附
aria-midi scale --suggest 60,62,64,65,67,69,71         # 由音高推测调式
```

## 常见问答模式

- **"X 和弦由哪些音组成？"** → 用 `scale --chord` 验证后按「音名 + MIDI 编号」回答
- **"这段旋律是什么调？"** → 收集音高 → `scale --suggest`，按覆盖率排序给出候选
- **"某风格有什么特征？"** → 读对应 styles 文件，回答结构（段落/Drop/BPM/配器）
- **"怎么写好旋律？"** → 讲 techniques.md 的休止/动机/力度，并指向 aria-compose 执行
- **音程换算** → 用 `scale --list` / `--chord` 输出 MIDI 编号反推

## 与 aria-compose 的分工

| 场景 | 用哪个 |
|------|--------|
| 解释概念、列音阶和弦、分析风格 | 本技能（aria-music-theory） |
| 用户要"写出来"：生成 song.json / MIDI 文件 | aria-compose（它会按需跨引用本技能的知识库） |

回答知识问题时不产出文件；一旦用户意图转向「写/生成音乐」，转交 aria-compose 工作流。
