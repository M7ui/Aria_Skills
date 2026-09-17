# aria-report — 零依赖 MIDI 批量逆向分析报告

Aria 技能包子工具（v1.0.0）：扫描一个目录（或单个 `.mid`），对每个文件做**风格识别 + 调式推测 + 旋律动机提取**，输出 Markdown 报告或 JSON。仅 Python 标准库（3.8+），解码环节复用同包的 `aria-decode`。

```
python <本包目录>/toolkits/aria-report/aria_report.py report --input <目录或文件.mid> [--output report.md] [--format md|json]
# 或把 bin 加入 PATH 后直接：
aria-report report --input decode/ --output report.md
```

## 定位规则

本工具与 `aria-decode` 同属 `toolkits/` 目录（同级），启动时通过相对路径自动加载 `../aria-decode/aria_decode.py`。**复制整个 `toolkits/` 目录到任意位置均可运行**；若只单独拷贝 `aria-report/`，启动会报错并以退出码 2 退出。

## 特性

| 特性 | 说明 |
|------|------|
| 批量处理 | 输入目录时扫描全部 `.mid` 并按文件名排序；输入单文件时只分析该文件 |
| 无损解码 | 复用 aria-decode，保留全部事件后再做分析 |
| 风格识别 | 基于 BPM / GM 音色 / 调式 的启发式打分，输出 Top 3 候选（附命中理由） |
| 调式推测 | 13 种音阶模板 × 12 个根音的覆盖率排序，输出 Top 3 |
| 动机提取 | 3 音动机（2 个连续音程）的重复检测，标注「原样重复 / 模进（移调）」与全部出现位置 |
| 容错 | 单个文件解码失败不影响整批：该文件记为 `ok: false` 并在报告里单列 |
| 双格式 | `--format md`（默认，人读）/ `--format json`（程序化消费，含全部结构化字段） |
| 中文编码 | 报告以 UTF-8 写出，音轨名 GBK/Big5/Shift-JIS 逐级回退解码 |

## 应用场景

- **逆向分析**：拿到别人编曲的 `.mid`，想快速判断「这是什么风格、什么调、旋律是怎么发展的」
- **素材筛选**：一次扫一批 MIDI，用概览表先看 BPM/风格/调式分布，再决定深入分析哪一个
- **作曲参照**：把自己产出的 `song.mid` 丢进去，看工具推测的调式与风格是否符合预期
- **风格锚定辅助**：配合 `aria-midi compare`（产出 vs 参考 MIDI 的参数对比）一起用

## 用法

```
aria-report report --input <目录或文件.mid> [--output <report.md>] [--format {md,json}]
```

| 选项 | 说明 |
|------|------|
| `--input` | 输入 `.mid` 文件，或包含 `.mid` 的目录（必填） |
| `--output` | 输出报告路径（默认 stdout；`-` 表示 stdout） |
| `--format` | `md`（默认）或 `json` |
| `--version` | 输出版本号 |

**退出码**：`0` 成功 / `1` 数据错误（未找到 `.mid` 文件、写文件失败）/ `2` 用法错误（路径不存在、缺 `--input`、无子命令、输出目录不存在）。

### 示例

```bash
# 分析整个目录（配合仓库根目录的 decode/ 输入目录）
aria-report report --input decode/ --output report.md

# 只分析单个文件，报告打到 stdout
aria-report report --input "Wait Day.mid"

# JSON 输出，交给脚本继续处理
aria-report report --input decode/ --format json > result.json

# 不写 --output 时直接重定向
aria-report report --input decode/ > report.md
```

## 分析维度

### 1. 风格识别（启发式）

按 BPM / GM 音色 / 调式逐条加分，取得分最高的 3 条。全部规则：

| 风格 | 得分 | 命中条件 |
|------|------|----------|
| Lo-fi | 3 | BPM 70–90 |
| Tropical House | 3 | BPM 100–115 且有 Marimba / Steel Drums / Pan Flute / Vibraphone / Kalimba / Xylophone |
| Deep House | 2 | BPM 116–126 且有 Bass 类音色 |
| G-House | 2 | BPM 118–126 + 小调 + Bass 或 Lead 音色 |
| Future House | 2 | BPM 122–128 + Lead 音色 |
| Electro House / EDM | 3 | BPM 126–132 + Lead 音色 |
| 钢琴独奏 / 古典 | 3 | 音色全是 Piano / Organ / Harpsichord / Clavinet，且音色数 ≤ 2 |
| 爵士 | 2 | 有 Sax / Trumpet / Trombone / Brass / Horn |
| 弦乐 / 电影配乐 | 2 | 有 String 类音色且无 Lead |
| 流行 | 1 | 大调 + BPM 90–130 |

同一文件可命中多条，报告按得分降序列出 Top 3。**没有命中任何规则时输出空列表**，报告里提示人工判断。

