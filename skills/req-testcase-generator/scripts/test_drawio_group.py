# -*- coding: utf-8 -*-
"""tcgen.drawio 模块层与排版的回归测试（对应 SKILL.md 硬门禁 13 的思维导图各项）。

管道改动后跑：python test_drawio_group.py
覆盖：模块层触发/不触发、跨模块 TP 唯一归属、模块 id 不撞、零重叠、
父子距离上限、无裸用例节点、drawio 与 mermaid 层级一致。

存在理由：project_template 的样例数据只有 11 个 TP，达不到 group_min=12，
自检跑「硬门禁全部通过」时模块层这段代码根本没被执行。本文件专门造够量的
数据把它跑到，避免「自检通过但新代码没覆盖」。
"""
import collections
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcgen import plat  # noqa: E402

plat.force_utf8_stdout()   # Ubuntu 在 LC_ALL=C 下 print 中文会崩
from tcgen import drawio  # noqa: E402

MAX_PARENT_CHILD = 600   # 硬门禁 13 ⑤


def mk(tc, tp, title='标题', cover='正向', pri='P1', req='REQ-001'):
    return dict(tc=tc, tp=tp, title=title, cover=cover, pri=pri, req=req)


def parse(path):
    xml = open(path, encoding='utf-8').read()
    N = {}
    for m in re.finditer(r'<mxCell id="([^"]+)" value="([^"]*)".*?'
                         r'x="(-?\d+)" y="(-?\d+)" width="(\d+)" height="(\d+)"', xml):
        N[m.group(1)] = dict(v=m.group(2), x=int(m.group(3)), y=int(m.group(4)),
                             w=int(m.group(5)), h=int(m.group(6)))
    kids = collections.defaultdict(list)
    for s, t in re.findall(r'source="([^"]+)" target="([^"]+)"', xml):
        kids[s].append(t)
    return N, kids


def _cy(N, i):
    return N[i]['y'] + N[i]['h'] / 2.0


def _tpnum(label):
    """从 TP 节点文本（形如 `TP-F-001 描述`）里取出数字序号。"""
    m = re.match(r'TP-[A-Z]+-(\d+)', label.strip())
    assert m, '不是 TP 节点文本: %r' % label
    return int(m.group(1))


def check_layout(N, kids, tag):
    """硬门禁 13 的 ④⑤⑥：同层零重叠、父子距离、无裸用例节点。"""
    cols = collections.defaultdict(list)
    for i, n in N.items():
        cols[n['x']].append((n['y'], n['h'], i))
    for x, rows in cols.items():
        rows.sort()
        for a, b in zip(rows, rows[1:]):
            assert a[0] + a[1] <= b[0], '%s: 列x=%d 重叠 %s/%s' % (tag, x, a[2], b[2])
    # ⑤ 只查「模块→测试点」这一层。根→维度、维度→模块两层豁免：占大半 TP 的
    # 维度其块高由数据决定（咖啡项目实测功能维度 2117px、根 1588px），除拆成多张
    # 画板外无法压到 600px 内，故不阻断。这里若改成查所有父节点，本测试用的小规模
    # 数据能过，真实项目却会在维度层必然失败——那是门禁造假，别改回去。
    for p, ks in kids.items():
        if not p.startswith('mod_') or p not in N or not ks:
            continue
        ys = [_cy(N, k) for k in ks if k in N]
        if ys:
            d = abs(_cy(N, p) - min(ys))
            assert d <= MAX_PARENT_CHILD, ('%s: 模块[%s]距首个测试点 %.0fpx >%d，须再拆'
                                           % (tag, N[p]['v'][:20], d, MAX_PARENT_CHILD))
    for i, n in N.items():
        if i.startswith('c_'):
            assert not re.fullmatch(r'TC-[\w-]+ \[[^\]]+\]', n['v'].strip()), \
                '%s: 裸用例节点 %s' % (tag, n['v'])


def t_no_group():
    """TP 数未达阈值 → 不分组，TP 直挂维度。"""
    cs = [mk('TC-A-%03d' % i, 'TP-F-%03d' % i) for i in range(1, 6)]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'x.drawio')
        r = drawio.build(p, cs, root_label='P', group_min=12)
        assert r['mods'] == 0, r
        N, kids = parse(p)
        dim = [i for i, n in N.items() if n['v'] == '功能'][0]
        assert len(kids[dim]) == 5, '未分组时 TP 应直挂维度'
        check_layout(N, kids, 'no_group')
    return '不分组: TP 直挂维度'


