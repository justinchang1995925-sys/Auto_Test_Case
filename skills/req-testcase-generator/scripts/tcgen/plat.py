# -*- coding: utf-8 -*-
"""平台适配层 —— 让同一份管道在 Windows 与 Linux/macOS 上行为一致。

只放「操作系统 / 解释器差异」，不放业务逻辑，也不放项目专有常量。
两件事：

  1. `lark_cli()`  定位 lark-cli 可执行文件（Windows 是 npm 的 .cmd 包装器，
     其余平台是同名脚本），按 `TCGEN_LARK_CLI` → PATH 顺序查找。
     **绝对路径一律不写死在代码里**——实测写死 `C:/Users/<某人>/AppData/.../lark-cli.cmd`
     后，换一台机器（或换一个用户名）全部飞书操作直接 FileNotFoundError，
     而本地 xlsx/drawio 照常产出，很容易误以为"只是飞书没连上"。
  2. `force_utf8_stdout()`  终端编码写不出中文时才换成 UTF-8。
"""
import io
import os
import shutil
import sys

IS_WINDOWS = os.name == 'nt'

#: 覆盖 lark-cli 位置的环境变量（自定义安装路径时设它，别改代码）
LARK_CLI_ENV = 'TCGEN_LARK_CLI'

#: 报错提示里的 Windows 默认安装位置。用 os.sep 拼而不写字面反斜杠：
#: 反斜杠在提示文案里极易被写成 '\\n'（换行）而把路径断成两行。
_WIN_HINT = os.sep.join(('%APPDATA%', 'npm', 'lark-cli.cmd'))

#: 候选可执行名。Windows 上 npm 装出来的是 `lark-cli.cmd`；`shutil.which` 靠
#: PATHEXT 通常也能用裸名字命中，但显式列出 .cmd 更稳（PATHEXT 被改过的机器上仍能找到）。
_NAMES = ('lark-cli.cmd', 'lark-cli') if IS_WINDOWS else ('lark-cli',)


def lark_cli():
    """返回 lark-cli 可执行文件路径；找不到时返回裸名字，让调用处去报错。

    这里不抛异常：`DEFAULT_LARK_CLI` 是模块导入期求值的，若此时就抛，
    则连不碰飞书的纯本地流程（build.py 出 xlsx/drawio）也会一起 import 失败。
    """
    env = (os.environ.get(LARK_CLI_ENV) or '').strip().strip('"').strip("'")
    if env:
        return os.path.expanduser(env)
    for name in _NAMES:
        found = shutil.which(name)
        if found:
            return found
    return 'lark-cli'


def cli_missing_msg(cmd, err=None):
    """lark-cli 起不来时的可执行修法（Windows / Linux 各给一条）。

    逐行拼成 list 再 join，不用「隐式相邻字符串 + % 格式化」那种写法：
    中间一旦插入 `+ _WIN_HINT +`，隐式拼接链就断了，`%` 只作用于最后一段字面量，
    直接 TypeError。
    """
    tail = (': %s' % err) if err else ''
    out = [
        '无法执行 lark-cli（%s）%s' % (cmd, tail),
        '  1) 装并授权：npm i -g lark-cli && lark-cli auth login',
        '     授权凭据存在用户目录下，**不随 skill 目录复制**，换机器必须重新登录',
        '  2) 装在非 PATH 位置时设环境变量 %s 指向可执行文件：' % LARK_CLI_ENV,
        '     Windows  ' + _WIN_HINT,
        '     Linux    /usr/local/bin/lark-cli 或 ~/.nvm/versions/node/<ver>/bin/lark-cli',
    ]
    return '\n'.join(out)


def force_utf8_stdout():
    """stdout 写不出中文时换成 UTF-8；写得出就一动不动。

    交付件名称与门禁结论全是中文，Ubuntu 在 `LC_ALL=C` 之类的环境里 stdout
    可能是 ASCII，print 直接 UnicodeEncodeError。
    **只在确实写不出时才换**：Windows 控制台的 cp936 本来就能写中文，
    强行改成 UTF-8 反而会在 cp936 控制台里显示成乱码——修一个平台不能弄坏另一个。
    """
    st = sys.stdout
    enc = getattr(st, 'encoding', None)
    if enc:
        try:
            '测'.encode(enc)
            return st
        except (UnicodeError, LookupError):
            pass
    buf = getattr(st, 'buffer', None)
    if buf is None:          # 被换成了 StringIO 之类没有 buffer 的对象，不动
        return st
    sys.stdout = io.TextIOWrapper(buf, encoding='utf-8', errors='replace',
                                  line_buffering=True)
    return sys.stdout
