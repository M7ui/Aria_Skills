# .agent — AiMidi 便携音乐技能包

> AI 音乐创作技能包：**提示词（Skills）+ 工具包（Toolkit）** 一体化封装。
> 由 AI-Music-Roll 项目重构而来，headless 作曲不依赖 Node 服务器、不调用 LLM API。

## 内容

```
.agent/
├── AGENTS.md              # 跨工具接入门面（支持 AGENTS.md 的工具自动发现）
├── README.md              # 本文件
├── install.py             # 自安装器：部署到 ~/.agents 供 skills 扫描
├── skills/
│   ├── amr-compose/       # 作曲工作流：自然语言 → song.json → MIDI（含模式库/规则/范例）
│   └── amr-music-theory/  # 乐理问答：音阶/和弦/进行 + 5 大风格知识库
└── toolkits/
    └── amr-midi/          # 零依赖 Python CLI：generate/validate/inspect/scale/analyze
        ├── amr_midi.py
        ├── README.md
        ├── tests/         # 23 个自测用例（roundtrip/校验/编码/分析）
        └── bin/amr-midi.cmd   # PATH 垫片
```

## 快速使用

```bash
# 1. 安装到 ~/.agents（供 skills 扫描类工具自动发现；幂等，可重复执行）
python install.py

# 2. 直接用 CLI（零安装）
python toolkits/amr-midi/amr_midi.py scale --root C4 --type major --list

# 3. 或加入 PATH 后用短命令
amr-midi generate --input song.json --output song.mid --bpm 120
```

## 完整作曲流程（详见 skills/amr-compose/SKILL.md 五步工作流）

```bash
amr-midi validate --input song.json --strict
amr-midi analyze  --input song.json --chords chords.json
amr-midi generate --input song.json --output song.mid
amr-midi inspect  --input song.mid
```

## 自测

```bash
python toolkits/amr-midi/tests/run_tests.py   # 23 个用例全绿
```

## 事实源

本包由 `D:\Document\AMR\AiMidi-Skills\skills-source\` 打包生成（`package_to_agent.py`）。
修改技能请回工作区改源文件后重新打包。
