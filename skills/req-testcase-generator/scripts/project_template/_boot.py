# -*- coding: utf-8 -*-
"""定位 tcgen 包并加入 sys.path。本文件随项目模板一起复制到项目目录。

项目侧固定写法（每个项目脚本开头调用一次，无需关心 skill 的绝对路径）：
    import _boot; _boot.setup()

搜索顺序（命中即止）：
    1. 环境变量 TCGEN_HOME          指向 skill 的 scripts 目录
    2. 同级或祖先目录的 .tcgen_home 文本文件，内容为 skill 目录或其 scripts 目录的路径
    3. 从当前目录逐级向上，试 LAYOUTS 里的每种相对布局
       （项目建在 skill 仓库内、或把 skill 放进项目的 .claude/skills 都能命中）
    4. 用户级安装位置 ~/.claude/skills/... 与 ~/.cursor/skills/...

**跨机器最省事的做法**：在项目目录放一个 `.tcgen_home` 文件，写上 skill 路径：
    Windows   D:/P_TestCase/skills/req-testcase-generator
    Ubuntu    /home/<user>/P_TestCase/skills/req-testcase-generator
这样换机器只改这一个文件，脚本本身不用动。Windows 上正斜杠与反斜杠都能用
（路径一律经 os.path 处理），`~` 会被展开。
"""
import os
import sys

_SKILL = 'req-testcase-generator'

# 每种布局都是「祖先目录 + 相对路径」，指向 skill 目录本身（不含 scripts）
LAYOUTS = (
    os.path.join('skills', _SKILL),                    # 本仓库布局（clone 下来即是）
    os.path.join('.claude', 'skills', _SKILL),         # Claude Code 项目级
    os.path.join('.cursor', 'skills', _SKILL),         # Cursor 项目级
    os.path.join('.agents', 'skills', _SKILL),         # 历史布局，兼容旧项目
    _SKILL,                                            # skill 目录直接放在项目旁
)

CONFIG_NAME = '.tcgen_home'


def _ok(scripts_dir):
    """scripts 目录里必须真有 tcgen 包，避免命中同名空壳目录。"""
    return bool(scripts_dir) and os.path.isdir(os.path.join(scripts_dir, 'tcgen'))


def _as_scripts(path):
    """接受 skill 目录或其 scripts 目录，统一返回可用的 scripts 目录。"""
    if not path:
        return None
    path = os.path.expanduser(path.strip().strip('"').strip("'"))
    if _ok(path):
        return path
    cand = os.path.join(path, 'scripts')
    return cand if _ok(cand) else None


def _ancestors(start):
    d = os.path.abspath(start)
    while True:
        yield d
        parent = os.path.dirname(d)
        if parent == d:
            return
        d = parent


def find():
    tried = []

    # 1. 环境变量
    env = os.environ.get('TCGEN_HOME')
    if env:
        tried.append('TCGEN_HOME=%s' % env)
        got = _as_scripts(env)
        if got:
            return got

    # 2. .tcgen_home 配置文件（当前目录或任一祖先目录）
    for d in _ancestors(os.getcwd()):
        cfg = os.path.join(d, CONFIG_NAME)
        if os.path.isfile(cfg):
            tried.append(cfg)
            try:
                with open(cfg, encoding='utf-8-sig') as fh:
                    for line in fh:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        got = _as_scripts(line)
                        if got:
                            return got
                        break
            except OSError:
                pass

    # 3. 逐级向上试各种相对布局
    for d in _ancestors(os.getcwd()):
        for rel in LAYOUTS:
            got = _as_scripts(os.path.join(d, rel))
            if got:
                return got

    # 4. 用户级安装位置
    home = os.path.expanduser('~')
    for rel in (os.path.join('.claude', 'skills', _SKILL),
                os.path.join('.cursor', 'skills', _SKILL)):
        p = os.path.join(home, rel)
        tried.append(p)
        got = _as_scripts(p)
        if got:
            return got

    raise RuntimeError(
        'tcgen 未找到。三种任选其一：\n'
        '  a) 在项目目录建 %s 文件，内容写 skill 路径，例如\n'
        '     Windows: D:/P_TestCase/skills/%s\n'
        '     Ubuntu : ~/P_TestCase/skills/%s\n'
        '  b) 设环境变量 TCGEN_HOME 指向 skill 的 scripts 目录\n'
        '  c) 把 skill 目录复制到项目的 .claude/skills/ 下\n'
        '已尝试: %s' % (CONFIG_NAME, _SKILL, _SKILL, '; '.join(tried) or '(无)'))


def setup():
    p = find()
    if p not in sys.path:
        sys.path.insert(0, p)
    return p
