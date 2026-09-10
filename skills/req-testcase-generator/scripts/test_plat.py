# -*- coding: utf-8 -*-
"""跨平台适配回归 —— 守「同一份 skill 在 Windows 与 Ubuntu 上都能跑」。

管道改动后跑：python test_plat.py

存在理由（实测踩过）：`tcgen/feishu.py` 曾把 lark-cli 写成
`C:/Users/<某个用户名>/AppData/Roaming/npm/lark-cli.cmd` 这个绝对路径。
换机器（换用户名、或换到 Ubuntu）后**全部飞书函数一律 FileNotFoundError，
而本地 xlsx/drawio 照常产出**——现象是「交付件都出来了，只有飞书没连上」，
很容易被当成网络或授权问题查半天，实际是路径写死。
`t_no_hardcoded_abs_path` 是这条的直接守卫：扫 tcgen/ 全包，
任何盘符绝对路径或写死的用户目录都会被抓出来。

另一半同等重要：**修 Linux 不能弄坏 Windows**。原来两个测试文件无条件把 stdout
包成 UTF-8，在 Windows 的 cp936 控制台里输出的中文反而是乱码。
`t_stdout_kept_when_encodable` / `t_stdout_switched_when_ascii` 成对守这件事。

不联网、也不要求本机真的装了 lark-cli。
"""
import ast
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcgen import feishu, plat  # noqa: E402

plat.force_utf8_stdout()

HERE = os.path.dirname(os.path.abspath(__file__))


class Env(object):
    """临时设/清环境变量，退出时精确还原（原来是 None 就删掉，不留空串）。"""

    def __init__(self, **kw):
        self.kw = kw

    def __enter__(self):
        self.old = dict((k, os.environ.get(k)) for k in self.kw)
        for k, v in self.kw.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class FakeStdout(object):
    """假 stdout：encoding 可控，写入的字节收在 buffer 里，用来测编码切换两条路。"""

    def __init__(self, encoding):
        self.encoding = encoding
        self.buffer = io.BytesIO()

    def write(self, s):
        self.buffer.write(s.encode(self.encoding))

    def flush(self):
        pass


class Stdout(object):
    def __init__(self, fake):
        self.fake = fake

    def __enter__(self):
        self.orig = sys.stdout
        sys.stdout = self.fake
        return self.fake

    def __exit__(self, *exc):
        sys.stdout = self.orig


# ---------------- lark-cli 定位 ----------------

def t_env_override_wins():
    """TCGEN_LARK_CLI 优先于 PATH —— 装在非标准位置时的唯一开关。"""
    with Env(TCGEN_LARK_CLI='/opt/custom/lark-cli'):
        got = plat.lark_cli()
    assert got == '/opt/custom/lark-cli', got
    # 带引号/空格也要能吃：从 Windows 属性面板复制路径常常带引号
    with Env(TCGEN_LARK_CLI='  "/opt/q/lark-cli"  '):
        got2 = plat.lark_cli()
    assert got2 == '/opt/q/lark-cli', got2
    return 'env 覆盖生效，且去掉引号与空格'


def t_env_expands_user():
    """`~` 必须展开 —— Linux 上 nvm 装的 lark-cli 常写成 ~/.nvm/.../bin/lark-cli。"""
    with Env(TCGEN_LARK_CLI='~/bin/lark-cli'):
        got = plat.lark_cli()
    assert '~' not in got, got
    assert got.replace(os.sep, '/').endswith('bin/lark-cli'), got
    return '~ 已展开'


def t_falls_back_to_bare_name():
    """PATH 里没有时返回裸名字，**不抛异常**。

    DEFAULT_LARK_CLI 在模块导入期求值：此处若抛，连根本不碰飞书的纯本地流程
    （build.py 出 xlsx/drawio）都会 import 失败。
    """
    orig = plat.shutil.which
    plat.shutil.which = lambda *a, **kw: None
    try:
        with Env(TCGEN_LARK_CLI=None):
            got = plat.lark_cli()
    finally:
        plat.shutil.which = orig
    assert got == 'lark-cli', got
    return '找不到时返回裸名字，不抛异常'


