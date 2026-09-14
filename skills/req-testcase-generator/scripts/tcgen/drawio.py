# -*- coding: utf-8 -*-
"""测试点思维导图（Draw.io XML + Mermaid，飞书兼容）。

两种输出同源：`build()` 出 `.drawio`（导入飞书云文档），`mermaid()` 出 `.mmd`
（经 whiteboard-cli 写入飞书画板）。层级派生都走 `derive()`，不会两处各写一份。

层次：root → 六维度 → [模块] → 测试点(TP) → 测试用例(TC)。
TC 层是评审用的「每个测试点测哪些方面」，节点文本 = TC-ID + 覆盖类型 + 优先级 + 标题，
因此评审时可直接照图说明：测哪些维度 → 哪些模块 → 哪些测试点 → 每个测试点覆盖哪些方面。
「模块」层只在某维度 TP 数达 `group_min` 时插入，见 derive() 的说明。

布局：左→右树，叶子(TC)逐行铺开、父节点(TP/模块/维度/root)按子块纵向居中，
正交连线、无箭头（arrows="0"），坐标不重叠。

用法：
    from tcgen import drawio
    drawio.build('输出.drawio', CASES, root_label='XX项目',
                 extra_tp={'TP-P-001': ('性能', '交付误差<1cm')},
                 group_min=12, module_names={'SAVE': '保存制作流程'})
    # 只要三级（不展开用例）时：show_cases=False
    # 测试点另有正式名称时：tp_names={'TP-F-001': '保存制作流程生效'}
    # 专项用例不在 CASES 里（走专项两表）时，用 extra_cases 挂上去：
    #   extra_cases=[dict(tc='TC-SP-PERF-001', tp='TP-P-001', title='单杯时长',
    #                     cover='专项', pri='P1', req='REQ-068')]
"""
import collections
import re

# 维度: (TP 前缀, 维度 fill, 维度 stroke, TP fill, TP stroke, TC fill)
DIM = {
    '功能':    (('TP-F',),   '#DBEAFE', '#3B82F6', '#EFF6FF', '#93C5FD', '#FBFDFF'),
    '性能':    (('TP-P',),   '#FFEDD5', '#F97316', '#FFF7ED', '#FDBA74', '#FFFCF7'),
    '稳定性':  (('TP-S',),   '#DCFCE7', '#22C55E', '#F0FDF4', '#86EFAC', '#FAFEFB'),
    '兼容性':  (('TP-C',),   '#CFFAFE', '#06B6D4', '#ECFEFF', '#67E8F9', '#F9FEFF'),
    '安全':    (('TP-SEC',), '#FEE2E2', '#EF4444', '#FEF2F2', '#FCA5A5', '#FFFAFA'),
    '用户体验': (('TP-UX',),  '#F3E8FF', '#A855F7', '#FAF5FF', '#D8B4FE', '#FDFBFF'),
}
# TP-SEC 必须先匹配，否则 TP-S 会吞掉它
_ORDER = ('TP-SEC', 'TP-F', 'TP-P', 'TP-S', 'TP-C', 'TP-UX')
_PFX2DIM = {p: d for d, (pfxs, *_) in DIM.items() for p in pfxs}

# 顶层按自定义键分组（group_by）时的配色轮转表。六维度各有语义色，
# 而「按需求编号分组」这类自定义键没有固有语义，故按出现顺序轮转取色，
# 保证同一份数据每次构建配色稳定（不用 hash，hash 随进程变）。
_PALETTE = [DIM[d][1:] for d in DIM]

# 列 x 坐标与节点宽度
X_ROOT, W_ROOT, H_ROOT = 40, 200, 48
X_DIM, W_DIM, H_DIM = 320, 130, 36
X_MOD, W_MOD, H_MOD = 520, 170, 34
X_TP, W_TP, H_TP = 760, 300, 34
X_TC, W_TC, H_TC = 1120, 430, 30

ROW_H = 36      # 每个叶子占一行
TP_GAP = 10     # 相邻测试点块的额外间距
MOD_GAP = 18    # 相邻模块块的额外间距
DIM_GAP = 26    # 相邻维度块的额外间距

_EDGE = ('edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;startArrow=none;'
         'endArrow=none;exitX=1;exitY=0.5;entryX=0;entryY=0.5;strokeColor=%s;')


def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def _dim_of(tp):
    for p in _ORDER:
        if tp.startswith(p):
            return _PFX2DIM[p]
    return None


