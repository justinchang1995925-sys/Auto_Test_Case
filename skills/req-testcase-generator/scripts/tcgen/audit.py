# -*- coding: utf-8 -*-
"""质量审计门禁计算（通用，与项目无关）。

审计三铁律的落地：每个门禁数都由集合运算/遍历得出，并列出违例 ID，禁止手填 0。
项目侧只提供数据，门禁口径不随项目变化。

用法：
    from tcgen.audit import compute, gates
    a = compute(cases=CASES, req_src=REQ_SRC, ex=d_ex, spec_reqs={'REQ-003'})
"""
import collections
import re

from .dsl import PRI_RISK, TT2DIM, tp_dim

POS_COVER = ('正向', '主流程')
NEG_COVER = ('反向', '异常', '边界')
STATUS_OK = {'必测', '选测', '不适用'}
WEAK_BASIS = ('不重要', '概率低', '影响小', '没必要')
TYPE_OK = {'功能', '性能', '稳定性', '兼容性', '安全', '用户体验'}
MEASURABLE_OK = {'可测', '不可测'}
COVER_STATUS_OK = {'待覆盖', '阻塞', 'N/A'}
# 功能安全三触发源：键=用例「测试数据」列里的关键字，值=报告展示名
FS_SOURCES = {'面板': '面板', '外部': '外部回路', '软件': '软件指令'}

# 门禁A：标题写成「验证方法」的语言特征 —— 手段介词 + 元动词收尾。
# 只匹配句末，且排除「验证码/校验和/检查项」这类元动词作名词的情形；
# 实测对 147 条真实标题零误报，故可作阻断项。
TITLE_META_RX = re.compile(
    r'(由|用|通过|借助|以)[^,;，；]{0,12}(验证|校验|检查|核实|测试)(?![码和项表器])\s*$')

# 门禁B：专用型测试类型 → 其唯一合法覆盖类型。
# 只约束功能维度内的三个专用类型。**性能/稳定性/兼容性测试不能列进来**：
# 它们是跨维度类型，覆盖类型由「后果归属」决定而非由测试类型决定——
# exception-library.md 明文规定 EX 交叉用例后果为「数据不一致」时归稳定性维度、
# 测试类型填 `稳定性测试`，而覆盖类型用 `异常`/`反向`。把它们列进来会把这种
# 合规写法误判成违例（实测拦到 TC-EX-DATA-001）。
# 通用型（功能/接口/安全/用户体验测试）本就可搭配多种覆盖类型，同样不列入。
TTYPE_COVER = {
    '反向测试': '反向', '边界测试': '边界', '异常测试': '异常',
}

# 软提示C：设计技法 → 相容的测试类型白名单（按技法原理列，不是拟合现有数据）。
# 未列入的技法（如异常注入）不参与该提示。
TECH_TTYPE_OK = {
    '边界值': {'边界测试', '功能测试', '反向测试', '异常测试'},
    '错误推测': {'反向测试', '异常测试', '功能测试', '接口测试',
                 '用户体验测试', '稳定性测试'},
    '等价类': {'功能测试', '反向测试', '异常测试', '用户体验测试'},
    '判定表': {'功能测试', '反向测试', '异常测试'},
    '状态迁移': {'功能测试', '接口测试', '反向测试', '异常测试'},
    '场景法': {'功能测试', '接口测试', '用户体验测试', '性能测试',
               '稳定性测试', '兼容性测试', '安全测试', '异常测试', '反向测试'},
}



