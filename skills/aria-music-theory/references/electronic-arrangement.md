# 电子音乐编曲乐理 × 风格化提示词

> 用途：写 EDM / House / Future Bass / Trance 等电子音乐前，先建立「和声功能 + 舞曲结构 + 音色层次」的编曲决策。
> 来源：eMastered《每个音乐家都应了解的 5 个 EDM 和弦进行式》、魔声 DJ 培训《舞曲制作：构架大纲》、北京现代音乐研修学院《电子音乐风格与编曲》讲座、本包 `edm-production.md`。
> 真实 MIDI 拆解：写 House 时再读 `house-melody-analysis.md` + `examples/midi/`。

## 1. 电子音乐乐理核心

### 1.1 和声功能是情绪，不是教条

- Tonic：稳定、回家；Subdominant：离开、色彩；Dominant：紧张、推进
- 高级乐句通常「和谐与不和谐之间游走」：在属功能上制造不和谐，回到主功能时解决
- 理论是解释，不是禁锢：先解释“为什么合理”，再决定是否打破

### 1.2 EDM 常用和声素材

- 自然调内三和弦为主，大小调混合制造情绪起伏
- 七和弦、加九和弦、挂留和弦增加紧张和色彩
- 常见做法：小调开始，副歌段落换大调或借用和弦
- 和弦进行不一定要复杂：两个和弦或单个持续和弦也可以成立

### 1.3 常用 EDM 进行

| 级数 | 听感 | C 小调 / C 大调示例 |
|------|------|--------------------|
| `i–VI–iv–VII` | 大气舞池感 | Cm → Ab → Fm → Bb |
| `i–III–VII–VI` | Avicii 式上扬 | Cm → Eb → Bb → Ab |
| `i–VI–III–VII` | 神秘、推进 | Cm → Ab → Eb → Bb |
| `IV–I–vi–V` | 流行电子抒情 | F → C → Am → G |
| `i–iv–VII–III` | 电影感、暗色 | Cm → Fm → Bb → Eb |

## 2. 舞曲结构与能量推进

### 2.1 Electro House 经典骨架

| 段落 | 长度 | 内容 | 能量 |
|------|------|------|------|
| 干鼓段 | 8+8 小节 | 鼓组逐层进入 | 30%→40% |
| Breakdown | 8 小节 | 旋律 + 和声为主，抽掉重打击乐 | 40% |
| Build-up | 8 小节 | 鼓加密、Riser、旋律碎片 | 40%→90% |
| Drop | 8+8 小节 | 全鼓 + Bass 最重 + Lead Hook | 100% |
| 再空拍 | 8 小节 | 回归 Breakdown 材料 | 40% |

### 2.2 能量推进手法

- 四分音符鼓 → 八分 → 十六分，细分节奏制造加速
- Riser 音高上行 + 力度渐强 + 鼓组逐层加入
- Drop 前抽空一拍或撤掉低频，让落点更重
- Drop 的 Bass 是全曲最明显的声音；Lead 负责抓耳 Hook
- 第二个 Drop 比第一个多一层和声/Lead，避免机械重复

## 3. 风格化编曲方法

### 3.1 节奏层

- 4/4 four-on-the-floor：Kick 每拍一下
- Clap/Snare 落 2、4 拍
- Hi-hat 反拍，或 Build-up 里从八分变十六分
- Sidechain 泵动用 MIDI 力度锯齿模拟：`50 → 72 → 92 → 108`

### 3.2 和声层

- 和弦节奏可以用 Staccato 短击：`@0:0.25 + @0.5:0.25 + @0.75:0.5`
- 铺底 Pad 用长音 + 7/9/sus 和弦
- 换和弦时保留共同音，内声部级进
- Breakdown 用 sus 挂留拖住张力，再落回 Drop 主和弦

### 3.3 旋律层

- Hook 用 2–4 个音 + 固定节奏，重复 2–4 次
- 旋律以五声音阶和和弦琶音为主，反拍强调
- Build-up 用碎片化上行；Drop 用清晰 Hook
- 每段重复至少变化一个元素：音高、节奏、力度、和声

### 3.4 Bass 层

- 根音 + 五音长音，力度 90–110
- Drop 里 Bass 是能量核心，音色最厚
- Offbeat Bass 可放 `@0.5/@1.5/@2.5/@3.5` 制造推进

## 4. 电子音乐编曲提示词模板

```text
请按以下电子音乐编曲提示词创作，并把决策落到 song.json / chords.json：

- 子风格：House / Future Bass / Trance / Electro / Progressive
- 情绪：舞池 / 史诗 / 暗色 / 梦幻 / 未来感
- BPM 与拍号：例如 128 BPM、4/4
- 调式：例如 A minor，用 scale --list 验证
- 进行：例如 i–VI–III–VII，每和弦几小节
- 和弦色彩：7 / 9 / sus / add9，标出强拍解决点
- 结构：干鼓 8+8 → Breakdown 8 → Build 8 → Drop 16 → Breakdown 8
- 音轨：Lead / Chords / Bass / Pad / Drums，标注 GM 音色和音域
- 能量曲线：每段给出层数、密度、力度范围
- 节奏手法：four-on-the-floor、反拍 Hi-hat、Build 细分、Drop 前抽空
- 张力手法：Riser、sus 挂留、副属或借调和弦
- 反公式化：允许打破 1–2 条默认规则，并说明目的

写完后执行 validate --strict、analyze、generate、inspect，并交付摘要。
```

## 5. 参考来源

- eMastered：每个音乐家都应了解的 5 个 EDM 和弦进行式
- 魔声 DJ 培训：舞曲制作 - 构架大纲
- 北京现代音乐研修学院：电子音乐风格与编曲讲座
- 本包：`references/styles/edm-production.md`、aria-compose `references/pattern-library.md`
