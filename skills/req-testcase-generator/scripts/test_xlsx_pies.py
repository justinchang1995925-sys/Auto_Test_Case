# -*- coding: utf-8 -*-
"""审计报告饼图生成回归 —— 守 A 方案在**生成侧**（xlsx）的落地。

存在理由：A 方案（合计为 0 不画饼图，改由渲染层写结论文本）一开始只改在某个项目的
本地 build_xlsx.py 里，`tcgen/xlsx.py:add_pies` 这份**新项目实际调用的共享实现**
没跟着改——新项目跑起来照旧画出那个无法自证的空白饼图。这份测试就是那次漏改的守卫。

不依赖飞书，纯 openpyxl 内存构图。
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcgen import plat                            # noqa: E402

# 中文输出：只在当前 stdout 编码写不出中文时才切 UTF-8。
# 原来这里无条件包一层 UTF-8，在 Windows 的 cp936 控制台里反而输出乱码——
# 修一个平台不能弄坏另一个。
plat.force_utf8_stdout()

from openpyxl import Workbook                       # noqa: E402

from tcgen import xlsx as X                         # noqa: E402

#: gates() 与 add_pies() 需要的全部键，默认「全绿」——各测试只改自己关心的那几个。
CLEAN = dict(
    testable=['R1', 'R2', 'R3'], uncovered=[], na=['R9'],
    func_reqs=['R1', 'R2'], depth_bad=[],
    ready=10, blk=0, draft=0,
    collapse_tp=[], collapse_req=[], tp_no_tc=[], step_bad=[],
    pri={'P0': 1, 'P1': 2, 'P2': 3, 'P3': 4},
    spec_ok=True, dim_bad=[], title_meta_bad=[], cover_bad=[],
    req_struct_bad=0, tp_degenerate=[], tp_all=['TP-F-001'], tp_named_n=1,
    fno_scope=[], fno_no_case=[],
    fs_depth_bad=[], fs_src_bad=[], fs_elem_bad=[],
    ex_no_body=[], ex_cell_unrated=[], ex_no_basis=[], ex_must_gap=[],
    ex_ref_bad=[], pri_incons=[],
    res_ok=True, res_bad=[], res={}, res_exempt=None,
)


def t_clean_covers_all_gate_keys():
    """CLEAN 必须覆盖 gates() 所需的全部键。

    这份字面量是与 compute() 的脱钩点：skill 每加一条门禁，gates() 就多读一个键，
    而这里不会自动跟上——上一次加门禁 19 就是直接 KeyError 才发现的（踩过）。
    有了这条断言，缺键会报出「缺哪个键」而不是在别的用例里炸出 KeyError。
    """
    from tcgen import audit as _a

    class _Probe(dict):
        """记录被读过的键；缺键返回安全值而不抛，以便一次收集全部缺失。"""

        def __init__(self, base):
            dict.__init__(self, base)
            self.missing = []

        def __getitem__(self, k):
            if k not in self:
                self.missing.append(k)
                return []          # 空列表对 gates() 的 not/== 判断都安全
            return dict.__getitem__(self, k)

    p = _Probe(CLEAN)
    _a.gates(p)
    assert not p.missing, 'CLEAN 缺 gates() 所需键: %s' % ','.join(
        sorted(set(p.missing)))
    return 'gates() 所需 %d 个键齐全' % len(_a.gates(dict(CLEAN)))

DEFECT_TITLE = '质量缺陷类型'


def _run(**over):
    """构图，返回 (worksheet, 图表标题列表)。"""
    a = dict(CLEAN)
    a.update(over)
    wb = Workbook()
    ws = wb.active
    ws.cell(1, 1, '占位')            # add_pies 用 ws.max_row 定位，需非空表
    X.add_pies(ws, a)
    titles = []
    for ch in ws._charts:
        try:
            titles.append(ch.title.tx.rich.p[0].r[0].t)
        except Exception:
            titles.append('?')
    return ws, titles


def t_zero_block_skipped():
    """四类质量缺陷全为 0 时，不画那个饼图（其余照画）。"""
    ws, titles = _run()
    assert DEFECT_TITLE not in titles, '零缺陷仍画了饼图: %s' % titles
    assert len(titles) == 5, '应剩 5 个饼图，实际 %d: %s' % (len(titles), titles)
    return '零缺陷块被跳过，其余 5 图照画'


def t_nonzero_block_still_drawn():
    """只要有一类缺陷非 0，该饼图必须照画——不能把「跳过」做成无条件。"""
    ws, titles = _run(step_bad=['TC-1'])
    assert DEFECT_TITLE in titles, '有缺陷却没画饼图: %s' % titles
    assert len(titles) == 6, '应有 6 个饼图，实际 %d: %s' % (len(titles), titles)
    return '有缺陷时照画（共 6 图）'


def t_aux_block_still_written():
    """跳过画图但**辅助数据块照写**——读者靠 G/H 列那几个 0 看懂零缺陷。

    若连辅助块一起省掉，页面上就只剩一片空白，比空白饼图更难懂。
    """
    ws, _ = _run()
    found = None
    for r in range(1, ws.max_row + 1):
        if ws.cell(r, 7).value == DEFECT_TITLE:
            found = r
            break
    assert found, '辅助块标题行不见了'
    labels = [ws.cell(found + i, 7).value for i in range(1, 5)]
    vals = [ws.cell(found + i, 8).value for i in range(1, 5)]
    assert labels == ['坍缩', '深度缺口', '反模式', '追溯缺口'], '标签不对: %s' % labels
    assert vals == [0, 0, 0, 0], '数值不对: %s' % vals
    return '辅助块仍在（G%d 起，四个 0 逐行列出）' % found


def t_no_note_text_in_cells():
    """生成侧**不许**往单元格写结论文本——否则会流进 CSV 造成永久假差异。

    线上那行文本由 feishu.rebuild_charts 写在渲染层 tile（不来自 CSV）。
    xlsx 的格子会随 export_csv 导出，两边地址不同，写了 diff 就永远报差异。
    实测踩过：note 写在线上 P16，本地 CSV 只有 A-H 八列，diff 每次报 (16,16)。
    """
    ws, _ = _run()
    dirty = []
    for r in range(1, ws.max_row + 1):
        for c in range(9, 17):                      # I..P
            v = ws.cell(r, c).value
            if v not in (None, ''):
                dirty.append((r, c, v))
    assert not dirty, 'I-P 列被写入了内容（会流进 CSV）: %s' % dirty[:3]
    return 'I-P 列均为空，CSV 宽度不受影响'


def t_csv_width_unchanged():
    """整表最大列数仍是 8（A-H）——A 方案不能让 CSV 变宽。"""
    ws, _ = _run()
    assert ws.max_column <= 8, 'max_column=%d，CSV 会变宽' % ws.max_column
    return 'max_column=%d（仍为 A-H）' % ws.max_column


def main():
    # 自动收集 t_* 函数，**不手写清单**：手写的那份会在新增测试后悄悄落后——
    # 加了测试却忘记登记，它就永远不跑，看起来还是「全绿」（踩过）。
    g = globals()
    ts = [g[k] for k in sorted(g) if k.startswith('t_') and callable(g[k])]
    bad = 0
    for t in ts:
        # 捕 Exception 而非只捕 AssertionError：CLEAN 缺键时 add_pies 抛的是
        # KeyError，只捕断言会让它逃出 main、脚本崩溃且**退出码仍为 0**，
        # CI 里看起来是通过的（踩过，靠故障注入才发现）。
        try:
            print('  PASS  %-32s %s' % (t.__name__, t()))
        except Exception as e:                       # noqa: BLE001
            bad += 1
            print('  FAIL  %-32s %s: %s' % (t.__name__, type(e).__name__, e))
    print('饼图生成回归: %d/%d 通过' % (len(ts) - bad, len(ts)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
