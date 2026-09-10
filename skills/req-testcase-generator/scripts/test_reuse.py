# -*- coding: utf-8 -*-
"""复用检查回归 —— 守「不许抄一份共享实现」这条门禁本身。

这份测试的重点**不是**能不能抓到违例，而是**会不会误报**。
第一版复用检查用文本 grep，在真实项目上报了 13 处，其中 12 处是误报：
  - `"P1"` 是优先级值（P0..P3），被当成饼图格位 P1；
  - `TITLE_META_RX` 出现在项目文件里，恰恰是正确的 import 复用；
  - `chart-create` 命中的是薄封装自己的文档字符串。
会误报的检查很快就没人看了——所以下面每条「不该报」的用例，和「该报」的一样重要。
"""
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcgen import plat                            # noqa: E402

# 中文输出：只在当前 stdout 编码写不出中文时才切 UTF-8。
# 原来这里无条件包一层 UTF-8，在 Windows 的 cp936 控制台里反而输出乱码——
# 修一个平台不能弄坏另一个。
plat.force_utf8_stdout()

from tcgen import reuse                              # noqa: E402


def scan(src, fn='mod.py'):
    with tempfile.TemporaryDirectory() as d:
        io.open(os.path.join(d, fn), 'w', encoding='utf-8').write(src)
        return reuse.scan_duplicates(d)


# ---------------- 不该报（误报守卫） ----------------

def t_priority_p1_not_tile():
    """优先级 P0..P3 不是饼图格位——格位行号是两位（J16/P31）。"""
    src = ('PRI = ("P0", "P1", "P2", "P3")\n'
           'def f(c):\n    return c["pri"] == "P1"\n')
    assert not scan(src), '优先级值被误判成格位: %s' % scan(src)
    return '优先级 P0-P3 不误报'


def t_import_is_not_copy():
    """import 共享常量是**正确做法**，不能判成抄了一份。"""
    src = ('from tcgen.audit import TITLE_META_RX, TTYPE_COVER\n'
           'def f(t):\n    return TITLE_META_RX.search(t) and TTYPE_COVER\n')
    assert not scan(src), 'import 复用被误报: %s' % scan(src)
    return 'import 复用不误报'


def t_docstring_mention_not_copy():
    """文档里写「不要自己拼 chart-create」不是违例，是说明。"""
    src = ('"""薄封装：不要自己拼 chart-create，走 rebuild_charts。"""\n'
           'from tcgen import feishu\n'
           'feishu.rebuild_charts("t", "s", "n", ".")\n')
    assert not scan(src), '文档字符串被误报: %s' % scan(src)
    return '文档提及不误报'


def t_using_shared_tiles_ok():
    """引用 feishu.CHART_TILES 是正解，不该报。"""
    src = ('from tcgen import feishu\n'
           'for t in feishu.CHART_TILES:\n    print(t)\n')
    assert not scan(src), '引用共享格位被误报: %s' % scan(src)
    return '引用 CHART_TILES 不误报'


# ---------------- 该报（漏报守卫） ----------------

def t_own_piechart_caught():
    """自己调 PieChart() 建图 = 抄了 add_pies —— 今天空白饼图的根因之一。"""
    src = ('from openpyxl.chart import PieChart\n'
           'ch = PieChart()\n')
    got = scan(src)
    assert got and 'PieChart' in got[0][1], '未抓到自建饼图: %s' % got
    return '自建 PieChart 被抓到'


def t_own_chart_create_caught():
    """自己拼 chart-create CLI = 抄了 rebuild_charts。"""
    src = ('cmd = ["lark-cli", "sheets", "+chart-create", "--range", "G1:H4"]\n')
    got = scan(src)
    assert got and 'chart-create' in got[0][1], '未抓到自拼 CLI: %s' % got
    return '自拼 chart-create 被抓到'


def t_copied_const_caught():
    """自己**赋值定义**共享常量 = 抄了一份，skill 改了它不会跟着改。"""
    src = ('import re\n'
           'TITLE_META_RX = re.compile("由.*验证")\n')
    got = scan(src)
    assert got and 'TITLE_META_RX' in got[0][1], '未抓到抄常量: %s' % got
    return '抄 TITLE_META_RX 被抓到'


def t_hardcoded_tiles_caught():
    """写死格位表 = 抄了 CHART_TILES，位置一改两边就错开。"""
    src = ("TILES = ('J1', 'P16', 'J31', 'P31')\n")
    got = scan(src)
    assert got and '格位' in got[0][1], '未抓到写死格位表: %s' % got
    return '写死格位表被抓到'


# ---------------- 元守卫 ----------------

def t_template_is_clean():
    """模板目录必须零违例——否则新项目一上手就见红，检查立刻失去权威。"""
    here = os.path.dirname(os.path.abspath(__file__))
    got = reuse.scan_duplicates(os.path.join(here, 'project_template'))
    assert not got, '模板自身违例: %s' % got
    return '模板目录零违例'


def main():
    ts = [t_priority_p1_not_tile, t_import_is_not_copy,
          t_docstring_mention_not_copy, t_using_shared_tiles_ok,
          t_own_piechart_caught, t_own_chart_create_caught,
          t_copied_const_caught, t_hardcoded_tiles_caught,
          t_template_is_clean]
    bad = 0
    for t in ts:
        try:
            print('  PASS  %-30s %s' % (t.__name__, t()))
        except AssertionError as e:
            bad += 1
            print('  FAIL  %-30s %s' % (t.__name__, e))
    print('复用检查回归: %d/%d 通过' % (len(ts) - bad, len(ts)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