def compute(cases, req_src, ex=None, spec_reqs=frozenset(), fs_source_map=None,
            spec_companion_reqs=None, tp_name_map=None):
    """返回全部门禁数与违例清单。

    cases    : dsl.add 收集的用例列表
    req_src  : REQ 清单行，字段序 (id, 描述, 来源文档, 章节, 类型, 可测性, 覆盖状态, 备注)
    ex       : 异常交叉矩阵模块（可为 None，表示本期无 EX 纳入）
    spec_reqs: 仅由专项用例覆盖的 REQ。它们不在普通用例里，故计入覆盖集、
               且不参与功能深度判定（另走专项配套规则）。
    spec_companion_reqs: 被专项测试覆盖的 REQ 全集，即须校验「专项+配套功能用例」的集合。
               通常 ⊇ spec_reqs——有些 REQ 既有普通功能用例、又被专项覆盖（如成功率类），
               它们要参与功能深度判定，但同样须有配套功能用例。默认取 spec_reqs。
    """
    CS = cases
    tp_name_map = tp_name_map or {}
    spec_reqs = set(spec_reqs)
    companion = set(spec_companion_reqs) if spec_companion_reqs else set(spec_reqs)
    srcmap = fs_source_map or FS_SOURCES

    # ---- 覆盖率 ----
    testable = [r[0] for r in req_src if r[5] == '可测' and r[6] != '阻塞']
    blocked_req = [r[0] for r in req_src if r[6] == '阻塞']
    na_req = [r[0] for r in req_src if r[6] == 'N/A']
    covered = set(c['req'] for c in CS) | spec_reqs
    uncovered = [r for r in testable if r not in covered]

    # ---- 覆盖深度：功能 REQ 须含正向类 且 非正向类 ----
    req_cov = collections.defaultdict(set)
    for c in CS:
        req_cov[c['req']].add(c['cover'])
    func = set(c['req'] for c in CS if c['ttype'] == '功能测试')
    depth_bad = [r for r in func if r not in spec_reqs and not (
        any(x in POS_COVER for x in req_cov[r]) and
        any(x in NEG_COVER for x in req_cov[r]))]

    # ---- 一对多坍缩：一条 TC 不得挂多个 TP 或多个 REQ ----
    tc2tp = collections.defaultdict(set)
    tc2req = collections.defaultdict(set)
    for c in CS:
        tc2tp[c['tc']].add(c['tp'])
        tc2req[c['tc']].add(c['req'])
    collapse_tp = sorted(k for k, v in tc2tp.items() if len(v) > 1)
    collapse_req = sorted(k for k, v in tc2req.items() if len(v) > 1)
    # 每个 TP 至少一条专属 TC
    tp_tc = collections.defaultdict(set)
    for c in CS:
        tp_tc[c['tp']].add(c['tc'])
    tp_no_tc = sorted(tp for tp, v in tp_tc.items() if not v)

    # ---- 门禁：测试点 1:1 退化（测试点层没做抽象，只是复读用例标题）----
    # 坍缩的对称反面：坍缩是「多 TP 挤进一条 TC」，退化是「每个 TP 只挂一条 TC 且
    # 描述与该用例标题同文」。它不违反坍缩/深度/追溯任何一条，却让测试点层完全失去
    # 信息量——思维导图里用例节点会因去重显示「同测试点主场景」，评审看不出测了哪些方面。
    # 判据取「唯一用例 且 标题与 TP 描述同文」：只看数量比会把「该测试点确实只需一条用例」
    # 的合规情形也算进来（如某些一次性校验项），必须叠加同文条件才不误报。
    tp_titles = collections.defaultdict(list)
    for c in CS:
        tp_titles[c['tp']].append((c['tc'], (c['title'] or '').strip()))
    # 未给正式名称时，测试点描述**按定义**就是首条用例标题（drawio.derive 的默认派生），
    # 因此「唯一用例 + 未给名称」即同文退化；给了名称就说明已做抽象，不算。
    tp_degenerate = sorted(
        tp for tp, lst in tp_titles.items()
        if len(lst) == 1 and not (tp_name_map or {}).get(tp))

    # ---- 反模式：步骤与预期条数错位（构建期 assert 已挡，此处二次复核）----
    step_bad = [c['tc'] for c in CS if len(c['steps']) != len(c['exp'])]

    # ---- 状态与优先级 ----
    ready = sum(c['status'] == 'Ready' for c in CS)
    blk = sum(c['status'] == 'Blocked' for c in CS)
    draft = sum(c['status'] == 'Draft' for c in CS)
    pri = {p: sum(c['pri'] == p for c in CS) for p in ('P0', 'P1', 'P2', 'P3')}
    tot = len(CS)

    # 专项 REQ 须同时有专项用例与功能可用性用例（只验功能走通，不判指标）
    spec_companion_bad = [r for r in sorted(companion)
                          if not any(c['req'] == r and c['ttype'] == '功能测试'
                                     for c in CS)]
    spec_ok = not spec_companion_bad

    risk_map = {'高': ('P0', 'P1'), '中': ('P2',), '低': ('P3',)}
    pri_incons = [c['tc'] for c in CS
                  if c['pri'] not in risk_map.get(PRI_RISK[c['pri']], ())]

    # ---- 门禁：TP 维度与用例维度错配 ----
    dim_bad = [c['tc'] for c in CS
               if TT2DIM.get(c['ttype'], '?') != tp_dim(c['tp'])]

    # ---- 门禁 A：标题不得写「验证方法」而非「场景+预期」----
    # 反例（真实踩过）：`试听中不可取消由再次点击验证` —— 元动词收尾说明整句在描述
    # 「用什么手段去验」，而标题应当写「什么条件下发生什么、预期如何」。
    # 只判句末：元动词出现在句中多为名词或定语（`用验证码登录成功`、
    # `验证码错误时提示重新输入`），一律不算违例。
    title_meta_bad = [c['tc'] for c in CS if TITLE_META_RX.search(c['title'] or '')]

    # ---- 门禁 B：覆盖类型 ↔ 测试类型 必须同源 ----
    # 专用型测试类型（反向/边界/异常/性能/稳定性/兼容性测试）各自绑定唯一覆盖类型；
    # 抓的是「改了一个字段忘改另一个」——两列自相矛盾时，导图、附表、矩阵会各说一套。
    # 通用型（功能/接口/安全/用户体验测试）可搭配多种覆盖类型，不在此约束内。
    cover_bad = [c['tc'] for c in CS
                 if c['ttype'] in TTYPE_COVER and c['cover'] != TTYPE_COVER[c['ttype']]]

    # ---- 软提示 C：设计技法 ↔ 测试类型 相容性（列出待人工确认，不阻断）----
    # 技法决定了用例在测什么，与测试类型应当相容；但边界情形确实存在
    # （如状态迁移技法配边界测试），故只提示不阻断，避免误报稀释硬门禁可信度。
    tech_warn = [c['tc'] for c in CS
                 if c['tech'] in TECH_TTYPE_OK
                 and c['ttype'] not in TECH_TTYPE_OK[c['tech']]]

    # ---- 门禁：REQ 清单结构性完整（章节反查/编号/字段/分母）----
    req_secs = set((r[2], r[3]) for r in req_src)
    doc_sections = getattr(ex, 'DOC_SECTIONS', {}) if ex else {}
    section_na = getattr(ex, 'SECTION_NA', {}) if ex else {}
    doc_secs = set((d, s) for d, ss in doc_sections.items() for s in ss)
    sec_gap = sorted(doc_secs - req_secs - set(section_na.keys()))

    nums = sorted(int(r[0].split('-')[1]) for r in req_src
                  if re.match(r'REQ-\d+$', r[0]))
    num_gap = [n for n in range(nums[0], nums[-1] + 1) if n not in nums] if nums else []
    num_dup = [n for n, cnt in collections.Counter(nums).items() if cnt > 1]

    field_bad = []
    for r in req_src:
        for idx, nm, ok in ((2, '来源文档', None), (3, '来源章节', None),
                            (4, '类型', TYPE_OK), (5, '可测性', MEASURABLE_OK),
                            (6, '覆盖状态', COVER_STATUS_OK)):
            v = (r[idx] or '').strip()
            if not v:
                field_bad.append('%s:%s空' % (r[0], nm))
            elif ok and v not in ok:
                field_bad.append('%s:%s非法' % (r[0], nm))
        # 安全类必须标子域：「功能安全」含「功能」二字，不标子域会被误判为功能类 REQ
        if r[4] == '安全' and not any(k in (r[7] or '') for k in ('信息安全', '功能安全')):
            field_bad.append('%s:安全类未标子域' % r[0])
    denom_ok = (sum(1 for r in req_src if r[5] == '可测') +
                sum(1 for r in req_src if r[5] == '不可测') == len(req_src))
    req_struct_bad = (len(sec_gap) + len(num_gap) + len(num_dup) +
                      len(field_bad) + (0 if denom_ok else 1))

    # ---- 门禁：功能安全覆盖（触发+恢复，多触发源，预期三要素）----
    fs_req = [r[0] for r in req_src
              if r[4] == '安全' and '功能安全' in (r[7] or '') and r[5] == '可测']
    fs_cov = collections.defaultdict(set)
    for c in CS:
        fs_cov[c['req']].add(c['cover'])
    fs_depth_bad = [r for r in fs_req if not (
        any('触发' in x for x in fs_cov[r]) and
        any('恢复' in x for x in fs_cov[r]))]
    fs_src_have = {k: sum(1 for c in CS if c['req'] in fs_req
                          and '功能安全-触发' in c['cover'] and k in c['data'])
                   for k in srcmap}
    # 多触发源要求只在「本期确有功能安全 REQ」时才成立。fs_req 为空时若照算，
    # 三个触发源计数全为 0 → fs_src_bad 填满 → 门禁恒不通过，任何没有功能安全
    # 需求的项目（如纯软件工具类）都永远过不了这一项，属误报。
    # 注意：这不等于放过「该测功能安全却整个维度标了 N/A」——那种情况由
    # SKILL.md 硬门禁 16 要求回查 Phase 1.2 的 F 组提问确认，不靠本项拦。
    fs_src_bad = ([srcmap[k] for k, v in fs_src_have.items() if v == 0]
                  if fs_req else [])
    fs_elem_bad = []
    for c in CS:
        if '功能安全-触发' in c['cover']:
            txt = ' '.join(c['exp'])
            if not (('停止时限' in txt or 'ms' in txt)
                    and ('上报' in txt or '状态' in txt)
                    and ('恢复' in txt or '拒绝' in txt or '保持' in txt)):
                fs_elem_bad.append(c['tc'])

    # ---- 门禁：通用异常交叉（仅本期纳入 EX 时校验）----
    ex_inc = list(getattr(ex, 'EX_INCLUDED', []) or []) if ex else []
    ex_library = list(getattr(ex, 'EX_LIBRARY', []) or []) if ex else []
    ex_body_tp = getattr(ex, 'EX_BODY_TP', {}) if ex else {}
    ex_rows = list(getattr(ex, 'EX_MATRIX_ROWS', []) or []) if ex else []
    all_tp = set(c['tp'] for c in CS)
    ex_no_body = [e for e in ex_inc
                  if not any(tp in all_tp for tp in ex_body_tp.get(e, []))]
    ex_cell_unrated = ['%s x %s' % (r[0], r[2]) for r in ex_rows
                       if r[4] not in STATUS_OK]
    ex_no_basis = ['%s x %s' % (r[0], r[2]) for r in ex_rows
                   if not (r[5] or '').strip() or any(w in r[5] for w in WEAK_BASIS)]
    all_tc = set(c['tc'] for c in CS)
    ex_must_gap = ['%s x %s' % (r[0], r[2]) for r in ex_rows
                   if r[4] == '必测' and (r[8] == '-' or r[8] not in all_tc)]
    ref_ex = set(r[3] for r in req_src if r[2] == '异常注入库')
    ex_ref_bad = sorted(ref_ex - set(ex_library))
    ex_cross = [c['tc'] for c in CS
                if c['tc'].startswith('TC-EX-') and '交叉基线' in c['remark']]

    # ---- 优先级分布：功能安全类（TP-SEC-101~199）不计入 P0 约 10% 的分布约束 ----
    def is_fs(c):
        m = re.match(r'TP-SEC-(\d+)$', c['tp'])
        return bool(m) and 101 <= int(m.group(1)) <= 199

    fs_cases = [c['tc'] for c in CS if is_fs(c)]
    nonfs = [c for c in CS if not is_fs(c)]
    pri_nonfs = {p: sum(c['pri'] == p for c in nonfs) for p in ('P0', 'P1', 'P2', 'P3')}

    return dict(
        testable=testable, blocked=blocked_req, na=na_req, uncovered=uncovered,
        depth_bad=depth_bad, func_reqs=sorted(func),
        collapse_tp=collapse_tp, collapse_req=collapse_req, tp_no_tc=tp_no_tc,
        step_bad=step_bad, ready=ready, blk=blk, draft=draft, pri=pri, tot=tot,
        spec_ok=spec_ok, spec_reqs=sorted(spec_reqs),
        spec_companion=sorted(companion), spec_companion_bad=spec_companion_bad,
        pri_incons=pri_incons,
        title_meta_bad=title_meta_bad, cover_bad=cover_bad, tech_warn=tech_warn,
        dim_bad=dim_bad, sec_gap=sec_gap, num_gap=num_gap, num_dup=num_dup,
        field_bad=field_bad, denom_ok=denom_ok, req_struct_bad=req_struct_bad,
        doc_sec_total=len(doc_secs), section_na_total=len(section_na),
        tp_degenerate=tp_degenerate, fs_req=fs_req, fs_depth_bad=fs_depth_bad, fs_src_have=fs_src_have,
        fs_src_bad=fs_src_bad, fs_elem_bad=fs_elem_bad,
        ex_inc=ex_inc, ex_library=ex_library, ex_no_body=ex_no_body,
        ex_cell_unrated=ex_cell_unrated, ex_no_basis=ex_no_basis,
        ex_must_gap=ex_must_gap, ex_ref_bad=ex_ref_bad, ex_cross=ex_cross,
        fs_cases=fs_cases, pri_nonfs=pri_nonfs, nonfs=len(nonfs),
    )


