# -*- coding: utf-8 -*-
"""需求原子化清单的可选「需求编号」列回归 —— 守 build_req 的位置契约。

存在理由：需求文档自带编号体系时（产测工具类需求常见 F02/F03…），清单前面加一列
需求编号能让读者一眼看到「F17 拆出了哪几条 REQ」，与按需求编号组织的思维导图对上。
但这个字段**只能挂在数据层元组末尾（索引 8）**：`tcgen.audit` 全部按固定位置读
REQ 字段（r[0] ID / r[2] 来源文档 / r[3] 章节 / r[4] 类型 / r[5] 可测性 /
r[6] 覆盖状态 / r[7] 备注），在前面插一列会让所有索引整体错位、门禁集体误判——
而且误判方式很隐蔽：类型列读到可测性、可测性读到覆盖状态，门禁照样「跑通」只是结论全错。
渲染时才把它移到首列。这份测试守的就是「渲染位置」与「数据位置」不得混为一谈。

不依赖飞书，纯 openpyxl 内存构表。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcgen import plat                            # noqa: E402

plat.force_utf8_stdout()

from openpyxl import Workbook                       # noqa: E402

from tcgen import audit as A                        # noqa: E402
from tcgen import xlsx as X                         # noqa: E402

#: 8 字段的传统 REQ 行（无需求编号）
ROW8 = ('REQ-001', '描述一', '需求文档V1', '1. Feature 大表 F17',
        '功能', '可测', '待覆盖', '备注一')
#: 9 字段：末尾多一个需求编号
ROW9 = ROW8 + ('F17',)

LINKS = ['说明横幅', 'http://example.com/a']


def _build(req_src):
    """渲染需求原子化清单，返回 (表头列表, 数据行列表)。"""
    wb = Workbook()
    ws = wb.active
    X.build_req(ws, req_src, LINKS, cases=[], spec_reqs=[])
    header = [c.value for c in ws[2]]
    rows = [[c.value for c in r]
            for r in ws.iter_rows(min_row=3, max_row=ws.max_row)]
    return header, rows


def t_no_fno_header_unchanged():
    """没有任何行带需求编号时，表头与列数必须与改动前完全一致。

    普通产品需求（无 F 编号体系）走的就是这条路径；多出一个空列会让所有
    既有项目的 diff 报满屏差异、飞书那侧还要重新合并单元格。
    """
    header, rows = _build([ROW8])
    assert header == list(X.REQ_HEADERS), \
        '无需求编号时表头被改动: %s' % header
    assert '需求编号' not in header, '无编号却插了需求编号列'
    assert len(rows[0]) == len(X.REQ_HEADERS), \
        '数据列数与表头不符: %d vs %d' % (len(rows[0]), len(X.REQ_HEADERS))
    assert rows[0][0] == 'REQ-001', '首列应仍是 REQ-ID: %s' % rows[0][0]
    return '无编号时表头/列数不变（%d 列）' % len(header)


def t_fno_rendered_as_first_column():
    """有行带需求编号时，它渲染成第一列，REQ-ID 顺移到第二列。"""
    header, rows = _build([ROW9])
    assert header[0] == '需求编号', '需求编号未渲染成首列: %s' % header
    assert header[1] == 'REQ-ID', 'REQ-ID 未顺移到第二列: %s' % header
    assert header[1:] == list(X.REQ_HEADERS), \
        '除首列外表头应与原样一致: %s' % header
    assert rows[0][0] == 'F17', '首列值应为需求编号: %s' % rows[0][0]
    assert rows[0][1] == 'REQ-001', '第二列应为 REQ-ID: %s' % rows[0][1]
    return '需求编号渲染为首列，REQ-ID 顺移（共 %d 列）' % len(header)


def t_partial_fno_fills_blank():
    """只有部分行带编号时，整表仍加这一列，缺的留空而不是整列消失。

    混合状态出现在「补编号补到一半」的中间态。若按「全有才加列」处理，
    已补的那部分编号会被静默丢弃——读者看不出是没编号还是列没渲染。
    """
    header, rows = _build([ROW9, ROW8])
    assert header[0] == '需求编号', '混合时未加需求编号列: %s' % header
    assert rows[0][0] == 'F17', '带编号的行未渲染编号: %s' % rows[0][0]
    assert rows[1][0] in ('', None), \
        '无编号的行首列应留空，实际 %r' % rows[1][0]
    assert rows[1][1] == 'REQ-001', '无编号行的 REQ-ID 未对齐到第二列'
    return '部分带编号时整表加列、缺者留空'


def t_fno_lives_at_index_8():
    """契约核心：需求编号必须在索引 8，前 8 位语义不得移动。

    这是本文件存在的主要理由。audit 按固定位置读 REQ 字段，把编号插到前面
    会让 r[4] 类型读到可测性、r[5] 可测性读到覆盖状态——门禁照样跑完，
    只是结论全错，且不报任何异常。
    """
    assert ROW9[8] == 'F17', '测试数据自身的编号不在索引 8'
    # 前 8 位与 8 字段行逐位相同：加编号不得挪动任何既有字段
    assert ROW9[:8] == ROW8, '加编号后前 8 位发生了位移'

    # 用 audit 实际读一遍：9 字段行与 8 字段行的门禁结论必须一致
    a8 = A.compute([], [ROW8], ex=None)
    a9 = A.compute([], [ROW9], ex=None)
    for k in ('testable', 'uncovered', 'na', 'func_reqs', 'req_struct_bad'):
        assert a8[k] == a9[k], \
            'audit 的 %s 因加编号而改变: %r -> %r（字段错位?）' % (k, a8[k], a9[k])
    return 'audit 对 8/9 字段行结论一致，前 8 位未错位'


def t_wrong_position_would_break_audit():
    """反证：把编号插到**首位**会让 audit 读错字段。

    不断言具体错法，只断言「结论必然改变」——证明位置契约不是可选风格，
    而是错了就会静默出错的硬约束。若哪天此断言失败（audit 改成按名取字段），
    说明契约已解除，本测试与 build_req 的注释都该一起更新。
    """
    wrong = ('F17',) + ROW8      # 编号插到首位：所有索引整体后移一位
    ok = A.compute([], [ROW8], ex=None)
    bad = A.compute([], [wrong], ex=None)
    assert ok != bad, \
        '编号插首位竟未影响 audit 结论——位置契约可能已解除，请复核注释'
    return '编号插首位确实改变 audit 结论（错位会静默出错）'


def main():
    tests = [t_no_fno_header_unchanged, t_fno_rendered_as_first_column,
             t_partial_fno_fills_blank, t_fno_lives_at_index_8,
             t_wrong_position_would_break_audit]
    ok = 0
    for t in tests:
        try:
            msg = t()
            print('  PASS %-38s %s' % (t.__name__, msg))
            ok += 1
        except Exception as e:
            print('  FAIL %-38s %s: %s' % (t.__name__, type(e).__name__, e))
    print('需求编号列回归: %d/%d 通过' % (ok, len(tests)))
    return 0 if ok == len(tests) else 1


if __name__ == '__main__':
    sys.exit(main())