def t_windows_prefers_cmd():
    """Windows 上先试 lark-cli.cmd —— npm 装出来的是 .cmd 包装器。"""
    seen = []

    def fake_which(name):
        seen.append(name)
        return 'X:/npm/' + name if name.endswith('.cmd') else None

    orig_which, orig_names = plat.shutil.which, plat._NAMES
    plat.shutil.which = fake_which
    plat._NAMES = ('lark-cli.cmd', 'lark-cli')
    try:
        with Env(TCGEN_LARK_CLI=None):
            got = plat.lark_cli()
    finally:
        plat.shutil.which, plat._NAMES = orig_which, orig_names
    assert seen[0] == 'lark-cli.cmd', seen
    assert got.endswith('.cmd'), got
    return '.cmd 优先（试序 %s）' % (seen,)


def t_posix_never_tries_cmd():
    """Linux/macOS 上不去找 .cmd —— 那是 Windows 独有的包装器。"""
    seen = []

    def fake_which(name):
        seen.append(name)
        return '/usr/local/bin/lark-cli'

    orig_which, orig_names = plat.shutil.which, plat._NAMES
    plat.shutil.which = fake_which
    plat._NAMES = ('lark-cli',)
    try:
        with Env(TCGEN_LARK_CLI=None):
            got = plat.lark_cli()
    finally:
        plat.shutil.which, plat._NAMES = orig_which, orig_names
    assert not [n for n in seen if n.endswith('.cmd')], seen
    assert got == '/usr/local/bin/lark-cli', got
    return 'POSIX 只找裸名字'


def t_names_match_platform():
    """_NAMES 与当前平台一致：Windows 含 .cmd，POSIX 只有裸名字。"""
    if plat.IS_WINDOWS:
        assert 'lark-cli.cmd' in plat._NAMES, plat._NAMES
    else:
        assert plat._NAMES == ('lark-cli',), plat._NAMES
    return 'IS_WINDOWS=%s _NAMES=%s' % (plat.IS_WINDOWS, plat._NAMES)


# ---------------- 起不来时的报错要能照着修 ----------------

def t_exec_translates_missing_cli():
    """lark-cli 不存在时必须给出修法，不能只丢一个 FileNotFoundError。

    裸的 FileNotFoundError 只显示一个可执行文件名，看不出到底是「要装 lark-cli」
    还是「装了但不在 PATH，该设 TCGEN_LARK_CLI」——换机器后第一个撞上的就是这个坎。
    """
    try:
        feishu._exec(['lark-cli-does-not-exist-xyz', 'sheets', '+read'])
    except RuntimeError as e:
        msg = str(e)
    else:
        raise AssertionError('缺 CLI 却没报错')
    for need in ('npm i -g lark-cli', 'auth login', plat.LARK_CLI_ENV,
                 'Windows', 'Linux'):
        assert need in msg, '报错缺少「%s」: %s' % (need, msg)
    return '报错含安装/授权/环境变量三条修法'


def t_win_hint_is_single_line():
    """Windows 路径提示不能被反斜杠断成两行。

    实测：提示文案里写字面反斜杠时，`\\n` 被当成换行，路径断成两截，
    读者照着抄就抄错了。故用 os.sep 拼，并在此固化断言。
    """
    msg = plat.cli_missing_msg('lark-cli')
    win = [ln for ln in msg.split('\n') if 'Windows' in ln]
    assert len(win) == 1, win
    assert 'lark-cli.cmd' in win[0], win
    return '路径完整在一行'


# ---------------- 中文输出：两个平台都不能坏 ----------------

def t_stdout_kept_when_encodable():
    """能写中文的 stdout 一动不动 —— 守 Windows cp936 控制台不被弄成乱码。

    原来两个测试文件无条件 `TextIOWrapper(..., 'utf-8')`，在 cp936 控制台里
    输出的中文全是乱码。修 Linux 不能弄坏 Windows。
    """
    fake = FakeStdout('cp936')
    with Stdout(fake):
        got = plat.force_utf8_stdout()
        same = got is fake and sys.stdout is fake
    assert same, '可写中文的 stdout 被替换了'
    return 'cp936 stdout 保持原样'


def t_stdout_switched_when_ascii():
    """ASCII stdout 必须换掉 —— Ubuntu 在 LC_ALL=C 下 print 中文会 UnicodeEncodeError。"""
    fake = FakeStdout('ascii')
    with Stdout(fake):
        plat.force_utf8_stdout()
        swapped = sys.stdout is not fake
        sys.stdout.write('硬门禁: 全部通过')
        sys.stdout.flush()
        raw = fake.buffer.getvalue()
    assert swapped, 'ASCII stdout 没被换掉'
    assert '硬门禁: 全部通过'.encode('utf-8') in raw, repr(raw)
    return 'ASCII stdout 切 UTF-8，中文写得出'


