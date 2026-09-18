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

`analyze` 除总分/技术分/音乐性分/结构分外，另在 `details` 给出**情感与线条**指标
（2026-09 新增）：`sounding_ratio`（发声占比）、`scalar_run_mean`（音阶跑动均长）、
`continuity_points`（线条连续性）、`leaps_per_min`、`leap_resolve_rate`、
`asc_mean`/`desc_mean`，以及 `details.structure.phrase_ending_alternation`。
放行前除看分数，还应看：发声占比 ≥0.8、音阶跑动均长 ≤1.5、线条连续性 ≥2.5。

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

### aria-roll — 钢琴卷帘渲染（看得见、听得见）

把 `song.json` **或任意 `.mid`** 渲染成自包含 HTML 卷帘：Canvas 卷帘 + Web Audio 现场合成播放，双击即看、按播放即听，不需要 DAW / 插件 / 音源。也可输出静态 SVG 供可读图的 Agent 使用。

零依赖 Python CLI（仅标准库 + 复用 aria-decode 读 .mid）：`roll`。退出码契约同 aria-midi。

```
python <本包目录>/toolkits/aria-roll/aria_roll.py roll --input song.json [--format html|svg]
# 或把 toolkits/aria-roll/bin 加入 PATH 后直接：
aria-roll roll --input <song.json 或 x.mid> [--output r.html] [--format html|svg]
```

交付作曲成果时，除 `.mid` 外一并给出 `<歌名>.html` —— 人可以当场试听与查看，不必离开对话去开 DAW。

### aria-mcp — MCP 服务端（跨 Agent 适配层）

把上面三个工具连同知识库包装成 MCP 服务端，使**任何支持 MCP 的客户端**都能调用 Aria——包括没有 shell、也读不到提示词的 GUI 类 Agent。零依赖：手写 stdio JSON-RPC 2.0，不引官方 SDK，无需 pip 安装。

暴露 11 个 tools（`scale_list` / `chord_tones` / `snap_pitches` / `suggest_scale` / `validate_song` / `analyze_song` / `generate_midi` / `inspect_midi` / `decode_midi` / `compare_style` / `report_midi`）与 18 个 resources（`skills/` 下全部 Markdown，按需拉取）。

```
python <本包目录>/toolkits/aria-mcp/aria_mcp.py            # stdio 传输
python <本包目录>/toolkits/aria-mcp/aria_mcp.py --selftest # 自检
```

客户端注册（`mcpServers` 为通用键，各客户端文件名不同）：

```json
{"mcpServers": {"aria": {"command": "python",
  "args": ["<本包目录>/toolkits/aria-mcp/aria_mcp.py"]}}}
```

设计要点：MIDI 以 **base64** 进出（客户端与服务端可能不共享文件系统）；`isError` 只表示工具没跑成，`validate_song` 查出错误时返回正常的 `ok:false` + `errors` 列表，**不**标成错误——否则 Agent 会把正常校验当成工具崩溃而读不到报错详情。各客户端配置落点见 `toolkits/aria-mcp/README.md`。

## 四种使用方式

1. **支持 MCP 的工具**（覆盖面最广，推荐）：把 `aria-mcp` 注册为 stdio MCP 服务端。不需要 shell，也不需要 Agent 读提示词。
2. **自动发现**（支持 skills 扫描的工具，如 ZCode/Claude Code）：运行本包内 `python install.py`，把 skills 与 toolkits 部署到 `~/.agents/` 即可被扫描加载。`aria-report` 依赖同级的 `aria-decode`；`aria-mcp` 依赖其余三个 toolkit 与同级的 `skills/` 知识库，**一并部署，不要单独拷贝**。
3. **显式加载**（任何工具）：让 Agent 读取 `skills/aria-compose/SKILL.md`，按其五步工作流执行；SKILL.md 内的 CLI 定位规则已按包内相对路径设计，复制到任何目录都有效。
4. **仅用 CLI**：不需要提示词时，按各 toolkit 的 README 直接调命令行（aria-midi / aria-decode / aria-report / aria-roll / aria-mcp）。

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

# 4. 诊断：analyze 不参与放行（总分在音符层面无梯度）；--baseline 看人写分位数落点；
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

### 项目布局（每首歌一个目录）

**不要把 `song.json` 直接写在项目根目录。** 固定文件名必然撞名，实际会演变成
`sad.song.json`、`wd222.song.json` 这类前缀混战。约定：

```
<项目>/
└── <歌名>/                     # 目录名 = song.json 顶层的 name
    ├── song.json              # {"name": "<歌名>", "bpm": ..., "tracks": [...]}
    ├── chords.json            # 和弦进行（可选）
    ├── <歌名>.mid             # 由 name 自动派生，无需 --output
    └── build_<歌名>.py        # 生成脚本（长曲/重复织体时用）
```

```bash
aria-midi generate --input 未寄出的信/song.json     # → 未寄出的信/未寄出的信.mid
```

`generate` 的 `--output` 可省：顶层有 `name`（或给 `--name`）时派生
`<输入目录>/<歌名>.mid`，并把歌名写入 MIDI 序列名（DAW 显示为曲名）。
两者都没有才报用法错误（退出码 2），与旧行为一致。

**诊断产物默认不落盘。** 回读核对、事件明细、解码结果都是看一眼就扔的中间物
（实测能占一次作曲过程产出体积的 87%）。用 `--output -` 走管道，或直接看 stdout。
确实要留存时放进歌曲目录、命名 `<歌名>.qa.json`，并在交付时说明可再生。

**长曲用生成脚本。** 超过约 16 小节、或伴奏有重复织体时，写 `build_<歌名>.py`
把音符序列化成 song.json，而不是手写几百个 JSON 对象：重复织体压成函数、返修改一处重跑、
不会手误写坏 0.25 网格。脚本不做乐理计算（音阶和弦用 `aria-midi scale` 查）、不校验、不写 MIDI。

## 快速开始

用户说「写一段 C 大调流行旋律」→ 读 aria-compose SKILL.md → 五步工作流：
`validate --strict` → `analyze` → `generate` → `inspect` → 交付 `<歌名>/song.json` + `<歌名>/<歌名>.mid` + 摘要。

用户说「把 song.mid 解码成 JSON」→ `aria-decode decode --input song.mid --output song.json`，交付含全部事件的 JSON。

用户说「拆解分析这段 MIDI 是什么风格 / 生成旋律动机报告」→ 把 `.mid` 放入 `decode/` 目录 → `aria-report report --input decode/`，交付风格判断 + 调式推测 + 旋律动机报告。

用户说「让我看看/听听这段音乐」→ `aria-roll roll --input <song.json 或 x.mid>`，交付自包含 HTML 卷帘（浏览器里直接播放）。

## 事实源与更新

本目录（aria-* 谱系）即当前维护版本，直接在此修改。早期由 `D:\Document\AMR\AiMidi-Skills\skills-source\`（amr-* 谱系）打包演化而来，两者已分叉，勿回改旧工作区。