### 2. 调式推测

对 13 种音阶模板（major / minor / harmonic_minor / melodic_minor / dorian / phrygian / lydian / mixolydian / locrian / pentatonic_major / pentatonic_minor / blues / whole_tone）× 12 个根音计算**覆盖率**（落在该音阶内的音符数 ÷ 总音符数），按下列优先级排序取 Top 3：

1. 覆盖率降序
2. 常见调式优先（`major` / `minor` 优先于教会调式与五声/蓝调）
3. 该根音的出现频次降序

若 MIDI 里带调号 meta（key_signature），风格判断的 `key_mode` 优先采用它。

### 3. 旋律动机提取

旋律轨内取**相邻 3 音**（2 个连续音程）作为动机单元，统计每种音程组合的重复次数：

- 出现 ≥ 2 次才算动机，按出现次数降序取 Top 6
- 起始音高**相同** → 标注「原样重复」；起始音高**不同** → 标注「模进（移调）」
- 每个动机列出全部出现位置（第 N 小节第 X 拍）

旋律轨的选取规则：**排除 GM 鼓通道（channel 9）后，平均音高最高的那一轨**。

## 输出结构

### JSON（`--format json`）

输出为**数组**，每个文件一项：

```json
[
  {
    "file": "demo.mid",
    "ok": true,
    "bpm": 120.0,
    "time_signature": "4/4",
    "duration_sec": 16.0,
    "key_signature": null,
    "track_count": 3,
    "note_count": 27,
    "melody_track": "旋律",
    "melody_note_count": 12,
    "programs": ["Acoustic Grand Piano"],
    "style": [{ "style": "钢琴独奏 / 古典", "score": 3, "reason": "纯钢琴/风琴类音色" }],
    "key_inference": [{ "root": "C", "type": "major", "coverage": 1.0 }],
    "motifs": [
      {
        "intervals": [2, 2],
        "note_names": ["C4", "D4", "E4"],
        "count": 2,
        "technique": "原样重复",
        "positions": [{ "bar": 1, "beat": 0.0 }, { "bar": 2, "beat": 0.5 }]
      }
    ],
    "warnings": []
  }
]
```

解码失败的文件为 `{ "file": "x.mid", "ok": false, "error": "..." }`。

### Markdown（`--format md`，默认）

```markdown
# 旋律动机分析报告

> 分析文件 1 个（成功 1 个）· 工具 aria-report 1.0.0 · 输入 decode/

## 概览

| 文件 | BPM | 调式推测 | 风格（Top1） | 主旋律轨 | 动机数 |
|------|-----|----------|-------------|----------|--------|
| demo.mid | 120.0 | C major | 钢琴独奏 / 古典 | 旋律 | 2 |

## demo.mid

### 基本信息
### 风格判断（启发式，供参考）
### 调式推测
### 旋律动机分析
```

## 测试

```
python tests/run_tests.py
```

38 个用例 73 项断言：调式推测（含相对调式并列）、风格识别各条规则、动机提取（重复/模进/素材不足/无重复）、小节定位、单文件分析、坏文件容错、鼓通道排除、旋律轨选取、meta 调号优先、目录扫描排序、Markdown 渲染（含无动机与解码失败分支）、CLI 退出码（0/1/2）、`--format json`、`--output`、UTF-8 stdout。测试素材在内存中现场构造，结束时自动清理临时目录。

## 已知限制

- **单轨多声部会污染动机分析**：旋律轨按「平均音高最高」选取，若一个轨道里混装了低音 + 和弦 + 旋律（很多导出/合并文件如此），被选中的「旋律」实际含全部声部，动机音程会出现 `-16 +19` 这类跨声部大跳，结果无意义。此时建议先用 `aria-decode` 拆出各声部，或改用多轨 MIDI。
- **调式推测无法区分相对调式**：C major、A minor、D dorian 的音级集合完全相同，覆盖率必然并列 1.0，只能靠「常见调式优先 + 主音频次」排先后。含完整七声的素材比五声素材可信。
- **动机只做音程维度**：只检测音程序列的重复，不检测节奏动机，也不识别倒影 / 逆行 / 时值变化等发展手法（仅有「原样重复 / 模进」两类标注）。
- **小节定位假设 4/4**：`第 N 小节第 X 拍` 一律按 4/4 换算，非 4/4 拍号的文件位置会偏。
- **音色识别依赖 program_change**：无 `program_change` 事件时音色列表为空，「钢琴独奏 / 古典」等依赖音色的规则不会命中。
- **风格判断是启发式**：规则表由 BPM 与音色名匹配构成，不分析节奏型/和声，仅作初筛参考，不能替代人工听判。

## 许可

MIT（见仓库根目录 LICENSE）。