def t_stdout_no_buffer_is_safe():
    """stdout 被换成 StringIO（无 .buffer）时不许崩 —— 测试框架常这么干。"""
    sio = io.StringIO()          # encoding 属性为 None
    with Stdout(sio):
        got = plat.force_utf8_stdout()
        ok = got is sio
    assert ok, '无 buffer 的 stdout 被动了'
    return '无 .buffer 的 stdout 安全跳过'


# ---------------- 反回退守卫：不许再写死绝对路径 ----------------

#: 盘符绝对路径（C:/... 或 C:\...）与写死的 Unix 用户目录
_ABS_RX = re.compile(r'^(?:[A-Za-z]:[/\\]|/(?:home|Users)/)')


def _code_strings(path):
    """产出文件里**代码位置**的字符串常量，跳过文档字符串。

    docstring 里举例说明 `C:/Users/...` 是合理的，抓它就是误报——
    而一个会误报的检查很快就没人看了（见 test_reuse.py 同款教训）。
    注释不进 AST，天然不会被扫到。
    """
    src = io.open(path, encoding='utf-8').read()
    tree = ast.parse(src)
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            body = getattr(node, 'body', None) or []
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docs.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docs:
            yield node.lineno, node.value


def t_no_hardcoded_abs_path():
    """tcgen/ 全包不得出现盘符绝对路径或写死的用户目录（那次事故的守卫）。"""
    tcgen = os.path.join(HERE, 'tcgen')
    mods = sorted(f for f in os.listdir(tcgen) if f.endswith('.py'))
    bad = []
    for fn in mods:
        for lineno, val in _code_strings(os.path.join(tcgen, fn)):
            if _ABS_RX.match(val):
                bad.append('%s:%d %r' % (fn, lineno, val[:60]))
    assert not bad, '写死了绝对路径: %s' % bad
    return 'tcgen/ 无写死绝对路径（%d 个模块）' % len(mods)


def t_guard_catches_injected_abs_path():
    """守卫自身有效性：注入一条绝对路径必须被抓到（故障注入，不落盘 tcgen/）。"""
    import tempfile
    src = ("# -*- coding: utf-8 -*-\n"
           '"""docstring 里的 C:/Users/foo/lark-cli.cmd 不算违例。"""\n'
           "CLI = 'C:/Users/someone/AppData/Roaming/npm/lark-cli.cmd'\n")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'inject.py')
        io.open(p, 'w', encoding='utf-8').write(src)
        hits = [v for _, v in _code_strings(p) if _ABS_RX.match(v)]
    assert len(hits) == 1, '注入未被抓到或误抓 docstring: %s' % (hits,)
    return '注入被抓到 1 条，docstring 举例未误报'


def t_default_lark_cli_not_absolute_literal():
    """DEFAULT_LARK_CLI 必须运行期求值，不能是源码里的字面量常量。"""
    src = io.open(os.path.join(HERE, 'tcgen', 'feishu.py'), encoding='utf-8').read()
    line = [ln for ln in src.split('\n') if ln.startswith('DEFAULT_LARK_CLI')]
    assert len(line) == 1, line
    assert 'plat.lark_cli()' in line[0], line[0]
    return line[0].strip()


def main():
    ts = [t_env_override_wins, t_env_expands_user, t_falls_back_to_bare_name,
          t_windows_prefers_cmd, t_posix_never_tries_cmd, t_names_match_platform,
          t_exec_translates_missing_cli, t_win_hint_is_single_line,
          t_stdout_kept_when_encodable, t_stdout_switched_when_ascii,
          t_stdout_no_buffer_is_safe,
          t_no_hardcoded_abs_path, t_guard_catches_injected_abs_path,
          t_default_lark_cli_not_absolute_literal]
    bad = 0
    for t in ts:
        try:
            print('  PASS  %-34s %s' % (t.__name__, t()))
        except AssertionError as e:
            bad += 1
            print('  FAIL  %-34s %s' % (t.__name__, e))
    print('跨平台回归: %d/%d 通过' % (len(ts) - bad, len(ts)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
