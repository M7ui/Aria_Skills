---
name: aria-compose
description: 自然语言音乐作曲工作流——把旋律、和弦进行、编曲想法写成 song.json 音符数据并生成标准 MIDI 文件。当用户要求"写/创作/生成 一段旋律、一首歌、背景音乐、MIDI、和弦进行、lo-fi、钢琴曲、电子音乐、伴奏"或任何需要产出可播放音乐文件的请求时触发，即使用户没有明说"作曲"二字。纯乐理知识问答（不产出音乐文件）改走 aria-music-theory。
metadata:
  version: "1.0.0"
  category: music
  author: aria
  requires:
    bins: [python]
---

# aria-compose — 自然语言作曲工作流

把用户的音乐想法变成标准 MIDI 文件。**你是作曲家**，`aria_midi.py` CLI 是你的落盘与校验工具。全流程离线运行，零 LLM API 依赖。

## 输出契约（必须全部交付）

1. `song.json` — 音符数据（schema 见 references/midi-schema.md）
2. `song.mid` — 标准 MIDI 文件（Type-1，TPQN=480）
3. 摘要（中文）— BPM / 调式 / 段落结构 / 音轨数 / 音符数 / 使用的和弦进行

## CLI 调用规范

`aria_midi.py` 与本技能同属一个技能包（`skills/` 与 `toolkits/` 同级）。按以下顺序定位：