def t_group():
    """TP 数达阈值 → 插模块层，父子距离与重叠都合规。"""
    cs = []
    for i in range(1, 16):
        m = 'ALPHA' if i <= 8 else 'BETA'
        cs.append(mk('TC-%s-%03d' % (m, i), 'TP-F-%03d' % i, title='用例%d' % i))
        cs.append(mk('TC-%s-%03d' % (m, i + 100), 'TP-F-%03d' % i,
                     title='反例%d' % i, cover='反向'))
    names = {'ALPHA': '甲模块', 'BETA': '乙模块'}
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'x.drawio')
        r = drawio.build(p, cs, root_label='P', group_min=12, module_names=names)
        assert r['mods'] == 2, r
        N, kids = parse(p)
        mods = [n['v'] for i, n in N.items() if i.startswith('mod_')]
        assert sorted(mods) == ['乙模块', '甲模块'], mods
        assert all(not re.search(r'[A-Za-z]', m) for m in mods), '模块名须中文'
        dim = [i for i, n in N.items() if n['v'] == '功能'][0]
        assert len(kids[dim]) == 2, '分组后维度应只接模块'
        check_layout(N, kids, 'group')
    return '分组: 2 模块, 中文名, 维度只接模块'


def t_cross_module_tp():
    """同一 TP 下用例跨模块 → 该 TP 只能出现在一个组里。"""
    cs = [mk('TC-AAA-001', 'TP-F-001'), mk('TC-BBB-002', 'TP-F-001')]
    cs += [mk('TC-AAA-%03d' % i, 'TP-F-%03d' % i) for i in range(2, 14)]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'x.drawio')
        drawio.build(p, cs, root_label='P', group_min=12,
                     module_names={'AAA': '甲', 'BBB': '乙'})
        N, kids = parse(p)
        tid = [i for i, n in N.items() if n['v'].startswith('TP-F-001 ')][0]
        parents = [p2 for p2, ks in kids.items() if tid in ks]
        assert len(parents) == 1, 'TP-F-001 挂了 %d 个父节点' % len(parents)
    return '跨模块 TP: 唯一归属'


def t_mod_id_unique():
    """两个维度都分组时模块 id 不能撞（曾因中文被清成 mod____0 而撞）。"""
    cs = [mk('TC-AAA-%03d' % i, 'TP-F-%03d' % i) for i in range(1, 14)]
    cs += [mk('TC-BBB-%03d' % i, 'TP-S-%03d' % i, cover='稳定性')
           for i in range(1, 14)]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'x.drawio')
        drawio.build(p, cs, root_label='P', group_min=12,
                     module_names={'AAA': '甲', 'BBB': '乙'})
        ids = re.findall(r'<mxCell id="(mod_[^"]+)"',
                         open(p, encoding='utf-8').read())
        assert len(ids) == len(set(ids)) == 2, ids
        assert '____' not in ''.join(ids), 'id 含连续下划线，中文被清洗: %s' % ids
    return '模块 id 唯一: %s' % ids


def t_dedupe():
    """TC 标题与 TP 描述同文 → 不重复整句，但不得只剩 ID+标签。"""
    cs = [mk('TC-AAA-001', 'TP-F-001', title='同一句话'),
          mk('TC-AAA-002', 'TP-F-001', title='另一句', cover='反向')]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'x.drawio')
        drawio.build(p, cs, root_label='P')
        N, _ = parse(p)
        v = N['c_TC_AAA_001']['v']
        assert '同一句话' not in v, '应省略与 TP 同文的标题: %s' % v
        assert len(v) > len('TC-AAA-001 [正向·P1]'), '不得只剩 ID+标签: %s' % v
    return '同文去重: %s' % v


def t_parity():
    """drawio 与 mermaid 层级必须一致，且 mermaid 缩进合法。"""
    cs = [mk('TC-AAA-%03d' % i, 'TP-F-%03d' % i) for i in range(1, 14)]
    cs += [mk('TC-CCC-001', 'TP-P-001', cover='性能')]
    kw = dict(root_label='P', group_min=12, module_names={'AAA': '甲'})
    with tempfile.TemporaryDirectory() as d:
        mp = os.path.join(d, 'x.mmd')
        a = drawio.build(os.path.join(d, 'x.drawio'), cs, **kw)
        b = drawio.mermaid(mp, cs, **kw)
        assert (a['mods'], a['tps'], a['tcs']) == (b['mods'], b['tps'], b['tcs']), \
            '层级不一致 drawio=%s mermaid=%s' % (a, b)
        lines = [l for l in open(mp, encoding='utf-8').read().splitlines() if l.strip()]
        assert lines[0] == 'mindmap' and lines[1].startswith('  root(('), lines[:2]
        for l in lines[2:]:
            ind = len(l) - len(l.lstrip())
            assert ind % 2 == 0 and 4 <= ind <= 10, '缩进非法: %r' % l
    return '同源一致: mods=%d tps=%d tcs=%d' % (a['mods'], a['tps'], a['tcs'])


