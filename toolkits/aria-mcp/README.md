# aria-mcp — 零依赖 MCP 服务端

Aria 技能包子工具（v1.0.0）：把 Aria 的能力以 **MCP（Model Context Protocol）** 标准暴露给任意支持 MCP 的 Agent —— **不需要 Agent 有 shell、也不需要 Agent 读得懂提示词**。

```
python <本包目录>/toolkits/aria-mcp/aria_mcp.py          # stdio 传输，由 MCP 客户端拉起
# 或把 bin 加入 PATH 后：
aria-mcp
```

**为什么需要它**：`aria-midi` / `aria-decode` / `aria-report` 是命令行工具，隐含要求 Agent 能执行进程。GUI 类 Agent（桌面客户端、编辑器面板）和沙箱聊天类 Agent 没有这个能力，只能用到 Aria 的知识层。MCP 是目前**唯一跨厂商的工具调用标准**，一个服务端即可覆盖所有支持它的客户端。

## 定位规则

本工具与其余三个 toolkit 同级，并需要能找到 `skills/` 知识库目录。启动时自动向上查找，兼容两种布局：

| 布局 | toolkits 位置 | skills 位置 |
|------|--------------|-------------|
| 仓库检出 | `<root>/toolkits/aria-mcp/` | `<root>/skills/` |
| `~/.agents` 安装 | `~/.agents/toolkits/aria-mcp/` | `~/.agents/skills/` |

两种情况下 `skills/` 都是 `toolkits/` 的兄弟目录。**复制整个 `toolkits/` 目录时请连同 `skills/` 一起**，否则 resources 为空（tools 仍可用）。

## 客户端配置

MCP 客户端普遍使用 `mcpServers` 这个键，但**外层文件名与键名各客户端不同**（格式仍在演进）。通用片段：

```json
{
  "mcpServers": {
    "aria": {
      "command": "python",
      "args": ["/绝对路径/Aria_Skills/toolkits/aria-mcp/aria_mcp.py"]
    }
  }
}
```

各客户端的落点（具体字段以各家文档为准）：

| 客户端 | 配置文件（常见位置） |
|--------|---------------------|
| Claude Desktop | `claude_desktop_config.json` |
| Claude Code | `.mcp.json`（项目）/ `~/.claude.json` |
| Cursor | `.cursor/mcp.json` |
| Windsurf | `mcp_config.json` |
| Cline / Roo | 扩展设置里的 MCP Servers（JSON 编辑） |
| Zed | `settings.json` → `context_servers`（键名不同） |
| Continue | `config.json` → `mcpServers` |

把 `command` 写成绝对路径最稳；若 `python` 不在 PATH，用解释器绝对路径（Windows 下 `.cmd` 垫片也可作为 command）。

**Windows 中文环境注意**：若音轨名出现乱码，在 `generate_midi` 调用里显式传 `name_encoding: "gbk"`。

## 暴露的能力

### tools（11 个）

| 工具 | 作用 |
|------|------|
| `scale_list` | 列出调式音阶音（含 MIDI 编号） |
| `chord_tones` | 列出和弦音 |
| `snap_pitches` | 把音高吸附到调式内 |
| `suggest_scale` | 由音高反推调式（13 音阶 × 12 根音按覆盖率，返回前 5 条） |
| `validate_song` | 校验 song.json（量化/音域/力度/重叠） |
| `analyze_song` | 旋律质量评分（技术/音乐性/乐句结构）+ 中文改进建议 |
| `generate_midi` | song.json → 标准 MIDI（返回 base64） |
| `inspect_midi` | 解析 MIDI 为音符列表（有损，做往返自检用） |
| `decode_midi` | 无损解码 MIDI（保留 CC/弯音/歌词/SysEx 等全部事件） |
| `compare_style` | 产出与参考 MIDI 的多维风格参数对比 |
| `report_midi` | 批量逆向分析（风格识别 + 调式推测 + 动机提取） |

典型作曲闭环（与服务端 `instructions` 里给 Agent 的指引一致）：

```
scale_list / chord_tones 查表
      → validate_song（必须 0 errors）
      → analyze_song（诊断；加 baseline=true 对照人写分位数，不参与放行）
      → generate_midi
      → inspect_midi 回读核对音符数/BPM
```

### resources（18 个知识文档）

`skills/` 下的全部 Markdown 以 `aria://knowledge/<相对路径>` 注册，客户端**按需拉取**，避免把约 4.3 万 token 的知识库一次性灌进上下文：

