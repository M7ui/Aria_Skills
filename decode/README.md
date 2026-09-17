# decode/ — MIDI 待拆解目录

把需要 AI 拆解分析的 `.mid` 文件放到这个目录，然后运行：

```bash
python toolkits/aria-report/aria_report.py report --input decode/
```

工具会扫描目录里的所有 `.mid`，逐个：
1. **无损解码**（复用 aria-decode，保留全部事件）
2. **风格识别**（基于 BPM / GM 音色 / 调式的启发式打分，输出 Top 3 候选 + 命中理由）
3. **调式推测**（由音高集合对 13 种音阶的覆盖率排序，输出 Top 3）
4. **旋律动机提取**（3 音动机的重复检测 + 发展手法：原样重复 / 模进（移调））
5. **生成报告**（默认打到 stdout，用 `--output` 才写文件）

完整说明（风格规则表、JSON 字段、退出码、已知限制）见 [`toolkits/aria-report/README.md`](../toolkits/aria-report/README.md)。

## 示例

```bash
# 分析整个目录（报告打到 stdout）
python toolkits/aria-report/aria_report.py report --input decode/

# 指定输出位置
python toolkits/aria-report/aria_report.py report --input decode/ --output my-report.md

# 只分析单个文件
python toolkits/aria-report/aria_report.py report --input decode/foo.mid
```

分析结果同时支持 JSON 输出（`--format json`），供程序化消费。
