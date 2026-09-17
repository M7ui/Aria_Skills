#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自安装器：把本包部署到 ~/.agents（供支持 skills 扫描的 Agent 工具自动发现）。

仅覆盖本包内包含的技能与工具包，不影响 ~/.agents 下的其他内容。幂等，可重复执行。
用法：python install.py
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AGENTS = Path.home() / ".agents"

# 不部署的运行时垃圾：字节码缓存与测试临时文件
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "_tmp*")


def mirror(src, dst):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=IGNORE)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ok = True
    for skill in ("aria-compose", "aria-music-theory"):
        src = ROOT / "skills" / skill
        if not src.exists():
            print(f"[跳过] 缺少 {src}")
            ok = False
            continue
        mirror(src, AGENTS / "skills" / skill)
        print(f"[安装] skills/{skill} -> {AGENTS / 'skills' / skill}")

    for tk in ("aria-midi", "aria-decode", "aria-report", "aria-roll", "aria-mcp"):
        src = ROOT / "toolkits" / tk
        if not src.exists():
            print(f"[跳过] 缺少 {src}")
            ok = False
            continue
        mirror(src, AGENTS / "toolkits" / tk)
        print(f"[安装] toolkits/{tk} -> {AGENTS / 'toolkits' / tk}")

    print("\n完成。" if ok else "\n部分内容缺失，请检查包完整性。")
    bins = "、".join(str(AGENTS / "toolkits" / tk / "bin")
                    for tk in ("aria-midi", "aria-decode", "aria-report", "aria-roll", "aria-mcp"))
    print(f"提示: 将 {bins} 加入 PATH 后，"
          "可直接使用 aria-midi / aria-decode / aria-report / aria-roll / aria-mcp 命令。")
    print("注意: aria-report 依赖同级的 aria-decode；aria-mcp 依赖其余三个 toolkit "
          "与同级的 skills/ 知识库，请一并安装、不要单独拷贝。")
    print("")
    print("接入 MCP 客户端：把 aria-mcp 注册为 stdio MCP 服务端，例如")
    print(f'  {{"mcpServers": {{"aria": {{"command": "python", "args": '
          f'["{AGENTS / "toolkits" / "aria-mcp" / "aria_mcp.py"}"]}}}}}}')
    print("详见 toolkits/aria-mcp/README.md（含各客户端配置落点）。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