def gate_notes(a):
    """每个硬门禁项的说明，全部由数据派生，不写死项目专有字符串。"""
    def ids(key, head=3):
        v = a[key]
        return '、'.join(str(x) for x in v[:head]) + ('…' if len(v) > head else '')

    return {
        '未覆盖REQ=0': '分母=可测∧非阻塞REQ %d条' % len(a['testable'])
                      + ('' if not a['uncovered'] else ';违例:' + ids('uncovered')),
        '深度未达标=0': '功能REQ %d条,须各自含正向类+非正向类' % len(a['func_reqs'])
                       + ('' if not a['depth_bad'] else ';违例:' + ids('depth_bad')),
        '一对多坍缩=0且TP无专属TC=0': 'TC→TP与TC→REQ映射均无size>1,且每TP≥1条专属TC',
        '反模式(步骤预期错位)=0': 'dsl.C() 构建期assert已强制步骤:预期=1:1,此处二次复核',
        '专项REQ配套功能用例齐全':
            ('被专项覆盖的REQ(%s)均含功能可用性用例' % (ids('spec_companion', 8) or '本期无')
             if a['spec_ok'] else '缺配套:' + ids('spec_companion_bad')),
        'TP维度与用例维度错配=0': '遍历TC比对(测试类型→维度)与(TP前缀→维度)',
        '标题写验证方法数=0':
            '正则查「手段介词+元动词收尾」(如「…由再次点击验证」);标题须写场景+预期'
            + ('' if not a['title_meta_bad'] else ';违例:' + ids('title_meta_bad')),
        '覆盖类型与测试类型矛盾数=0':
            '专用型测试类型(反向/边界/异常/性能/稳定性/兼容性)各绑定唯一覆盖类型,遍历比对'
            + ('' if not a['cover_bad'] else ';违例:' + ids('cover_bad')),
        'REQ清单结构性完整':
            '章节反查差集(文档章节全集%d−已引用−已标N/A %d)/编号连续/字段枚举/分母自洽 四项'
            % (a['doc_sec_total'], a['section_na_total']),
        '功能安全深度达标(触发+恢复,多触发源)':
            ('功能安全REQ(%s)含触发+恢复;各触发源%s;预期含停止时限+状态上报+恢复行为'
             % (('、'.join(a['fs_req']) or '本期无'),
                ','.join('%s=%d' % (k, v) for k, v in a['fs_src_have'].items()))),
        'EX交叉五项全通过':
            '本体用例/未评估格/缺依据/必测缺口/EX-ID非法 均为0;标"不适用"且依据充分的格不计缺口',
        '优先级与风险一致': '高↔P0/P1,中↔P2,低↔P3',
    }