def colors_of(label, order=()):
    """取某顶层分组的配色 (维度fill, 维度stroke, TPfill, TPstroke, TCfill)。

    六维度用各自的语义色；`group_by` 传入的自定义分组键（如需求编号 F17）
    没有固有语义，按它在 `order` 中的位置轮转取色——用位置而非 hash，
    这样同一份数据每次构建的配色完全一致，diff 时不会出现无意义的颜色变动。
    """
    if label in DIM:
        return DIM[label][1:]
    idx = list(order).index(label) if label in order else 0
    return _PALETTE[idx % len(_PALETTE)]


def _node(nid, label, x, y, w, h, fill, stroke, extra=''):
    return ('<mxCell id="%s" value="%s" style="rounded=1;whiteSpace=wrap;html=1;'
            'fillColor=%s;strokeColor=%s;%s" vertex="1" parent="1">'
            '<mxGeometry x="%d" y="%d" width="%d" height="%d" as="geometry"/>'
            '</mxCell>' % (nid, esc(label), fill, stroke, extra, x, y, w, h))


def _edge(eid, src, dst, stroke):
    return ('<mxCell id="%s" edge="1" parent="1" source="%s" target="%s" '
            'style="%s"><mxGeometry relative="1" as="geometry"/></mxCell>'
            % (eid, src, dst, _EDGE % stroke))


