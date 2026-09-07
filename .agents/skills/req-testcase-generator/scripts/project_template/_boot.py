# -*- coding: utf-8 -*-
"""定位 tcgen 包并加入 sys.path。本文件随项目模板一起复制到项目目录。

搜索顺序：
    1. 环境变量 TCGEN_HOME
    2. 从当前目录逐级向上找 .claude/skills/req-testcase-generator/scripts
    3. 用户级 ~/.claude/skills/req-testcase-generator/scripts

项目侧固定写法：
    import _boot; _boot.setup()
每个项目脚本开头都调用一次，无需关心 skill 的绝对路径。
"""
import os
import sys

REL = os.path.join('.claude', 'skills', 'req-testcase-generator', 'scripts')


def find():
    env = os.environ.get('TCGEN_HOME')
    if env and os.path.isdir(os.path.join(env, 'tcgen')):
        return env
    d = os.path.abspath(os.getcwd())
    while True:
        cand = os.path.join(d, REL)
        if os.path.isdir(os.path.join(cand, 'tcgen')):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    home = os.path.join(os.path.expanduser('~'), REL)
    if os.path.isdir(os.path.join(home, 'tcgen')):
        return home
    raise RuntimeError(
        'tcgen 未找到。设置 TCGEN_HOME 指向 skill 的 scripts 目录，'
        '或把项目放在含 .claude/skills/req-testcase-generator 的目录树下。')


def setup():
    p = find()
    if p not in sys.path:
        sys.path.insert(0, p)
    return p