1. 若 PATH 中已有 `aria-midi` 命令：`aria-midi <子命令> [参数]`
2. 否则用包内相对路径：`python <SKILL.md 所在目录>/../../toolkits/aria-midi/aria_midi.py <子命令> [参数]`
   （即「技能包根目录下的 toolkits\aria-midi\aria_midi.py」。示例：本技能位于
   `C:\Users\Mark\.agents\skills\aria-compose\` 时，CLI 即
   `C:\Users\Mark\.agents\toolkits\aria-midi\aria_midi.py`；
   位于 `D:\.agent\skills\aria-compose\` 时，CLI 即 `D:\.agent\toolkits\aria-midi\aria_midi.py`）

| 子命令 | 用途 | 退出码 |
|--------|------|--------|
| `validate --input song.json [--strict]` | 校验 schema/音域/力度/量化/重叠 | 0 通过 / 1 有错误 |
| `analyze --input song.json [--chords chords.json] [--key-root C4]` | 0–10 评分 + 中文改进建议 | 0 |
| `generate --input song.json --output song.mid [--bpm 120]` | 生成标准 MIDI 文件 | 0 / 1 / 2 |
| `inspect --input song.mid` | 解析回读 .mid 自检 | 0 / 1 |
| `scale --root C4 --type major [--list/--chord/--snap/--suggest]` | 音阶/和弦计算查表 | 0 / 2 |

## 五步工作流

### 第 1 步：确认需求
明确：风格（流行/EDM/爵士/Tropical House…）、BPM、调式（默认 C major）、长度（默认 8 小节）、音轨需求（旋律/低音/和弦）。用户没说就选合理默认，并在最终摘要中说明。

### 第 2 步：读知识库（写音符前必读）
- 先读 `references/composition-rules.md`（段落规范 + 和弦规范 + 7 大规则）
- 再读 `references/pattern-library.md`（**模式库**：和弦进行配方 / 伴奏织体 / 节奏律动 / 旋律发展技法 / 结构模板 / 情绪参数映射）
- 按风格读 `../aria-music-theory/references/styles/` 对应文件：流行→`pop-music.md`、电子→`edm-production.md`、爵士→`jazz-improvisation.md`、Tropical House→`tropical-house.md`、通用技巧→`techniques.md`
- 用 CLI 查表，不要心算：
  ```bash
  aria-midi scale --root C4 --type major --list        # 音阶音
  aria-midi scale --root G4 --type major --chord dom7  # 和弦音
  ```

### 第 3 步：规划结构（套用模式库）
1. **段落**（3–5 段）：按 pattern-library.md §5 选结构模板（流行 ABABCB / AABA / EDM 能量曲线 / Lo-fi 循环），标注各段小节数、音域、力度、密度
2. **和弦进行**：按情绪查 pattern-library.md §1.7 决策表 → 选 §1 配方（如欢快流行用 I–V–vi–IV、日系抒情用 4536、悲伤用 i–VII–VI–V），写入 `chords.json`（供 analyze 检查强拍匹配）
3. **织体与节奏**：从 §2 选伴奏织体（Alberti/琶音/半分解/柱式/stride/oom-pah/waltz/八度低音）、从 §3 选节奏律动（流行切分/爵士 comping/EDM 鼓组）
4. **音轨分工**：低音 36–50 / 和弦 48–67 / 旋律 60–84，逐轨完成（先旋律后低音）

### 第 4 步：写 song.json（动机式作曲）
严格按 composition-rules.md 的 7 大规则逐个音符写：
- 先发明 2–5 音动机，再发展（重复→移调→变奏）
- 强拍（4/4 的第 1、3 拍）必须落在当前和弦的和弦音上
- 每 1–2 拍后留 0.25–0.5 拍休止；乐句间留 0.5–1 拍呼吸
- 力度成弧线（乐句内极差 ≥15），相邻音符力度不可相同
- 大跳（≥4 半音）后反向级进解决；时值至少混用 3 种
- 所有 start_beat / duration 必须是 0.25 的整数倍

### 第 5 步：验证 → 生成 → 自检（循环直到达标）
```bash
aria-midi validate --input song.json --strict            # 必须 0 errors
aria-midi analyze  --input song.json --chords chords.json
# analyze 分数 < 7 或建议未处理 → 按建议修改 song.json，回到第 4 步
aria-midi generate --input song.json --output song.mid --bpm 120
aria-midi inspect  --input song.mid                      # 核对音符数/BPM 往返一致
```

## 作曲规则速查（详版见 references/composition-rules.md）

1. **动机驱动**：短动机 × 变奏发展，禁止连续上下行音阶
2. **和弦音停留**：强拍必须是和弦音；非和弦音只作弱拍经过音
3. **节奏呼吸**：每 1–2 拍后休止；乐句间 0.5–1 拍呼吸
4. **力度弧线**：乐句内钟形/线性弧线，动态范围 ≥15
5. **跳级平衡**：≥4 半音大跳后反向级进解决
6. **段落对比**：副歌比主歌更高、更响、更密
7. **人性化**：相邻音符力度不同；每次重复至少变 1 个元素

## 质量检查清单（交付前逐项打勾）

- [ ] `validate --strict` 通过（0 errors）
- [ ] `analyze` 分数 ≥ 7 且无未处理建议
- [ ] 每个音轨音域符合分工（低音 36–50 / 和弦 48–67 / 旋律 60–84）
- [ ] 强拍音符落在 chords.json 定义的和弦音上（chord_tone_rate ≥ 60%）
- [ ] 全曲至少 2 处明显休止；力度极差 ≥ 15
- [ ] `generate` + `inspect` 往返：音符数、BPM、时长一致
- [ ] 摘要包含 BPM / 调式 / 段落 / 音轨 / 和弦进行

## 最小示例

用户："写 4 小节 C 大调旋律" → 先写 chords.json（C 全曲），再写 song.json：

```json
{
  "bpm": 120,
  "tracks": [{
    "name": "旋律",
    "channel": 0,
    "program": 0,
    "notes": [
      {"pitch": 67, "start_beat": 0.0, "duration": 0.5, "velocity": 95},
      {"pitch": 69, "start_beat": 1.0, "duration": 0.75, "velocity": 100},
      {"pitch": 72, "start_beat": 2.0, "duration": 1.0, "velocity": 105},
      {"pitch": 64, "start_beat": 3.5, "duration": 0.5, "velocity": 80}
    ]
  }]
}
```

完整范例（流行副歌 / EDM Build-up / 爵士 Walking Bass，含低音轨）见 references/examples.md。

## 常见报错修复

| validate/analyze 报错 | 修法 |
|----------------------|------|
| 音高越界 | 限定 36–96 旋律区（绝对范围 0–127） |
| 力度越界 | 改到 1–127 |
| 非 0.25 量化（off grid） | start/duration 改为 0.25 的整数倍 |
| 同音高重叠 | 缩短前音符或后移后音符 |
| chord_tone_rate 低 | 把强拍音符移到和弦音上 |
| 力度范围小 | 重新设计力度弧线（极差 ≥15） |
| 连奏过多/无休止 | 乐句间插入 0.5–1 拍空隙 |

## Reference Files

| 文件 | 何时读 |
|------|--------|
| `references/composition-rules.md` | 每次写音符前必读（段落+和弦+7 规则+清单） |
| `references/pattern-library.md` | **规划结构时必读**（进行配方/织体/节奏/旋律技法/结构模板/情绪映射） |
| `references/midi-schema.md` | 不确定 JSON 字段/约束/GM 音色时 |
| `references/examples.md` | 需要完整范例参考时 |
| `../aria-music-theory/references/styles/*.md` | 按风格需要（流行/EDM/爵士/Tropical/通用） |