def gates(a):
    """硬门禁逐项判定，顺序与审计报告「硬门禁」分区、门禁饼图口径一致。"""
    return [
        ('未覆盖REQ=0', not a['uncovered']),
        ('深度未达标=0', not a['depth_bad']),
        ('一对多坍缩=0且TP无专属TC=0',
         not (a['collapse_tp'] or a['collapse_req'] or a['tp_no_tc'])),
        ('反模式(步骤预期错位)=0', not a['step_bad']),
        ('专项REQ配套功能用例齐全', a['spec_ok']),
        ('TP维度与用例维度错配=0', not a['dim_bad']),
        ('标题写验证方法数=0', not a['title_meta_bad']),
        ('覆盖类型与测试类型矛盾数=0', not a['cover_bad']),
        ('REQ清单结构性完整', a['req_struct_bad'] == 0),
        ('测试点未1:1退化', not a['tp_degenerate']),
        ('功能安全深度达标(触发+恢复,多触发源)',
         not (a['fs_depth_bad'] or a['fs_src_bad'] or a['fs_elem_bad'])),
        ('EX交叉五项全通过',
         not (a['ex_no_body'] or a['ex_cell_unrated'] or a['ex_no_basis']
              or a['ex_must_gap'] or a['ex_ref_bad'])),
        ('优先级与风险一致', not a['pri_incons']),
    ]