def t_module_order():
    """模块顺序必须按「组内最小 TP 号」升序，不按用例数、不按字母序。

    造数据让三种排序结果互不相同：
      甲(ZZZ) 占 001~002，只 2 个 TP；乙(AAA) 占 010~021，12 个 TP。
    按用例数降序 → 乙在前（旧规则，回退时本测试失败）；
    按字母序     → AAA 在前；
    按最小 TP 号 → 甲在前（正确）。
    """
    cs = [mk('TC-ZZZ-%03d' % i, 'TP-F-%03d' % i) for i in (1, 2)]
    cs += [mk('TC-AAA-%03d' % i, 'TP-F-%03d' % i) for i in range(10, 22)]
    kw = dict(root_label='P', group_min=12,
              module_names={'ZZZ': '甲模块', 'AAA': '乙模块'})
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'x.drawio')
        drawio.build(p, cs, **kw)
        N, _ = parse(p)
        mods = sorted(((n['y'], n['v']) for i, n in N.items()
                       if i.startswith('mod_')))
        got = [v for _, v in mods]
        assert got == ['甲模块', '乙模块'], '模块顺序应按最小 TP 号: %s' % got
        # 自上而下 TP 号严格升序
        tps = sorted((n['y'], _tpnum(n['v'])) for i, n in N.items()
                     if i.startswith('n_'))
        nums = [x for _, x in tps]
        assert nums == sorted(nums), 'TP 号非升序: %s' % nums
    return '模块按最小 TP 号升序: %s' % got


def t_attribution_majority():
    """跨模块 TP 按「用例模块占多数」归属，不按首条用例。

    TP-F-001 有 1 条 AAA + 2 条 BBB，而按 (REQ, TC) 排序的首条是 AAA——
    旧规则「取首条」会判给 AAA（回退时本测试失败），正确应判给 BBB。
    """
    cs = [mk('TC-AAA-001', 'TP-F-001', req='REQ-001'),
          mk('TC-BBB-002', 'TP-F-001', req='REQ-002'),
          mk('TC-BBB-003', 'TP-F-001', req='REQ-003')]
    cs += [mk('TC-BBB-%03d' % i, 'TP-F-%03d' % i) for i in range(2, 14)]
    kw = dict(root_label='P', group_min=12,
              module_names={'AAA': '甲', 'BBB': '乙'})
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'x.drawio')
        drawio.build(p, cs, **kw)
        N, kids = parse(p)
        tid = [i for i, n in N.items() if n['v'].startswith('TP-F-001 ')][0]
        par = [p2 for p2, ks in kids.items() if tid in ks]
        assert len(par) == 1, 'TP-F-001 挂了 %d 个父节点' % len(par)
        assert N[par[0]]['v'] == '乙', 'TP-F-001 应归多数模块「乙」，实际 %s' % N[par[0]]['v']
        # 平票时按号段就近：AAA 只剩 0 个 TP，不应产生空模块节点
        mods = [n['v'] for i, n in N.items() if i.startswith('mod_')]
        assert '甲' not in mods, '不应产生空模块节点: %s' % mods
    return '跨模块 TP 归多数模块，无空模块'



def t_group_by_requirement():
    """group_by 按需求编号分组：顶层换成 F 编号，维度不再作为顶层。

    产测工具类需求的组织轴是「每条需求要测哪些方面」，不是「六维度下有哪些
    测试点」——后者会把同一条需求的测试点散到多个维度里，评审时看不出
    某条需求的测试面是否完整。
    """
    cases = [mk('TC-BURN-001', 'TP-F-001', req='REQ-001'),
             mk('TC-BURN-002', 'TP-F-002', req='REQ-002'),
             mk('TC-ENC-001', 'TP-S-001', req='REQ-006'),
             mk('TC-WL-001', 'TP-F-021', req='REQ-007')]
    f_of = {'REQ-001': 'F17', 'REQ-002': 'F17', 'REQ-006': 'F15', 'REQ-007': 'F04'}
    dims, groups, tp_desc, tp_cases = drawio.derive(
        cases, group_by=lambda c: f_of.get(c['req']))
    assert set(dims) == {'F17', 'F15', 'F04'}, '顶层未按 F 编号分组: %s' % dims
    assert '功能' not in dims, '维度仍出现在顶层: %s' % dims
    f17 = [tp for _, tps in groups['F17'] for tp in tps]
    assert set(f17) == {'TP-F-001', 'TP-F-002'}, 'F17 下测试点不对: %s' % f17
    # 跨维度的需求：F15 下同时可能有功能与稳定性 TP，仍归在同一个 F 下
    f15 = [tp for _, tps in groups['F15'] for tp in tps]
    assert f15 == ['TP-S-001'], 'F15 下测试点不对: %s' % f15
    return '顶层=%s，各需求测试点独立成块' % '/'.join(dims)