def _center(top, bottom, h):
    """子块 [top, bottom) 的纵向中心处放一个高 h 的父节点，返回父节点 y。"""
    return max((top + bottom - h) // 2, 0)


def _norm_case(c):
    """补齐 extra_cases 里可能缺的字段，使其与 dsl 用例同构。"""
    return dict(tc=c.get('tc', '?'), tp=c.get('tp', '?'),
                title=c.get('title', ''), cover=c.get('cover', '专项'),
                pri=c.get('pri', '-'), req=c.get('req', ''))


def case_label(c, tp_desc=None):
    """TC 节点文本：ID + 覆盖类型 + 优先级 + 标题，评审时一眼看出测的是哪个方面。

    tp_desc 传入该 TC 所属 TP 的描述时，若两者文字完全相同则省略标题——
    默认 TP 描述取自其首条用例标题，不省会让父子两个节点显示同一句话，
    白白拉宽节点、加重文字溢出。
    """
    head = '%s [%s·%s]' % (c['tc'], c['cover'], c['pri'])
    title = (c['title'] or '').strip()
    if tp_desc and title and title == str(tp_desc).strip():
        # 与父 TP 同文时不重复整句，但必须留下可读的「测哪个方面」，
        # 否则节点只剩 ID+标签，评审看不出这条在验什么。
        return '%s 同测试点主场景' % head
    return '%s %s' % (head, title)


def _tp_no(tp):
    """取 TP-ID 的数字序号用于排序。按数字而非字符串排：位数不齐时
    （TP-F-9 与 TP-F-10）字符串序会把 10 排到 9 前面。取不到号的排最后。"""
    m = re.search(r'(\d+)\s*$', str(tp))
    return int(m.group(1)) if m else 10 ** 9


def _mod_id(dims, d, gi):
    """模块节点 id。用维度序号而非维度名：维度名是中文，正则清洗后会变成
    一串下划线（mod____0），不同维度的同序号组会撞 id。drawio 与 mermaid
    共用本函数，保证两种输出的节点 id 一致。"""
    return 'mod_%d_%d' % (dims.index(d), gi)


def module_of(tc):
    """从 TC-ID 取模块缩写：TC-{模块}-001 / TC-EX-{模块}-001 / TC-SP-{模块}-001。"""
    m = re.match(r'TC-(?:EX-|SP-)?([A-Z0-9]+)', str(tc))
    return m.group(1) if m else '?'


def _attribute(tps, tp_cases):
    """把每个 TP 归到唯一一个模块，返回 {模块缩写: [TP-ID]}。

    一个 TP 只能进一个组，否则同一 TP 会在多个模块下重复出现、TC 数虚高。规则：
    ① **用例模块占多数者胜**。不能「取首条用例」——首条是按 (REQ, TC) 排序的结果，
       与模块无关：跨模块 TP 会被判给号段完全不相干的模块（实测 TP-F-041 有
       2 条 STATE + 2 条 COMBO，首条 TC-STATE-018 的 REQ 较小，于是 041 被判给
       STATE，可它的号在 04x 段即组合编排段，导致 STATE 组最小号变成 041、
       整个 06x 块被提到 050 前面，模块顺序出现两处逆序）。
    ② **平票时归给号段最近的模块**。TP 号是分段编排的（一个模块占一个十位段），
       取各候选模块在①中已定下的 TP 号，谁离本 TP 最近就归谁。
    """
    counted = {tp: collections.Counter(module_of(c['tc'])
                                       for c in tp_cases.get(tp, []))
               for tp in tps}

    # 第一轮：占多数的直接定；平票的挂起，等①的结果出来再判
    firm, pending = collections.defaultdict(list), []
    for tp in tps:
        cnt = counted[tp]
        if not cnt:
            firm['?'].append(tp)
            continue
        top = max(cnt.values())
        winners = sorted(k for k, v in cnt.items() if v == top)
        if len(winners) == 1:
            firm[winners[0]].append(tp)
        else:
            pending.append((tp, winners))

    # 第二轮：平票的按号段就近归属
    for tp, winners in pending:
        n = _tp_no(tp)
        firm[min(winners, key=lambda m: (
            min((abs(_tp_no(t) - n) for t in firm.get(m, ())), default=10 ** 9),
            m))].append(tp)
    return firm


def derive(cases, extra_tp=None, tp_names=None, extra_cases=(),
           group_min=0, module_names=None, group_by=None):
    """把用例集派生成思维导图层级数据，drawio 与 mermaid 两种输出共用。

    group_by: 顶层分组方式。
        None（默认）= 按六维度分组，顶层是 功能/性能/稳定性/兼容性/安全/用户体验。
        callable    = 接收一条用例 dict、返回分组标签的函数，顶层换成该标签。
            用于「按需求编号组织」这类场景：产测工具类需求里，读者关心的是
            「F17 要测哪些方面」，而不是「功能维度下有哪些测试点」——按需求编号
            分组时一眼能看到每条需求各自的测试面，按维度分组则会把同一条需求的
            测试点散到六个维度里。
            维度信息不因此丢失：TP 前缀仍带维度语义，硬门禁 14（TP 维度与用例
            维度一致）照常校验，只是导图的顶层换了组织轴。
            返回 None 的用例落入「未分组」，不静默丢弃。

    group_min: 某维度的 TP 数 >= 该值时，在「维度」与「测试点」之间插入一层
        「模块」分组。0 = 不分组。**这一层是防重叠/防维度标签跑出屏幕的关键**：
        思维导图（尤其飞书画板的原生自动布局）把父节点摆在其整个子块的垂直中心，
        某个维度独占大半测试点时（如功能维度占 79 个 TP 中的 56 个），它的子块
        高达数千 px，维度标签被摆到正中间，读者滚到最上面几行测试点时标签已在
        屏幕外，看起来就是「维度丢了、直接显示 TP-TC」。分组后单块高度回落到
        可视范围，标签始终在其子节点近旁。
    module_names: {模块缩写: 中文名}。交付件命名要求中文，缺失则回退用缩写。

    返回 (dims, groups, tp_desc, tp_cases)：
        dims     六维度固定顺序
        groups   {维度: [(模块标签 or None, [TP-ID 升序]), ...]}
                 模块标签为 None 表示该维度不分组，TP 直挂维度
        tp_desc  {TP-ID: 测试点描述}
        tp_cases {TP-ID: [用例(按 REQ,TC 排序)]}
    """
    tp_names = tp_names or {}
    module_names = module_names or {}
    tp_desc, tp_dim = {}, {}
    tp_cases = collections.defaultdict(list)
    for c in list(cases) + [_norm_case(x) for x in (extra_cases or ())]:
        tp = c['tp']
        tp_cases[tp].append(c)
        if tp not in tp_desc:
            tp_desc[tp] = c['title']
        d = group_by(c) if group_by else _dim_of(tp)
        if d:
            tp_dim[tp] = d
        elif group_by:
            # group_by 返回 None：归入「未分组」而不是丢掉这个 TP。
            # 静默丢弃会让导图少节点却不报错，与「测试点漏了」无法区分。
            tp_dim[tp] = '未分组'
    for tp, (d, desc) in (extra_tp or {}).items():
        tp_desc.setdefault(tp, desc)
        tp_dim.setdefault(tp, d)
    for tp, name in tp_names.items():
        if tp in tp_desc or tp in tp_dim:
            tp_desc[tp] = name
    for tp in tp_cases:
        tp_cases[tp].sort(key=lambda c: (c['req'], c['tc']))

    by_dim = collections.defaultdict(list)
    for tp, d in tp_dim.items():
        by_dim[d].append(tp)
    for d in by_dim:
        by_dim[d].sort()
    if group_by:
        # 自定义分组：顶层顺序按「组内最小 TP 号」排，与模块层同一口径，
        # 保证读者自上而下看到的 TP 编号递增；「未分组」固定排在最后。
        keys = [k for k in by_dim if k != '未分组']
        dims = sorted(keys, key=lambda k: _tp_no(min(by_dim[k])))
        if '未分组' in by_dim:
            dims.append('未分组')
    else:
        dims = list(DIM.keys())

    # ---- 模块分组：只对 TP 数达阈值的维度生效，避免小维度被拆成一堆单元素组 ----
    groups = {}
    for d in dims:
        tps = by_dim.get(d, [])
        if not tps:
            groups[d] = []
        elif not group_min or len(tps) < group_min:
            groups[d] = [(None, tps)]
        else:
            buckets = _attribute(tps, tp_cases)
            # 模块顺序按「组内最小 TP 号」排，不按用例数——TP 号本身是分段编排的
            # （一个模块占一个十位段），按号排出来的顺序才和编号一致：读者从上往下
            # 看到的就是 TP-F-001、002…递增。按用例数排会让 001 开头的模块掉到中间。
            groups[d] = [(module_names.get(k, k), sorted(v))
                         for k, v in sorted(buckets.items(),
                                            key=lambda kv: (_tp_no(min(kv[1])),
                                                            kv[0]))]
    return dims, groups, tp_desc, tp_cases


def build(out_path, cases, root_label, extra_tp=None, diagram_name=None,
          show_cases=True, tp_names=None, extra_cases=(),
          group_min=0, module_names=None, dedupe_titles=True, group_by=None):
    """extra_tp: {TP-ID: (维度, 描述)}，用于专项等不在普通用例里的测试点。
    show_cases: 是否展开 TC 节点（评审版默认展开）。
    tp_names:   {TP-ID: 测试点名称}，覆盖「取该 TP 第一条用例标题」的默认派生。
    extra_cases: 不在 CASES 里的用例（如走专项两表的专项用例）。
    group_min / module_names: 见 derive()。
    dedupe_titles: TC 标题与其 TP 描述相同时省略标题，见 case_label()。
    """
    dims, groups, tp_desc, tp_cases = derive(
        cases, extra_tp, tp_names, extra_cases, group_min, module_names,
        group_by)

    # ---- 叶子驱动的树布局：TC 逐行铺开，各级父节点按自己的子块居中 ----
    dim_y, mod_rows, tp_rows, tc_rows = {}, [], [], []
    parent_of = {}
    cur = 40
    for d in dims:
        gs = groups.get(d) or []
        if not gs:
            continue
        dim_top = cur
        for gi, (label, tps) in enumerate(gs):
            grp_top = cur
            mid = _mod_id(dims, d, gi)
            for tp in tps:
                cs = tp_cases.get(tp, []) if show_cases else []
                tp_top = cur
                if cs:
                    for c in cs:
                        tc_rows.append((c, cur, d, tp))
                        cur += ROW_H
                else:
                    cur += ROW_H   # 无用例的测试点（如专项 extra_tp）仍占一行
                tp_rows.append((tp, _center(tp_top, cur, H_TP), d))
                if label is not None:
                    parent_of[tp] = mid
                cur += TP_GAP
            if label is not None:
                mod_rows.append((mid, d, label, _center(grp_top, cur - TP_GAP, H_MOD)))
                cur += MOD_GAP
        dim_y[d] = _center(dim_top, cur - TP_GAP, H_DIM)
        cur += DIM_GAP

    cells = [_node('root', root_label, X_ROOT, _center(40, cur - DIM_GAP, H_ROOT),
                   W_ROOT, H_ROOT, '#111827', 'none', 'fontColor=#FFFFFF;')]
    edges = []

    dim_id = {}
    for i, d in enumerate(dims):
        if not groups.get(d):
            continue
        _c = colors_of(d, dims)
        fill, stroke = _c[0], _c[1]
        did = 'dim_%d' % i
        dim_id[d] = did
        cells.append(_node(did, d, X_DIM, dim_y[d], W_DIM, H_DIM, fill, stroke,
                           'fontStyle=1;'))
        edges.append(_edge('e_root_%s' % did, 'root', did, stroke))

    for mid, d, label, my in mod_rows:
        _c = colors_of(d, dims)
        fill, stroke = _c[2], _c[1]
        cells.append(_node(mid, label, X_MOD, my, W_MOD, H_MOD, fill, stroke,
                           'fontStyle=1;'))
        edges.append(_edge('e_%s' % mid, dim_id[d], mid, stroke))

    tp_id = {}
    for tp, ty, d in tp_rows:
        _c = colors_of(d, dims)
        tfill, tstroke = _c[2], _c[3]
        tid = 'n_' + tp.replace('-', '_')
        tp_id[tp] = tid
        label = '%s %s' % (tp, tp_desc.get(tp, ''))
        cells.append(_node(tid, label, X_TP, ty, W_TP, H_TP, tfill, tstroke))
        edges.append(_edge('e_%s' % tid, parent_of.get(tp, dim_id[d]), tid, tstroke))

    for c, cy, d, tp in tc_rows:
        _c = colors_of(d, dims)
        cfill, cstroke = _c[4], _c[3]
        cid = 'c_' + c['tc'].replace('-', '_')
        lbl = case_label(c, tp_desc.get(tp) if dedupe_titles else None)
        cells.append(_node(cid, lbl, X_TC, cy, W_TC, H_TC,
                           cfill, cstroke, 'fontSize=11;align=left;spacingLeft=8;'))
        edges.append(_edge('e_%s' % cid, tp_id[c['tp']], cid, cstroke))

    xml = ('<mxfile host="app.diagrams.net">\n<diagram name="%s">\n'
           '<mxGraphModel dx="1400" dy="1000" grid="0" fold="1" arrows="0" connect="1">\n'
           '<root>\n<mxCell id="0"/>\n<mxCell id="1" parent="0"/>\n'
           % esc(diagram_name or root_label)
           + "\n".join(cells) + "\n" + "\n".join(edges)
           + '\n</root>\n</mxGraphModel>\n</diagram>\n</mxfile>\n')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(xml)
    return dict(dims=len(dim_id), mods=len(mod_rows),
                tps=len(tp_rows), tcs=len(tc_rows))


# ---- Mermaid 输出（写入飞书画板用；与 build() 同源，勿另写一份派生逻辑）----

def _mm_text(s):
    """Mermaid 节点文本：整体用双引号包裹，故内部双引号换成单引号；换行压平。"""
    return str(s).replace('"', "'").replace('\n', ' ').replace('\r', ' ').strip()


def _mm_id(s):
    return re.sub(r'[^0-9A-Za-z_]', '_', str(s))


def mermaid(out_path, cases, root_label, extra_tp=None, show_cases=True,
            tp_names=None, extra_cases=(), group_min=0, module_names=None,
            dedupe_titles=True, group_by=None):
    """生成 Mermaid mindmap（.mmd），层级与 build() 完全一致：
    root -> 顶层分组（默认六维度，group_by 可换成需求编号等）-> [模块] -> 测试点 -> 测试用例。

    用途：飞书画板只认代码/原生格式，不认 .drawio。写入方式见 SKILL.md，
    要点是 whiteboard-cli --to openapi 管道给 whiteboard +update --overwrite，
    且 --overwrite 会清空画板原有节点，执行前先 +query --output_as raw 备份。
    """
    dims, groups, tp_desc, tp_cases = derive(
        cases, extra_tp, tp_names, extra_cases, group_min, module_names,
        group_by)

    lines = ['mindmap', '  root((%s))' % _mm_text(root_label)]
    n_dim = n_mod = n_tp = n_tc = 0
    for d in dims:
        gs = groups.get(d) or []
        if not gs:
            continue
        n_dim += 1
        lines.append('    %s' % _mm_text(d))
        for gi, (label, tps) in enumerate(gs):
            ind = '      '
            if label is not None:
                lines.append('%s%s["%s"]'
                             % (ind, _mod_id(dims, d, gi), _mm_text(label)))
                n_mod += 1
                ind = '        '
            for tp in tps:
                lines.append('%s%s["%s %s"]'
                             % (ind, _mm_id(tp), tp, _mm_text(tp_desc.get(tp, ''))))
                n_tp += 1
                if not show_cases:
                    continue
                for c in tp_cases.get(tp, []):
                    lbl = case_label(c, tp_desc.get(tp) if dedupe_titles else None)
                    lines.append('%s  %s["%s"]'
                                 % (ind, _mm_id(c['tc']), _mm_text(lbl)))
                    n_tc += 1

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return dict(dims=n_dim, mods=n_mod, tps=n_tp, tcs=n_tc)
