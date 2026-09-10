# -*- coding: utf-8 -*-
"""tcgen.feishu 回读比对（门禁18 工具）的回归测试。

管道改动后跑：python test_feishu_diff.py

不联网：把 feishu.read_sheet / feishu._run 换成假数据，只验比对逻辑本身。
存在理由：这些函数只在「改完数据后同步飞书」时才被调用，平时跑 build.py 碰不到；
而它们报出的单元格地址是人照着去改的依据，地址错一位就会改错格子。
图表部分（diff_charts）守的是另一类事故：数据逐格一致、图表对象也在，
但报告增删行后图表引用没跟着位移，饼图全渲染成空白。
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcgen import plat  # noqa: E402

plat.force_utf8_stdout()   # Ubuntu 在 LC_ALL=C 下 print 中文会崩
from tcgen import feishu  # noqa: E402


class FakeOnline(object):
    """临时把 read_sheet 替换成固定返回值，避免测试联网。"""

    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        self.orig = feishu.read_sheet
        feishu.read_sheet = lambda *a, **kw: [list(r) for r in self.rows]
        return self

    def __exit__(self, *exc):
        feishu.read_sheet = self.orig


def write_csv(d, name, rows):
    p = os.path.join(d, feishu.safe_name(name) + '.csv')
    with io.open(p, 'w', encoding='utf-8', newline='') as f:
        for r in rows:
            f.write(','.join('"%s"' % str(x).replace('"', '""') for x in r) + '\n')
    return p


def t_col_is_one_based():
    """列号必须 1-based，能直接喂给 col_letter()。

    第 9 列（下标 8）不一致时，地址必须报成 I 而不是 H。传 0-based 会让所有
    地址整体错一位——实测把 `I9`(备注列) 报成了 `H9`(测试结果列)，照着去改就改错格子。
    """
    hdr = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']
    online = [hdr, ['x'] * 8 + ['线上值']]
    local = [hdr, ['x'] * 8 + ['本地值']]
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        write_csv(d, '表', local)
        with FakeOnline(online):
            res = feishu.diff_sheets('tok', [('sid', '表')], d)
    (name, diffs) = res[0]
    assert len(diffs) == 1, '应恰好 1 处差异: %s' % diffs
    row, col, fv, lv = diffs[0]
    assert row == 2, '行号应 1-based=2，实际 %s' % row
    assert col == 9, '列号应 1-based=9，实际 %s（传了 0-based?）' % col
    addr = '%s%d' % (feishu.col_letter(col), row)
    assert addr == 'I2', '地址应 I2，实际 %s' % addr
    assert (fv, lv) == ('线上值', '本地值'), '线上/本地值顺序颠倒: %s' % ((fv, lv),)
    return '地址 I2 正确，线上/本地未颠倒'


def t_numeric_normalized():
    """飞书把整数列存成 float，147 vs 147.0 不得算差异。"""
    with FakeOnline([['计数'], [147.0]]):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            write_csv(d, '表', [['计数'], ['147']])
            res = feishu.diff_sheets('tok', [('sid', '表')], d)
    assert not res[0][1], '147.0 与 "147" 被误判成差异: %s' % res[0][1]
    return '整数 float 归一化生效'


def t_trailing_blanks_ignored():
    """行尾空列与表尾空行是飞书侧的空白区，不算差异。"""
    with FakeOnline([['A', 'B'], ['1', '2'], ['', ''], ['', '']]):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            write_csv(d, '表', [['A', 'B', ''], ['1', '2']])
            res = feishu.diff_sheets('tok', [('sid', '表')], d)
    assert not res[0][1], '空白区被误判成差异: %s' % res[0][1]
    return '尾部空列/空行被忽略'


def t_real_diff_still_caught():
    """归一化不能宽到放过真差异。"""
    with FakeOnline([['A'], ['异常提示扩展']]):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            write_csv(d, '表', [['A'], ['异常安慰扩展']])
            res = feishu.diff_sheets('tok', [('sid', '表')], d)
    diffs = res[0][1]
    assert len(diffs) == 1 and diffs[0][2] == '异常提示扩展', '真差异漏检: %s' % diffs
    return '真差异仍被抓到'


def t_missing_local_csv():
    """本地缺 CSV 要显式报出来，不能静默当成一致。"""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        with FakeOnline([['A'], ['1']]):
            res = feishu.diff_sheets('tok', [('sid', '不存在的表')], d)
    assert res[0][1], '缺 CSV 却报一致'
    return '缺本地 CSV 会报出'


class FakeChartList(object):
    """桩掉 _run + read_sheet，让 diff_charts 离线跑。

    `numbers` 控制线上 H 列数值格是数字还是文本：diff_charts 用
    read_sheet(raw=True) 判类型，桩必须同时提供，否则测不到「存成文本」这一路。
    """

    def __init__(self, ranges, grid=None, numbers=True):
        self.text = json.dumps(
            {'data': {'sheets': [{'charts': [
                {'details': {'snapshot': {'series': [
                    {'range': "'质量审计报告'!%s" % r}]}}}
                for r in ranges]}]}}, ensure_ascii=False)
        self.grid = grid
        self.numbers = numbers

    def _fake_read(self, token, sheet_id, last_col='P', last_row=400,
                   lark_cli=None, raw=False):
        rows = []
        for r in (self.grid or []):
            row = list(r)
            while len(row) < 8:
                row.append('')
            v = row[7]
            if v != '' and raw:
                row[7] = int(v) if self.numbers else str(v)
            rows.append(row)
        return rows

    def __enter__(self):
        self.orig_run = feishu._run
        self.orig_read = feishu.read_sheet
        feishu._run = lambda *a, **kw: self.text
        feishu.read_sheet = self._fake_read
        return self

    def __exit__(self, *exc):
        feishu._run = self.orig_run
        feishu.read_sheet = self.orig_read


# 辅助块故意放在第 20 行以后：真实报告里辅助块在 G63 往后，位移 5 行仍是正数行号。
# 若把块放在前几行，-5 会得到负数行号被正则滤掉，extra 少报一个，测出来的
# 事故形态就和真实的不一样了。
CHART_CSV = [
    ['报告说明'],
] + [['', '', '', '', '', '', '', ''] for _ in range(18)] + [
    ['分区', '门禁项', '结论', '说明', '', '', '', ''],
    ['硬门禁', '未覆盖REQ=0', '通过', '-', '', '', '', ''],
    ['', '', '', '', '', '', '覆盖率(已覆盖/未覆盖/N-A)', ''],
    ['', '', '', '', '', '', '已覆盖', '60'],
    ['', '', '', '', '', '', '未覆盖', '3'],
    ['', '', '', '', '', '', 'N/A', '2'],
    ['', '', '', '', '', '', '可执行性(Ready/Blocked)', ''],
    ['', '', '', '', '', '', 'Ready', '131'],
    ['', '', '', '', '', '', 'Blocked', '16'],
]


def t_charts_ok_when_aligned():
    """引用与 CSV 辅助块对齐时，diff_charts 双空。"""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = write_csv(d, '质量审计报告', CHART_CSV)
        blocks = feishu.parse_chart_blocks(p)
        rngs = ['G%d:H%d' % (b['trow'], b['last']) for b in blocks]
        assert len(rngs) == 2, '应解析出 2 个辅助块，实际 %s' % rngs
        with FakeChartList(rngs, grid=CHART_CSV, numbers=True):
            miss, extra, text = feishu.diff_charts('tok', 'sid', p)
    assert not miss and not extra, '对齐却报差异: miss=%s extra=%s' % (miss, extra)
    assert not text, '数值本是数字却报成文本: %s' % text
    return '对齐且数值为数字时三空（%s）' % ','.join(rngs)


def t_charts_catch_row_shift():
    """辅助块位移后图表引用没跟着动，必须报出来。

    这是真实事故：报告插入 5 行 → G/H 辅助块整体下移 5 行 → 图表引用仍指旧地址 →
    6 个饼图全渲染成空白。而此时**数据逐格比对完全一致、图表对象也都在**，
    只查数据一致性根本发现不了。
    """
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = write_csv(d, '质量审计报告', CHART_CSV)
        blocks = feishu.parse_chart_blocks(p)
        stale = ['G%d:H%d' % (b['trow'] - 5, b['last'] - 5) for b in blocks]
        with FakeChartList(stale, grid=CHART_CSV, numbers=True):
            miss, extra, _ = feishu.diff_charts('tok', 'sid', p)
    assert miss, '位移未被检出（miss 为空）'
    assert extra, '过期引用未被检出（extra 为空）'
    assert len(miss) == len(stale), '应报出全部 %d 个块，实际 %s' % (len(stale), miss)
    return '位移 -5 行被检出：miss=%s extra=%s' % (miss, extra)


def t_charts_catch_text_numbers():
    """数值格存成文本必须报出来——引用地址全对，饼图照样空白。

    这是第二起真实事故：整表推送时每格都 `{'value': str(...)}`，H 列的 `67` 成了
    `'67'`。此时引用地址完全正确、图表对象一个不少、辅助数据「看起来」也对，
    但饼图取不到可绘制的数值，6 图全空。

    关键：`diff_sheets` 查不出这一条——`_norm_cell` 为消除「147 vs 147.0」的
    假差异，会把 `67` 和 `'67'` 都归一化成 `"67"`。两道检查同时失效，正是这次
    「引用已修好、饼图仍无数据」的原因。
    """
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = write_csv(d, '质量审计报告', CHART_CSV)
        blocks = feishu.parse_chart_blocks(p)
        rngs = ['G%d:H%d' % (b['trow'], b['last']) for b in blocks]
        with FakeChartList(rngs, grid=CHART_CSV, numbers=False):
            miss, extra, text = feishu.diff_charts('tok', 'sid', p)
    assert not miss and not extra, '引用本应对齐: miss=%s extra=%s' % (miss, extra)
    assert text, '数值格存成文本却没报出来（这正是饼图空白的原因）'
    n = sum(b['last'] - b['trow'] for b in blocks)
    assert len(text) == n, '应报出全部 %d 个数值格，实际 %d 个: %s' % (n, len(text), text)
    return '文本数值格被检出 %d 个（引用仍对齐）' % len(text)


# 第二个块四个扇区全为 0：真实场景是「四类质量缺陷均为 0」的零缺陷情形。
ZERO_CSV = CHART_CSV[:-3] + [
    ['', '', '', '', '', '', '质量缺陷类型', ''],
    ['', '', '', '', '', '', '坍缩', '0'],
    ['', '', '', '', '', '', '深度缺口', '0'],
    ['', '', '', '', '', '', '反模式', '0'],
    ['', '', '', '', '', '', '追溯缺口', '0'],
]


def t_tile_cells_parses_addresses():
    """tile 地址要解成 1-based (行, 列)，与 diff_sheets 的坐标同一套。

    P16 必须是 (16,16) 而非 (16,15)：列号错一位，屏蔽的就是隔壁格子——
    既漏掉了该屏蔽的假差异，又把一个真数据格给盖住了。
    """
    cells = feishu.tile_cells(('J1', 'P16'))
    assert cells == {(1, 10), (16, 16)}, '解析错误: %s' % sorted(cells)
    assert feishu.tile_cells() == feishu.tile_cells(feishu.CHART_TILES), \
        '默认值应等于 CHART_TILES'
    return 'J1->(1,10) P16->(16,16)，默认取 CHART_TILES'


def t_tile_note_not_reported_as_diff():
    """渲染层 tile 格位不参与数据比对，但同行其他列的真差异仍要抓到。

    实测事故：零数据块的结论文本写在线上 P16，本地 CSV 只有 A-H 八列，
    diff_sheets 于是报出一条**永远修不掉**的差异 `(16,16)`。而一个会误报的
    检查，很快就没人看了——这正是屏蔽它的理由。

    但屏蔽必须精确：只放过 tile 那一格，同一行第 3 列的真差异照样得报出来，
    否则就从「误报」滑到了更糟的「漏报」。
    """
    hdr = ['h%d' % i for i in range(1, 9)]
    local = [hdr] + [['x'] * 8 for _ in range(15)]
    online = [list(r) for r in local]
    online[15] = ['x'] * 8 + [''] * 7 + ['质量缺陷类型：坍缩 均为 0']   # P16 有 note
    online[15][2] = '被人手工改过'                                      # C16 真差异

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        write_csv(d, '质量审计报告', local)
        with FakeOnline(online):
            res = feishu.diff_sheets('tok', [('sid', '质量审计报告')], d,
                                     tile_sheet='质量审计报告')
        with FakeOnline(online):
            res_off = feishu.diff_sheets('tok', [('sid', '质量审计报告')], d)

    diffs = res[0][1]
    cols = sorted(c for _, c, _, _ in diffs)
    assert 16 not in cols, 'P16 的 note 仍被报成差异: %s' % diffs
    assert cols == [3], '同行真差异应只剩 C16，实际列 %s' % cols

    off = sorted(c for _, c, _, _ in res_off[0][1])
    assert 16 in off, '不传 tile_sheet 时不该屏蔽（否则是无条件漏报）: %s' % off
    return 'note 被放过、同行真差异仍报出；未指定表名时不屏蔽'


def t_total_reflects_sum():
    """parse_chart_blocks 要给出 total/labels —— A 方案判「画不画图」的依据。"""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        blocks = feishu.parse_chart_blocks(write_csv(d, '质量审计报告', ZERO_CSV))
    assert len(blocks) == 2, '应解析出 2 个块，实际 %d' % len(blocks)
    nz, zero = blocks[0], blocks[-1]
    assert nz['total'] > 0, '非零块 total 却是 %r' % nz['total']
    assert zero['total'] == 0, '全 0 块 total 却是 %r' % zero['total']
    assert zero['labels'] == ['坍缩', '深度缺口', '反模式', '追溯缺口'], \
        'labels 不对: %s' % zero['labels']
    return 'total 正确（非零=%g，零缺陷块=0，labels 齐全）' % nz['total']


def t_zero_block_not_reported_missing():
    """合计为 0 的块按 A 方案本就不画饼图，不能报成 missing 假差异。

    A 方案：零数据不画图、改写结论文本。若 diff_charts 仍把该块算进 exp，
    每次 diff 都会报一条永远修不掉的 missing——检查一旦会误报，人就会开始忽略它。
    """
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = write_csv(d, '质量审计报告', ZERO_CSV)
        blocks = feishu.parse_chart_blocks(p)
        # 线上只为非零块建图，零块没有图表 —— 这是 A 方案下的正确状态
        rngs = ['G%d:H%d' % (b['trow'], b['last'])
                for b in blocks if b['total']]
        with FakeChartList(rngs, grid=ZERO_CSV, numbers=True):
            miss, extra, text = feishu.diff_charts('tok', 'sid', p)
    assert not miss, '零数据块被误报为 missing: %s' % miss
    assert not extra and not text, 'miss 之外还有误报: extra=%s text=%s' % (extra, text)
    return '零数据块未被误报（线上仅 %d 图）' % len(rngs)


def t_stale_chart_on_zeroed_block_caught():
    """某块从非零变成 0 后，线上遗留的旧图必须报进 extra。

    这是零数据块唯一需要动作的场景：图还在、但它现在指着一片 0，
    渲染出来就是那个「无法自证」的空白饼图，必须重跑 charts 换成结论文本。
    """
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = write_csv(d, '质量审计报告', ZERO_CSV)
        blocks = feishu.parse_chart_blocks(p)
        # 线上给「所有」块都建了图（包括后来归零的那个）—— 变更前的旧状态
        rngs = ['G%d:H%d' % (b['trow'], b['last']) for b in blocks]
        stale = 'G%d:H%d' % (blocks[-1]['trow'], blocks[-1]['last'])
        with FakeChartList(rngs, grid=ZERO_CSV, numbers=True):
            miss, extra, _ = feishu.diff_charts('tok', 'sid', p)
    assert stale in extra, '归零块上的旧图未报进 extra: extra=%s' % extra
    assert not miss, '不该有 missing: %s' % miss
    return '归零块的遗留旧图被检出（%s）' % stale


def main():
    ts = [t_col_is_one_based, t_numeric_normalized, t_trailing_blanks_ignored,
          t_real_diff_still_caught, t_missing_local_csv,
          t_charts_ok_when_aligned, t_charts_catch_row_shift,
          t_charts_catch_text_numbers, t_tile_cells_parses_addresses,
          t_tile_note_not_reported_as_diff, t_total_reflects_sum,
          t_zero_block_not_reported_missing,
          t_stale_chart_on_zeroed_block_caught]
    bad = 0
    for t in ts:
        try:
            print('  PASS  %-28s %s' % (t.__name__, t()))
        except AssertionError as e:
            bad += 1
            print('  FAIL  %-28s %s' % (t.__name__, e))
    print('飞书比对回归: %d/%d 通过' % (len(ts) - bad, len(ts)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
