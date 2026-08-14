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


def mirror(src, dst):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ok = True
    for skill in ("amr-compose", "amr-music-theory"):
        src = ROOT / "skills" / skill
        if not src.exists():
            print(f"[跳过] 缺少 {src}")
            ok = False
            continue
        mirror(src, AGENTS / "skills" / skill)
        print(f"[安装] skills/{skill} -> {AGENTS / 'skills' / skill}")

    for tk in ("amr-midi",):
        src = ROOT / "toolkits" / tk
        if not src.exists():
            print(f"[跳过] 缺少 {src}")
            ok = False
            continue
        mirror(src, AGENTS / "toolkits" / tk)
        print(f"[安装] toolkits/{tk} -> {AGENTS / 'toolkits' / tk}")

    print("\n完成。" if ok else "\n部分内容缺失，请检查包完整性。")
    print(f"提示: 将 {AGENTS / 'toolkits' / 'amr-midi' / 'bin'} 加入 PATH 后可直接使用 amr-midi 命令。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