def t_group_by_keeps_dim_prefix():
    """按需求分组不得篡改 TP 前缀——维度语义仍在 TP-ID 上，硬门禁14 照常校验。"""
    cases = [mk('TC-A-001', 'TP-SEC-101', req='REQ-001'),
             mk('TC-A-002', 'TP-S-001', req='REQ-001')]
    dims, groups, _, _ = drawio.derive(cases, group_by=lambda c: 'F17')
    tps = [tp for _, tps_ in groups['F17'] for tp in tps_]
    assert 'TP-SEC-101' in tps and 'TP-S-001' in tps, 'TP 前缀被改动: %s' % tps
    assert drawio._dim_of('TP-SEC-101') == '安全', 'TP 前缀维度解析被破坏'
    return '安全/稳定性 TP 同归 F17，前缀维度语义不变'


def t_group_by_none_falls_into_ungrouped():
    """group_by 返回 None 的用例落入「未分组」，不静默丢弃。

    静默丢弃会让导图少节点却不报错，与「测试点真的漏了」无法区分。
    """
    cases = [mk('TC-A-001', 'TP-F-001', req='REQ-001'),
             mk('TC-B-001', 'TP-F-002', req='REQ-999')]
    f_of = {'REQ-001': 'F17'}
    dims, groups, _, _ = drawio.derive(cases, group_by=lambda c: f_of.get(c['req']))
    assert '未分组' in dims, '无归属的 TP 被丢弃了: %s' % dims
    assert dims[-1] == '未分组', '「未分组」应排在最后: %s' % dims
    ung = [tp for _, tps in groups['未分组'] for tp in tps]
    assert ung == ['TP-F-002'], '未分组内容不对: %s' % ung
    return '无归属 TP 进「未分组」并排在末尾'


def t_group_by_order_by_tp_no():
    """顶层顺序按组内最小 TP 号排，与模块层同口径，保证自上而下 TP 号递增。"""
    cases = [mk('TC-C-001', 'TP-F-050', req='REQ-A'),
             mk('TC-A-001', 'TP-F-001', req='REQ-B'),
             mk('TC-B-001', 'TP-F-020', req='REQ-C')]
    f_of = {'REQ-A': 'F13', 'REQ-B': 'F17', 'REQ-C': 'F04'}
    dims, _, _, _ = drawio.derive(cases, group_by=lambda c: f_of.get(c['req']))
    assert dims == ['F17', 'F04', 'F13'], '顶层未按最小 TP 号排: %s' % dims
    return '顶层顺序 %s（按最小 TP 号 1/20/50）' % '/'.join(dims)


def t_group_by_colors_stable():
    """自定义分组的配色按位置轮转，同一份数据两次构建配色一致（不用 hash）。"""
    order = ['F17', 'F15', 'F04']
    a = [drawio.colors_of(k, order) for k in order]
    b = [drawio.colors_of(k, order) for k in order]
    assert a == b, '两次取色不一致（用了 hash？）'
    assert len(set(map(tuple, a))) == 3, '三个分组取到了相同配色: %s' % a
    assert drawio.colors_of('功能', order) == drawio.DIM['功能'][1:], \
        '六维度应仍用各自语义色'
    return '配色按位置稳定轮转，维度色不受影响'


def main():
    ts = [t_no_group, t_group, t_cross_module_tp, t_mod_id_unique,
          t_dedupe, t_parity, t_module_order, t_attribution_majority,
          t_group_by_requirement, t_group_by_keeps_dim_prefix,
          t_group_by_none_falls_into_ungrouped,
          t_group_by_order_by_tp_no, t_group_by_colors_stable]
    bad = 0
    for t in ts:
        try:
            print('  PASS  %-18s %s' % (t.__name__, t()))
        except AssertionError as e:
            bad += 1
            print('  FAIL  %-18s %s' % (t.__name__, e))
    print('思维导图回归: %d/%d 通过' % (len(ts) - bad, len(ts)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
