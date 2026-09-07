# -*- coding: utf-8 -*-
"""测试点思维导图（Draw.io XML，飞书在线思维导图兼容）。

从用例集派生测试点：root → 六维度 → TP 节点，左→右树布局，
正交连线、无箭头（arrows="0"），坐标按块居中不重叠。

用法：
    from tcgen import drawio
    drawio.build('输出.drawio', CASES, root_label='XX项目',
                 extra_tp={'TP-P-001': ('性能', '交付误差<1cm')})
"""
import collections

# 维度: (TP 前缀, 维度节点 fill, 维度节点 stroke, TP 节点 fill, TP 节点 stroke)
DIM = {
    '功能':    (('TP-F',),   '#DBEAFE', '#3B82F6', '#EFF6FF', '#93C5FD'),
    '性能':    (('TP-P',),   '#FFEDD5', '#F97316', '#FFF7ED', '#FDBA74'),
    '稳定性':  (('TP-S',),   '#DCFCE7', '#22C55E', '#F0FDF4', '#86EFAC'),
    '兼容性':  (('TP-C',),   '#CFFAFE', '#06B6D4', '#ECFEFF', '#67E8F9'),
    '安全':    (('TP-SEC',), '#FEE2E2', '#EF4444', '#FEF2F2', '#FCA5A5'),
    '用户体验': (('TP-UX',),  '#F3E8FF', '#A855F7', '#FAF5FF', '#D8B4FE'),
}
# TP-SEC 必须先匹配，否则 TP-S 会吞掉它
_ORDER = ('TP-SEC', 'TP-F', 'TP-P', 'TP-S', 'TP-C', 'TP-UX')
_PFX2DIM = {p: d for d, (pfxs, *_) in DIM.items() for p in pfxs}


def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def _dim_of(tp):
    for p in _ORDER:
        if tp.startswith(p):
            return _PFX2DIM[p]
    return None


def build(out_path, cases, root_label, extra_tp=None, diagram_name=None):
    """extra_tp: {TP-ID: (维度, 描述)}，用于专项等不在普通用例里的测试点。"""
    tp_desc, tp_dim = {}, {}
    for c in cases:
        tp = c['tp']
        if tp not in tp_desc:
            tp_desc[tp] = c['title']
        d = _dim_of(tp)
        if d:
            tp_dim[tp] = d
    for tp, (d, desc) in (extra_tp or {}).items():
        tp_desc.setdefault(tp, desc)
        tp_dim.setdefault(tp, d)

    dims = list(DIM.keys())
    by_dim = collections.defaultdict(list)
    for tp, d in tp_dim.items():
        by_dim[d].append(tp)
    for d in by_dim:
        by_dim[d].sort()

    dim_x, tp_x, row_h = 320, 620, 42
    dim_y, tp_rows, cur = {}, [], 40
    for d in dims:
        tps = by_dim.get(d, [])
        block_start = cur
        for tp in tps:
            tp_rows.append((tp, cur, d))
            cur += row_h
        if not tps:
            cur += row_h
        dim_y[d] = (block_start + cur - row_h) // 2
        cur += 24   # 维度间距

    root_y = max((cur - row_h) // 2, 40)
    cells = ['<mxCell id="root" value="%s" style="rounded=1;whiteSpace=wrap;html=1;'
             'fillColor=#111827;fontColor=#FFFFFF;strokeColor=none;" vertex="1" '
             'parent="1"><mxGeometry x="40" y="%d" width="200" height="48" '
             'as="geometry"/></mxCell>' % (esc(root_label), root_y)]
    edges = []

    dim_id = {}
    for i, d in enumerate(dims):
        fill, stroke = DIM[d][1], DIM[d][2]
        did = 'dim_%d' % i
        dim_id[d] = did
        cells.append(
            '<mxCell id="%s" value="%s" style="rounded=1;whiteSpace=wrap;html=1;'
            'fillColor=%s;strokeColor=%s;fontStyle=1;" vertex="1" parent="1">'
            '<mxGeometry x="%d" y="%d" width="130" height="36" as="geometry"/></mxCell>'
            % (did, esc(d), fill, stroke, dim_x, dim_y[d]))
        edges.append(
            '<mxCell id="e_root_%s" edge="1" parent="1" source="root" target="%s" '
            'style="edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;startArrow=none;'
            'endArrow=none;exitX=1;exitY=0.5;entryX=0;entryY=0.5;strokeColor=%s;">'
            '<mxGeometry relative="1" as="geometry"/></mxCell>' % (did, did, stroke))

    for tp, ty, d in tp_rows:
        tfill, tstroke = DIM[d][3], DIM[d][4]
        tid = 'n_' + tp.replace('-', '_')
        label = '%s %s' % (tp, tp_desc.get(tp, ''))
        cells.append(
            '<mxCell id="%s" value="%s" style="rounded=1;whiteSpace=wrap;html=1;'
            'fillColor=%s;strokeColor=%s;" vertex="1" parent="1">'
            '<mxGeometry x="%d" y="%d" width="300" height="34" as="geometry"/></mxCell>'
            % (tid, esc(label), tfill, tstroke, tp_x, ty))
        edges.append(
            '<mxCell id="e_%s" edge="1" parent="1" source="%s" target="%s" '
            'style="edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;startArrow=none;'
            'endArrow=none;exitX=1;exitY=0.5;entryX=0;entryY=0.5;strokeColor=%s;">'
            '<mxGeometry relative="1" as="geometry"/></mxCell>'
            % (tid, dim_id[d], tid, tstroke))

    xml = ('<mxfile host="app.diagrams.net">\n<diagram name="%s">\n'
           '<mxGraphModel dx="1400" dy="1000" grid="0" fold="1" arrows="0" connect="1">\n'
           '<root>\n<mxCell id="0"/>\n<mxCell id="1" parent="0"/>\n'
           % esc(diagram_name or root_label)
           + "\n".join(cells) + "\n" + "\n".join(edges)
           + '\n</root>\n</mxGraphModel>\n</diagram>\n</mxfile>\n')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(xml)
    return dict(dims=len(dims), tps=len(tp_rows))
