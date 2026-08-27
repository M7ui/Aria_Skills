# G-House（Ghetto House）暗黑风制作指南

> 用途：写 G-House 前，先对齐「暗黑坐标」——BPM / swing / 极简小调 stab / sub bass 主导 / rap 人声切片。
> 来源：Melodigging、Last.fm、Minatrix.FM、getit01、edm-ghost-production.com（联网调研沉淀，和弦已用 `aria-midi scale --chord` 复算）。
> 定位：与 Tropical House 是 House 家族明暗两极——Tropical 明亮留白，G-House 阴暗低音驱动。

## 1. 风格定位与出身

- 全称 **Ghetto House**（G = Ghetto「贫民窟」，不是 Gangsta）
- 2010 年代初法国 **Amine Edge & DANCE**（CUFF 厂牌）开创，把 deep/tech house 律动 + gangsta rap 审美融合
- 代表作：Malaa《Notorious》、Tchami《The Sermon》（Confession 厂牌）
- 核心气质：阴暗（dark）、低音驱动、街头 swagger、noir 都市感
- 代表艺人：Malaa、Tchami、Drezo、Matroda、Bijou、Dr. Fresch、Wax Motif、AC Slater（Night Bass）、Destructo、Shiba San

## 2. 关键特征速览

| 维度 | 值 |
|------|-----|
| BPM | 120–126（早期 118–122，融合 Bass House 后 125–130） |
| 拍号 | 4/4 + **55–60% swing**（shuffle 感是灵魂） |
| 和声 | **极简**：短小的小调 stab（常 G/F#/A 小调）+ 过滤和弦 + 偶尔 atmospheric pad |
| 低音 | 绝对主角：Reese/folded saw/FM/失真 808，占 45–80 Hz |
| 人声 | gangsta rap acapella 切片/loop/降调（−1 到 −5 半音） |
| 鼓组 | 909/808：four-on-the-floor + clap 2/4 + off-beat hat + shuffle 填充 |
| 情绪 | 阴暗、挑衅、粗粝、深夜舞池 |

## 3. 和声配方（极简是原则，已复算）

G-House 的和声**故意不铺满**，把空间让给 bass 和人声。小调 stab 为主：

**① 小调 stab 三和弦（常用调：G/F#/A 小调）**

```text
Gm  (55, 58, 62)   F#m (54, 57, 61)   Am (57, 60, 64)
```

**② 暗色 7 和弦（min7 增加暗沉感）**

```text
Gm7 (55, 58, 62, 65)   Am7 (57, 60, 64, 67)
```

**③ 进行配方**

- **静态 Vamp**：`i` 或 `i–VII` 各 4–8 小节（Gm ↔ F），催眠律动
- **极简两和弦**：`i–VI`（Gm–Eb）或 `i–iv`（Gm–Cm），stab 短击、和弦 2 小节一换
- **stab 节奏**：`@0:0.25 + @1.5:0.25 + @3:0.5` 短促弹跳，力度 70–85，不塞满

## 4. 鼓组节奏（909/808，shuffle 感）

```text
Kick:  每拍正拍（four-on-the-floor），力度 100–110，909 音色
Clap:  第 2、4 拍（backbeat），力度 80–95，短促
Hat:   反拍 0.5/1.5/2.5/3.5，力度 45–60，off-beat closed hat
Shuffle: 55–60% swing，附点/三连音感，制造"跛行"律动
```

**swing 在 0.25 网格的表达**：用 `0.75/0.25` 硬 swing 近似三连音（同爵士 swing 处理，见 composition-rules.md 规则 7），或用双轨错位（0.125 间隔）模拟 shuffle 填充。

## 5. Bassline 设计（G-House 的绝对主角）

- **音色**：Reese / folded saw / FM / 失真 808，占 45–80 Hz，带中频质感（俱乐部里能听见）
- **写法**：极简、低沉的短动机重复，不抢人声
- **Kick–Bass 关系**：kick 占 50–60 Hz，bass 基频错开其上下，sidechain 让位
- **示例**：G1(31) 长音 + 反拍 Gm 短击交替，力度 95–115

## 6. 人声与采样（街头气质核心）

- gangsta rap acapella / 原创 rap，切片、loop、**降调 −1 到 −5 半音**匹配阴郁基调
- hook 取一句记忆点短语，drop 里用更紧的切片，breakdown 里放完整段落
- pitch/formant shift 造「低沉、慢速、menacing」质感

## 7. 旋律/stab 手法

- 旋律**让位给 bass 和人声**，不写长旋律线
- 用短促 stab（1–2 音）做点缀，偶尔 atmospheric pad 铺氛围
- 强调「留白」：避免 clutter，让 bass + vocal 扛住整首

## 8. 结构模板（DJ 向）

Intro 16–32（鼓 + 氛围）→ Verse（rap 人声 + 极简 stab）→ Build（tease 人声 + riser）→ Drop（bass-led + 紧切片）→ Breakdown（凸显 verse）→ Drop 2 → Outro 16–32。

**关键**：intro/outro 拉长到 16–32 小节方便 DJ 混音；drop 前先「tease」人声片段，落点更狠。

## 9. 与 Bass House 的辨析（易混）

| 维度 | G-House | Bass House |
|------|---------|------------|
| BPM | 118–126（偏慢） | 125–130（偏快） |
| 核心 | rap 人声采样 + 极简小调 | 脏 reese bass + wub |
| 气质 | 街头 swagger、noir | 更炸、更 grimy |
| 代表 | Malaa、Amine Edge & DANCE | Jauz、Holy Goof、CruCast |

## 10. 提示词追加块

```text
G-House 风格策略：
- 调式：G/F#/A 小调，用 scale --list 验证
- BPM 120–126 + 55–60% swing
- 和声极简：小调 stab 短击，进行 i 或 i–VII 静态 vamp
- 低音主导：Reese/失真 808 占 45–80 Hz，Kick–Bass 错频 + sidechain
- 人声：rap 采样切片 + 降调 −1 到 −5 半音，hook 取记忆点短语
- 鼓组：four-on-the-floor + clap 2/4 + off-beat hat + shuffle
- 结构：16–32 小节 intro/outro，drop 前 tease 人声
- 留白：不 clutter，bass + vocal 扛整首
```

## 11. 资料来源

- Melodigging《G-House》《House》
- Last.fm《G-house music》
- Minatrix.FM《G-House: 街头音乐登上世界舞池》
- getit01 / 网易云《现代的 G-House 到底是怎样一种存在》
- edm-ghost-production.com《Bass House & Tech Bass》