- `aria://knowledge/aria-compose/SKILL.md` — 作曲五步工作流
- `aria://knowledge/aria-compose/references/pattern-library.md` — 模式库（进行配方/织体/律动/发展技法/结构模板/情绪映射）
- `aria://knowledge/aria-compose/references/composition-rules.md` — 作曲规则总纲
- `aria://knowledge/aria-music-theory/references/styles/*.md` — 各风格知识
- …（`resources/list` 可枚举全部）

## 实现说明

### 零依赖

MCP 的 stdio 传输本质是「**按行分隔的 JSON-RPC 2.0**」，因此这里用标准库手写实现，**不引入官方 `mcp` SDK，不需要任何 pip 安装** —— 保住本包「复制即用」的卖点。

已实现的方法：`initialize`、`ping`、`tools/list`、`tools/call`、`resources/list`、`resources/read`，以及 `notifications/*` 通知（按协议不作响应）。

### 三个关键设计决策

**1. 传内容，不传路径。** MCP 客户端与服务端可能不共享文件系统（远程/容器场景），所以 MIDI 一律以 **base64** 进出：`generate_midi` 返回 `midi_base64`，`inspect_midi` / `decode_midi` / `compare_style` 接受它。服务端内部用临时文件承接 CLI 的文件参数，用完即删。

**2. `isError` 只表示「工具没跑成」，不表示「结论是否定」。** `validate_song` 查出错误时 CLI 退出码为 1，但 stdout 仍是一份完整的结构化结果。这种情况返回正常的 `ok:false` + `errors` 列表，**不**标成 `isError` —— 否则 Agent 会把一次正常的校验当成工具崩溃，从而读不到它最需要的报错详情。

**3. stdout 只走协议，日志走 stderr。** 任何多余的 `print` 都会破坏 JSON-RPC 消息流，因此诊断信息一律 `stderr`。

### 复用而非重写

所有音乐计算通过 subprocess 调用同包已发布的 CLI，并解析其稳定的「JSON 进 JSON 出」契约。**不改动 `aria-midi` / `aria-decode` / `aria-report` 的任何代码**，也不重复实现乐理逻辑。测试套件里有一条「MCP 与 CLI 结果逐字段一致」的用例来锁住这一点。

## 测试

```
python tests/run_tests.py
```

40 个用例 87 项断言，分协议层与工具层：

- **协议层**：`initialize` 握手与版本协商、通知不响应、`ping`、`tools/list` 与 inputSchema 自洽性（required ⊆ properties、array 带 items）、未知方法 `-32601`、缺 method `-32600`、非法 JSON `-32700`、`serve()` 分帧（空行忽略/通知不产出响应/id 顺序）、stdout 每行都是合法 JSON-RPC、`handle()` 对畸形输入永不抛异常
- **资源层**：列表字段、读取正文、未知 URI 被拒、**路径穿越被拒**（`../` 与 `..%2f` 等四种变体）
- **工具层**：11 个工具的正路与错路；`generate → inspect` 往返音符数一致；校验失败是 `ok:false` 而非 `isError`；文件名目录穿越被抹平
- **一致性**：`validate` / `analyze` 的 MCP 结果与 CLI 直调**逐字段相同**
- **进程级**：真实子进程走 stdio 端到端、空 stdin 正常退出、`--version` / `--selftest` / `--help`

## 已知限制

- **要求 Agent 支持 MCP。** 不支持 MCP 且无 shell 的 Agent 仍只能用知识层（可读 resources 对应的 Markdown 文件）。
- **单次调用无状态。** 服务端不在调用之间保留会话状态，每次都要把 song.json 完整传进来。作品较大时 payload 会偏大。
- **`decode_midi` 输出可能很大。** 一个 658 音符文件的**完整**解码约 50 万字符，会超过单条返回上限（40 万字符）。建议默认用 `include_events: false`（或 `include_notes: false`）只取所需的一半，仅在需要查 CC/弯音/Tempo 变化时才开完整模式。超限时返回的是一个**合法 JSON 信封**（`truncated: true` + 实际大小 + 前 2000 字符预览 + 缩小提示），不是截断的半截 JSON —— 客户端始终能 `parse`。
- **`report_midi` 的动机分析对单轨多声部文件无意义。** 它按「平均音高最高的轨」选旋律轨，若一个轨里混装了低音+和弦+旋律，检出的「动机」会是跨声部大跳的假象。详见 `toolkits/aria-report/README.md` 的已知限制。
- **协议版本演进。** 已声明支持 `2024-11-05` / `2025-03-26` / `2025-06-18`；客户端请求未知版本时回落到 `2024-11-05`。MCP 规范仍在变动，后续新版本可能需要跟进。
- **超时上限 120 秒/次**，批量 `report_midi` 处理大量文件时可能触及。

## 许可

MIT（见仓库根目录 LICENSE）。
