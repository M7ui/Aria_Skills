# AMIDI 技能包接入指引（AGENTS.md）

本目录是自包含的音乐创作技能包：**提示词（Skills）+ 工具包（Toolkit）**。任何能读文件/执行命令的 Agent 工具均可使用。

## 技能清单（skills/）

| 技能 | 触发场景 | 入口 |
|------|---------|------|
| amr-compose | 用户要求写/创作/生成旋律、歌曲、背景音乐、MIDI、和弦进行（compose music / generate MIDI / chord progression / melody） | `skills/amr-compose/SKILL.md` |
| amr-music-theory | 乐理与风格问答：音阶、和弦、进行、编曲技法（music theory / scale / chord voicing） | `skills/amr-music-theory/SKILL.md` |

两技能通过 description 互设负向路由（作曲产出文件走 amr-compose；纯问答走 amr-music-theory）。

## 工具包（toolkits/）

### amr-midi — 作曲 CLI

零依赖 Python CLI（仅标准库，Python 3.8+）：`generate / validate / inspect / scale / analyze`。
JSON 进出，退出码 0=成功 / 1=数据错误 / 2=用法错误。

```
python <本包目录>/toolkits/amr-midi/amr_midi.py <子命令> [参数]
# 或把 toolkits/amr-midi/bin 加入 PATH 后直接：
amr-midi <子命令> [参数]
```

### amr-decode — MIDI → JSON 无损解码器

零依赖 Python CLI（仅标准库，Python 3.8+）：`decode`。无损解码全部 MIDI 事件（meta/CC/弯音/歌词/SysEx/系统消息），PPQN 与 SMPTE 双时基，JSON 进出，退出码契约同 amr-midi。

```
python <本包目录>/toolkits/amr-decode/amr_decode.py decode --input <file.mid> [--output <file.json>] [--no-events] [--no-notes]
# 或把 toolkits/amr-decode/bin 加入 PATH 后直接：
amr-decode decode --input song.mid
```

## 三种使用方式

1. **自动发现**（支持 skills 扫描的工具，如 ZCode/Claude Code）：运行本包内 `python install.py`，把 skills 与 toolkits 部署到 `~/.agents/` 即可被扫描加载。
2. **显式加载**（任何工具）：让 Agent 读取 `skills/amr-compose/SKILL.md`，按其五步工作流执行；SKILL.md 内的 CLI 定位规则已按包内相对路径设计，复制到任何目录都有效。
3. **仅用 CLI**：不需要提示词时，按 `toolkits/amr-midi/README.md` 直接调命令行。

## 快速开始

用户说「写一段 C 大调流行旋律」→ 读 amr-compose SKILL.md → 五步工作流：
`validate --strict` → `analyze` → `generate` → `inspect` → 交付 song.json + song.mid + 摘要。

## 事实源与更新

本包由 AMIDI-Skills 工作区的 `skills-source/` 打包生成（`package_to_agent.py`）。修改技能请回到工作区改源文件后重新打包，勿直接修改本包内容（install.py 除外）。
