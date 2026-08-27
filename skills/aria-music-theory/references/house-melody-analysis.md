# House 多风格旋律拆解

> 用途：写 House 前，先拆真实 MIDI，把「鼓组节奏 / 低音 / 和弦 / 旋律」分别提取出来，再落到 song.json。
> 真实素材：`examples/midi/deephouse-demo.mid`、`examples/midi/tropical-demo.mid`、`examples/midi/lofi-demo.mid`。

## 1. 拆解步骤

```bash
# 第 1 步：快速看全局
python <技能包根目录>/toolkits/aria-decode/aria_decode.py decode --input examples/midi/deephouse-demo.mid --no-events

# 第 2 步：按音轨提取音符
python <技能包根目录>/toolkits/aria-midi/aria_midi.py inspect --input examples/midi/deephouse-demo.mid

# 第 3 步：按小节分组，写出每个小节的鼓 / 低音 / 和弦 / 旋律
# 第 4 步：把拆出的和弦进行、旋律轮廓、节奏型写成风格参考
```

拆解顺序固定：鼓 → 低音 → 和弦 → 旋律。先确定律动，再确认和声，最后分析旋律为什么“落在这些拍上”。

## 2. Deep House 真实拆解（deephouse-demo.mid）

### 2.1 全局

| 项目 | 值 |
|------|-----|
| BPM | 126 |
| 拍号 | 4/4 |
| 长度 | 8 小节 |
| 音轨 | 鼓组 / 低音 / 和弦Stab / 旋律Hook |
| 音色 | 低音 Program 38；和弦 Program 4；旋律 Program 5 |

### 2.2 鼓组节奏

```text
Kick:   C2(36) 每拍正拍，0/1/2/3，力度 105
Clap:   D#2(39) 第 1、3 拍，力度 75
Hat:    F#2(42) 每个反拍 0.5/1.5/2.5/3.5，力度 45
Open:   A#2(46) 每小节第 4 反拍 3.5，力度 55
```

这是标准 Deep House 骨架：four-on-the-floor + 反拍 Hat + 正拍 Clap。

### 2.3 低音与和弦

| 小节 | 低音（反拍） | 和弦 Stab（反拍） | 级数（A minor） |
|------|--------------|-------------------|-----------------|
| 1–2 | A2 (45) | Am7：A3 C4 E4 G4 | i7 |
| 3–4 | F2 (41) | Fmaj7：F3 A3 C4 E4 | VI maj7 |
| 5–6 | C2 (36) | C：C3 E3 G3 C4 | III |
| 7–8 | G2 (43) | G7：G3 B3 D4 F4 | VII7 |

进行为 `i7 – VI – III – VII7`，即 A 小调版的经典 `i–VI–III–VII`。

低音和 Stab 都落在反拍：`0.5/1.5/2.5/3.5`，与 Kick 正拍错开，这是 Deep House 的“咬合感”来源。

### 2.4 旋律 Hook 拆解

| 小节 | 和弦 | 旋律音 | 分析 |
|------|------|--------|------|
| 1–2 | Am7 | E5-D5-C5-A4 → 重复 | 强位 C/E/A 都是和弦音，D 是弱拍外音 |
| 3–4 | Fmaj7 | C5-A4-F4-A4 → 重复 | 全部落在 Fmaj7 和弦音上 |
| 5–6 | C | E5-D5-C5-G4 → 重复 | E/C/G 和弦音，D 为经过音 |
| 7–8 | G7 | D5-B4-G4-B4-D5-C5 | G7 音为主，C5 在句尾形成引导下一循环的经过音 |

规律：

- Hook 从 `0.75`（反拍后）进入，避开正拍
- 每个 2 小节乐句内部先原样重复一次
- 旋律轮廓整体下行，最后 C5 连接回 Am7 循环
- 力度按 `85 → 78 → 82 → 78` 做小弧线，不机械

## 3. Tropical House 真实拆解（tropical-demo.mid）

### 3.1 全局

| 项目 | 值 |
|------|-----|
| BPM | 112 |
| 拍号 | 4/4 |
| 长度 | 16 小节 |
| 音轨 | 旋律 / 和弦Stab / 铺底Pad / 低音 / 鼓组 |
| 旋律音色 | Program 12（马林巴类） |

### 3.2 和弦进行

每小节一个和弦：

```text
Em – C – G – D（4 小节循环，共 4 轮）
```

Stab 节奏不是每拍满打，而是 `0.0:0.75 + 1.5:0.5 + 3.0:1.0`，制造轻快、不密集的摆动。

### 3.3 旋律拆解

旋律以两小节为一句，整体轮廓：

```text
B4 D5 B4 A4 | G4(长) C5
C5 D5 E5 D5 | G4(长) D5
D5 E5 D5 B4 | G4(长) A4
A4 B4 A4 F#4 | D5(长) C5
```

规律：

- 多用级进和邻音，基本在 G 大调/E 小调五声音阶感内
- 乐句先上行到高点，再用长音回落
- 长音集中在 G4 / A4 / D5，是旋律的“气口”
- 音色用马林巴/木琴类，旋律不用高速 16 分，而是 0.5–2.0 拍时值

## 4. House 多风格旋律对照

| 风格 | BPM | 和弦色彩 | 旋律形态 | 节奏核心 | 编曲关键 |
|------|-----|----------|----------|----------|----------|
| Deep House | 118–126 | m7、maj7 | 2 小节乐句原样重复，Hook 从反拍后进入 | Kick 正拍 + 低音/Stab 反拍 | 低音与和弦咬合反拍 |
| G-House | 118–126 | 极简小调 stab | 短促 stab，旋律让位 bass/人声 | Kick 正拍 + shuffle swing | 低音主导 + rap 采样切片 |
| Tropical House | 100–115 | 明亮大调/自然小调 | 级进 + 长音回落，马林巴音色 | 稀疏 Stab，鼓点不塞满 | 旋律留白，长音气口 |
| Future House | 122–128 | 小调 7 和弦 | 短促 4 音 Hook，重复为主 | Staccato Stab + Sidechain | 和弦抽吸感 |
| Electro House | 126–130 | 小调/弗里几亚 | 16 分 Pluck/Arp + 问答句 | Build-up 细分加速，Drop 全鼓 | 高频 Lead 和 Bass Riff 对话 |
| Melodic/Progressive | 120–128 | 7/9/11、sus | 长线条旋律，段落内逐步升高 | 长 Pad + Arp 层叠 | 旋律随 Arp 层数推进 |

写 House 时，先选一列，再按真实 MIDI 的拆法逐轨落 song.json。

## 5. 提示词追加块

```text
House 风格策略：
- 子风格：Deep / Tropical / Future / Electro / Melodic Progressive
- 拆解参照：examples/midi/deephouse-demo.mid 或 tropical-demo.mid
- 鼓组：Kick 正拍 / Clap 2、4 / Hat 反拍 / Open Hat 位置
- 低音：正拍或反拍？根音进行是否每 2 小节换？
- 和弦：m7 / maj7 / sus？Stab 落在哪些拍？
- 旋律：从哪一拍进入？2 小节是否重复？长音在哪？最高音在哪？
- 非公式化：允许在某一小节抽掉 Kick、把旋律提前半拍、或换离调和弦，并说明目的
```

## 6. 资料来源

- 本机 `D:\Document\AMR\AiMidi-Skills\e2e-demo` 三个真实 MIDI 演示文件
- 公开 MIDI 数据集（联网后补充）：Hugging Face `ronantakizawa/sampleflip-midi`、GitHub `ldrolez/free-midi-chords`、GitHub `BenLeon2001/Free-Chord-Progressions`
