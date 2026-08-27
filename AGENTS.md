# Aria 技能包接入指引（AGENTS.md）

本目录是自包含的音乐创作技能包：**提示词（Skills）+ 工具包（Toolkit）**。任何能读文件/执行命令的 Agent 工具均可使用。

## 技能清单（skills/）

| 技能 | 触发场景 | 入口 |
|------|---------|------|
| aria-compose | 用户要求写/创作/生成旋律、歌曲、背景音乐、MIDI、和弦进行（compose music / generate MIDI / chord progression / melody） | `skills/aria-compose/SKILL.md` |
| aria-music-theory | 乐理与风格问答：音阶、和弦、进行、编曲技法（music theory / scale / chord voicing） | `skills/aria-music-theory/SKILL.md` |

两技能通过 description 互设负向路由（作曲产出文件走 aria-compose；纯问答走 aria-music-theory）。

## 工具包（toolkits/）

### aria-midi — 作曲 CLI

零依赖 Python CLI（仅标准库，Python 3.8+）：`generate / validate / inspect / scale / analyze`。
JSON 进出，退出码 0=成功 / 1=数据错误 / 2=用法错误。

```
python <本包目录>/toolkits/aria-midi/aria_midi.py <子命令> [参数]
# 或把 toolkits/aria-midi/bin 加入 PATH 后直接：
aria-midi <子命令> [参数]
```

### aria-decode — MIDI → JSON 无损解码器

把任意 `.mid` 无损解码为结构化 JSON，用于逆向分析、格式转换与生成后质检。保留全部事件（meta/CC/弯音/歌词/SysEx/系统消息），支持 PPQN 与 SMPTE 双时基，Tempo 变化按全局时间轴换算秒时间，附 GM 音色名 / CC 控制器名 / 音高名映射。`aria-midi inspect` 只提取音符/音轨名/Tempo，需要完整事件时改用本工具。

零依赖 Python CLI（仅标准库，Python 3.8+）：`decode`。JSON 进出，退出码契约同 aria-midi。

```
python <本包目录>/toolkits/aria-decode/aria_decode.py decode --input <file.mid> [--output <file.json>] [--no-events] [--no-notes]
# 或把 toolkits/aria-decode/bin 加入 PATH 后直接：
aria-decode decode --input song.mid
aria-decode decode --input song.mid --no-events   # 快速概览：头部+全局+音符
aria-decode decode --input song.mid --no-notes    # 只要事件明细
```

### aria-report — MIDI 批量逆向分析报告

把 `decode/` 目录里的 `.mid` 批量拆解，输出「风格识别 + 调式推测 + 旋律动机分析」报告。复用 aria-decode 解码器，适合「拿到人类编曲的 MIDI，想看清它是什么风格、旋律动机怎么发展」的场景。

零依赖 Python CLI（仅标准库 + 复用 aria-decode）：`report`。退出码契约同 aria-midi。

```
python <本包目录>/toolkits/aria-report/aria_report.py report --input decode/ --output report.md
# 或把 toolkits/aria-report/bin 加入 PATH 后直接：
aria-report report --input decode/ [--output report.md] [--format md|json]
```

## 三种使用方式

1. **自动发现**（支持 skills 扫描的工具，如 ZCode/Claude Code）：运行本包内 `python install.py`，把 skills 与 toolkits 部署到 `~/.agents/` 即可被扫描加载。
2. **显式加载**（任何工具）：让 Agent 读取 `skills/aria-compose/SKILL.md`，按其五步工作流执行；SKILL.md 内的 CLI 定位规则已按包内相对路径设计，复制到任何目录都有效。
3. **仅用 CLI**：不需要提示词时，按 `toolkits/aria-midi/README.md` 或 `toolkits/aria-decode/README.md` 直接调命令行。

## 操作细节（Agent 执行时）

### 联网查找机制

- 触发条件：用户要求真实案例/最新编曲手法、风格不在本地知识库、analyze 连续不达标
- 检索方式：中英文模糊关键词各 1–3 轮，**不锁定指定网站**，从结果里提取新词继续细化
- 质量门槛：至少 3 个可验证来源；音阶/和弦用 `aria-midi scale --chord` 复算；MIDI 用 `aria-decode` 拆解
- 落库要求：检索词、采用来源、落库结论写进最终摘要；冲突来源记录差异和选择理由
- 离线降级：网络不可用时使用本地知识库和 `examples/midi/`，摘要标记“未联网校验”

### CLI 定位顺序

1. 先试 `aria-midi --version`；存在则用短命令 `aria-midi <子命令> [参数]`
2. 不存在时用包内路径：`python <本包目录>/toolkits/aria-midi/aria_midi.py <子命令> [参数]`
3. `aria-decode` 同理：`python <本包目录>/toolkits/aria-decode/aria_decode.py decode --input <file.mid>`
4. `aria-report` 同理：`python <本包目录>/toolkits/aria-report/aria_report.py report --input <目录或文件.mid>`

不要用猜的路径；找不到文件时先用 `rg --files toolkits | rg "aria_(midi|decode|report)\.py$"` 定位。

### 作曲执行序列（aria-compose）

```bash
# 1. 查表（不要心算音阶/和弦）
python toolkits/aria-midi/aria_midi.py scale --root C4 --type major --list
python toolkits/aria-midi/aria_midi.py scale --root C4 --type major --chord dom7

# 2. 写 chords.json + song.json（schema 见 skills/aria-compose/references/midi-schema.md）
# 3. 严格校验，必须 ok=true 且 errors=[]
python toolkits/aria-midi/aria_midi.py validate --input song.json --strict

# 4. 评分，score >= 7 且 passed=true 才放行；structure_score >= 6 检查乐句连贯性；
#    不达标按 suggestions 修改后重跑（传 --key-root 才会检查终止稳定性）
python toolkits/aria-midi/aria_midi.py analyze --input song.json --chords chords.json --key-root C4

# 5. 生成 + 回读自检
python toolkits/aria-midi/aria_midi.py generate --input song.json --output song.mid --bpm 120
python toolkits/aria-midi/aria_midi.py inspect --input song.mid

# 6. 无损质检（检查 Tempo 变化/CC/弯音等 inspect 看不到的事件）
python toolkits/aria-decode/aria_decode.py decode --input song.mid --output song.qa.json
```

### 退出码契约

| 退出码 | 含义 | Agent 下一步 |
|--------|------|--------------|
| `0` | 成功 | 继续下一环节或交付 |
| `1` | 数据错误 | 读 `errors` / `warnings` 修正 song.json 后重跑 |
| `2` | 用法/IO 错误 | 检查参数、输入路径、输出目录 |

## 快速开始

用户说「写一段 C 大调流行旋律」→ 读 aria-compose SKILL.md → 五步工作流：
`validate --strict` → `analyze` → `generate` → `inspect` → 交付 song.json + song.mid + 摘要。

用户说「把 song.mid 解码成 JSON」→ `aria-decode decode --input song.mid --output song.json`，交付含全部事件的 JSON。

用户说「拆解分析这段 MIDI 是什么风格 / 生成旋律动机报告」→ 把 `.mid` 放入 `decode/` 目录 → `aria-report report --input decode/`，交付风格判断 + 调式推测 + 旋律动机报告。

## 事实源与更新

本目录（aria-* 谱系）即当前维护版本，直接在此修改。早期由 `D:\Document\AMR\AiMidi-Skills\skills-source\`（amr-* 谱系）打包演化而来，两者已分叉，勿回改旧工作区。
