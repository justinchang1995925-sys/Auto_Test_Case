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

from .dsl import COVER_OK, PRI_RISK, TT2DIM, TTYPE_OK, tp_dim

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
# 原实现是 {'反向测试':'反向','边界测试':'边界','异常测试':'异常'} 的绑定表。
# ttype 归正为只收六维度后，那三个键**再也不会出现**，该门禁会恒为空——
# 不是「通过」，是「没东西可查」。故换成跨维度矛盾判据，保住「防两列自相矛盾」的原意。
#
# 判据：功能维度的用例（ttype→功能）其 cover 必须是功能视角或功能安全；
#      跨维度的用例（性能/稳定性/兼容性/安全/用户体验测试）不得填 `正向/主流程`
#      ——那是功能视角的说法，跨维度用例的 cover 应是其维度名或异常/反向/边界。
# 为什么跨维度可以填异常/反向/边界：exception-library.md 明文规定 EX 交叉用例
# 后果为「数据不一致」时归稳定性维度、ttype 填 `稳定性测试`、cover 用 `异常`。
# 视角类 cover：与维度无关，任何维度都能用（正常路径/反向/边界/异常都是设计角度）。
# **不要把「正向」当成功能维度专属**——「用户体验测试 + 正向」是合理写法
# （正常操作路径下的体验），首版判据写成「跨维度不得填正向」拦到了 5 条合规用例，
# 属误报。误报的检查很快就没人看，反过来削弱其他门禁。
PERSPECTIVE_COVER = ('正向', '主流程', '反向', '边界', '异常',
                     '功能安全-触发', '功能安全-恢复', '专项')
# 维度名类 cover：填了它就等于声明「本用例属该维度」，必须与 ttype 推出的维度一致。
DIM_COVER = ('性能', '稳定性', '兼容性', '安全', '用户体验', '功能')

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



# 门禁 19：资源观测最低必采项。缺任一项即判不通过。
# 取值依据实测（RK3588/PREEMPT_RT）：实时线程核占用须取最大值而非均值（控制环被挤是
# 单核事件，均值会摊平）；隔离核正常恒 0，被侵占是最灵敏的告警位；无 swap 的产品
# 承诺量超配后触发即 OOM，故 committed 与 oom_kill 必采。
RES_CPU_MIN = ('cpu_all', 'cpu_rt_max', 'temp', 'freq')
RES_MEM_MIN = ('mem_avail', 'anon', 'committed', 'slab_unreclaim',
               'pagetables', 'oom_kill')
RES_VERDICT_KINDS = ('瞬时', '趋势', '状态')


def degenerate_tps(cases, tp_name_map=None):
    """1:1 退化的 TP 清单（空 = 无退化）。

    未给正式名称时测试点描述**按定义**就是首条用例标题（drawio.derive 的默认派生），
    因此「唯一用例 + 未给名称」即同文退化；给了名称说明已做抽象，不算。

    **做成共享函数**：项目侧自建审计时要算同一个门禁，抄一份就会与 skill 分叉。
    实测咖啡项目的手写门禁清单里根本没有这一项——上游加了退化门禁，
    该项目**从未生效过**，直到调 gates() 时因缺键报 KeyError 才暴露。
    """
    import collections as _c
    tp_titles = _c.defaultdict(list)
    for c in cases:
        tp_titles[c['tp']].append(c['tc'])
    return sorted(tp for tp, lst in tp_titles.items()
                  if len(lst) == 1 and not (tp_name_map or {}).get(tp))


def duplicate_candidates(cases):
    """疑似重复用例的分组清单（空 = 无重复）。**软提示，不阻断**。

    判据取「操作步骤序列 + 预期结果序列**逐条完全相同**」——两条用例连怎么做、
    期望什么都一字不差，那它们测的就是同一件事，哪怕挂在不同 REQ/TP 下。
    只比步骤与预期、不比标题：标题可以措辞不同而实质相同（实测正是这种）。

    为什么必然会有人踩：**深度门禁要求某 REQ 补某方向覆盖时，最省事的做法就是
    复制邻近用例改个 REQ 号交差**。实测踩过：为给 REQ-012（讲「不符时报错」）
    补正向面，复制了 REQ-010 的「版本一致判 PASS」——而「版本一致」本就是
    REQ-010 的地盘，REQ-012 的正向面应是「报错内容本身完整正确」。
    两条用例前置/步骤/预期一字不差，评审时看不出为什么要跑两遍。

    **只作软提示**：确实存在「步骤相同但测试数据不同」的合规写法（同一操作换参数），
    此时 steps/exp 可能雷同而 data 不同。用来阻断会误报，
    而会误报的检查很快就没人看了（见 pipeline.md 对 text_cells 的同类判断）。
    返回 [[tc, ...], ...]，每组为一批互为重复的 TC，供人工判断该删哪条或改写。
    """
    import collections as _c
    buckets = _c.defaultdict(list)
    for c in cases:
        key = (tuple(x.strip() for x in c['steps']),
               tuple(x.strip() for x in c['exp']))
        buckets[key].append(c['tc'])
    return sorted([sorted(v) for v in buckets.values() if len(v) > 1])


def cover_conflicts(cases):
    """覆盖类型 ↔ 测试类型 跨维度矛盾的 TC 清单（空 = 无矛盾）。

    抓的是「改了一个字段忘改另一个」——两列自相矛盾时导图、附表、矩阵各说一套。

    **做成共享函数而非留在 compute 里**：项目侧要在自己的审计里算同一个门禁
    （实测咖啡项目就把这段表达式抄了一份）。抄一份的后果是 skill 改判据后
    项目侧照旧跑老逻辑，两处判定分叉——这正是本 skill 反复警告的。
    """
    bad = []
    for c in cases:
        cov = c['cover']
        if cov in PERSPECTIVE_COVER:
            continue                    # 视角类与维度无关，任何维度都能用
        if cov in DIM_COVER and cov != TT2DIM.get(c['ttype'], '?'):
            bad.append(c['tc'])         # 声明了别的维度，与 ttype 自相矛盾
    return bad


def enum_violations(cases):
    """(ttype 非法的 TC, cover 非法的 TC)。同样供项目侧复用，不要各写一份。"""
    return ([c['tc'] for c in cases if c['ttype'] not in TTYPE_OK],
            [c['tc'] for c in cases if c['cover'] not in COVER_OK])


def _spec_tcs(cases, spec):
    """本期全部专项用例号。**两个来源都要看**：

    专项用例走 spec 两表，**不在 dsl.CASES 里**；早先只扫 cases，样例项目明明有
    TC-SP-PERF-001 却判「无专项」，门禁 19 以错误理由通过、等于从未生效（踩过）。
    仍保留扫 cases 的分支：有些项目把专项用例也塞进 CASES 以便进追溯矩阵。
    """
    out = {str(c.get('tc', '')) for c in cases
           if str(c.get('tc', '')).startswith('TC-SP-')}
    for row in ((spec or {}).get('rows') or ()):
        # 专项主表首列固定是用例序号
        first = str(row[0]) if len(row) else ''
        if first.startswith('TC-SP-'):
            out.add(first)
    return out


def _res_gate(cases, res, spec=None):
    """门禁 19 的八项核对，返回违例说明列表（空 = 通过）。

    只有本期确实存在专项用例（TC-SP-*）时才要求资源观测——没有专项测试的项目
    （如纯 Web 功能测试）不受此门禁约束。
    """
    spec_tcs = _spec_tcs(cases, spec)
    if not spec_tcs:
        return []
    if not res:
        return ['本期有专项用例但未提供资源观测项（门禁 19 要求 TC-SP-RES-xxx）']

    bad = []
    tc = str(res.get('tc') or '')
    if not tc.startswith('TC-SP-RES'):
        bad.append('资源观测用例编号缺失或不合规（须 TC-SP-RES-xxx，收到 %r）' % tc)
    if not res.get('req') or not res.get('tp'):
        bad.append('资源观测项缺自己的 REQ 或 TP')
    attached = list(res.get('attached') or ())
    if not attached:
        bad.append('未写明依附的专项用例编号（前置条件须显式依赖）')
    else:
        # 依附对象必须是真实存在的专项用例，否则填个不存在的号也能过
        ghost = [t for t in attached if t not in spec_tcs and t != tc]
        if ghost:
            bad.append('依附的专项用例不存在: %s（本期专项用例: %s）'
                       % (','.join(ghost),
                          ','.join(sorted(spec_tcs - {tc})) or '无'))

    miss_cpu = [k for k in RES_CPU_MIN if k not in set(res.get('cpu_keys') or ())]
    miss_mem = [k for k in RES_MEM_MIN if k not in set(res.get('mem_keys') or ())]
    if miss_cpu:
        bad.append('CPU 最低必采项缺失: %s' % ','.join(miss_cpu))
    if miss_mem:
        bad.append('内存最低必采项缺失: %s' % ','.join(miss_mem))

    miss_kind = [k for k in RES_VERDICT_KINDS
                 if k not in set(res.get('verdict_kinds') or ())]
    if miss_kind:
        bad.append('判定口径缺失: %s（三类须齐）' % ','.join(miss_kind))

    if not res.get('threshold_sources'):
        bad.append('未写明阈值来源（须读 sched_rt_*/trip_point_0_temp//proc/meminfo）')
    if res.get('hardcoded_thresholds'):
        bad.append('阈值硬编码: %s（须写来源与口径，不写死数值）'
                   % ','.join(map(str, res['hardcoded_thresholds'])))
    # 结论：允许「已定义但未执行」这个合法状态，但必须显式标 Blocked + 写解除条件。
    # 不留这条路，交付阶段（用例刚定义、尚未跑 100 杯）就只能填一个假的 PASS/WARN
    # 去骗过门禁 —— 那正是本 skill 定义的门禁造假。执行后再改成实测结论。
    concl = str(res.get('conclusion') or '').upper()
    if concl == 'BLOCKED':
        if not res.get('unblock'):
            bad.append('资源判定结论标 Blocked 但未写解除条件'
                       '（须写明何时可出结论，如「TC-SP-STAB-001 执行完毕后」）')
    elif concl not in ('PASS', 'WARN', 'FAIL'):
        bad.append('资源判定结论缺失（只采不判视为未完成；'
                   '尚未执行请标 Blocked 并写解除条件，不要填假结论）')
    if not res.get('agent_cost'):
        bad.append('未自证采集器扰动（须含采集器自身 CPU/RSS/fork 证据）')
    if res.get('mixed_into'):
        bad.append('资源指标混入既有专项用例判定标准: %s（违反一案一验）'
                   % ','.join(res['mixed_into']))
    return bad


def compute(cases, req_src, ex=None, spec_reqs=frozenset(), fs_source_map=None,
            spec_companion_reqs=None, tp_name_map=None, res=None, spec=None):
    """返回全部门禁数与违例清单。

    cases    : dsl.add 收集的用例列表
    req_src  : REQ 清单行，字段序 (id, 描述, 来源文档, 章节, 类型, 可测性, 覆盖状态, 备注)
    ex       : 异常交叉矩阵模块（可为 None，表示本期无 EX 纳入）
    spec_reqs: 仅由专项用例覆盖的 REQ。它们不在普通用例里，故计入覆盖集、
               且不参与功能深度判定（另走专项配套规则）。
    spec_companion_reqs: 被专项测试覆盖的 REQ 全集，即须校验「专项+配套功能用例」的集合。
               通常 ⊇ spec_reqs——有些 REQ 既有普通功能用例、又被专项覆盖（如成功率类），
               它们要参与功能深度判定，但同样须有配套功能用例。默认取 spec_reqs。
    res      : 资源观测交付信息（门禁 19）。None 表示项目未提供，若本期有专项用例则判缺失。
               形如 dict(tc='TC-SP-RES-001', req='REQ-0NN', tp='TP-S-0NN',
                        attached=['TC-SP-STAB-001'], cpu_keys=[...], mem_keys=[...],
                        verdict_kinds=['瞬时','趋势','状态'], threshold_sources=[...],
                        hardcoded_thresholds=[...],
                        conclusion='PASS/WARN/FAIL/Blocked',
                        unblock='...',   # conclusion=Blocked 时必填
                        agent_cost='...', mixed_into=[...])
    """
    CS = cases
    tp_name_map = tp_name_map or {}
    spec_reqs = set(spec_reqs)
    companion = set(spec_companion_reqs) if spec_companion_reqs else set(spec_reqs)
    srcmap = fs_source_map or FS_SOURCES
    res_req = (res or {}).get('req')

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

    # ---- 门禁：需求编号分组完整（顶层节点数 = 纳入需求数）----
    # 只在 REQ 清单带「需求编号」（索引 8）时生效——即需求文档自带编号体系、
    # 思维导图按需求编号分组的场景。
    #
    # 存在理由：按需求编号分组时，导图顶层节点数应当等于纳入的需求数，
    # 数一下就知道有没有漏。实测踩过：文档 12 项打钩需求，导图只出 8 项，
    # 靠用户手工数才发现整条 F07 没进 REQ 清单。
    # **既有的「未覆盖 REQ」门禁抓不到这种漏**：它比对的是「REQ 清单 vs 追溯矩阵」，
    # 而 F07 从没进过 REQ 清单，比对的两边都缺它，差集自然为空。
    # 本门禁把「需求编号」作为第三方基准，专抓「整条需求没进清单」这一类。
    #
    # 注意本门禁只能校验「已进 REQ 清单的需求编号是否都有用例」。
    # 「文档里有但 REQ 清单里完全没有的需求编号」它同样看不见——那一层由
    # SKILL.md Phase 1.5「需求全集必须逐行核对」的人工回报兜住（放行条件 B2）。
    # 两者互补：本门禁守「进了清单却没落用例」，B2 守「压根没进清单」。
    fno_of = {r[0]: (r[8] or '').strip()
              for r in req_src if len(r) > 8 and (r[8] or '').strip()}
    fno_scope = sorted(set(fno_of[r[0]] for r in req_src
                           if r[0] in fno_of and r[5] == '可测' and r[6] != '阻塞'))
    fno_covered = set()
    for c in CS:
        f = fno_of.get(c['req'])
        if f:
            fno_covered.add(f)
    fno_covered |= set(fno_of[r] for r in spec_reqs if r in fno_of)
    fno_no_case = [f for f in fno_scope if f not in fno_covered]

    # ---- 门禁：测试点 1:1 退化（测试点层没做抽象，只是复读用例标题）----
    # 坍缩的对称反面：坍缩是「多 TP 挤进一条 TC」，退化是「每个 TP 只挂一条 TC 且
    # 描述与该用例标题同文」。它不违反坍缩/深度/追溯任何一条，却让测试点层完全失去
    # 信息量——思维导图里用例节点会因去重显示「同测试点主场景」，评审看不出测了哪些方面。
    # 判据取「唯一用例 且 标题与 TP 描述同文」：只看数量比会把「该测试点确实只需一条用例」
    # 的合规情形也算进来（如某些一次性校验项），必须叠加同文条件才不误报。
    # 判定见 degenerate_tps（抽成共享函数供项目侧复用，不在各处抄一份）
    tp_degenerate = degenerate_tps(CS, tp_name_map)
    # 供 gate_notes 报口径：TP 全集与其中已给正式名称的个数。
    tp_all = sorted({c['tp'] for c in CS})
    tp_named_n = sum(1 for tp in tp_all if (tp_name_map or {}).get(tp))

    # ---- 反模式：步骤与预期条数错位（构建期 assert 已挡，此处二次复核）----
    step_bad = [c['tc'] for c in CS if len(c['steps']) != len(c['exp'])]

    # ---- 状态与优先级 ----
    ready = sum(c['status'] == 'Ready' for c in CS)
    blk = sum(c['status'] == 'Blocked' for c in CS)
    draft = sum(c['status'] == 'Draft' for c in CS)
    pri = {p: sum(c['pri'] == p for c in CS) for p in ('P0', 'P1', 'P2', 'P3')}
    tot = len(CS)

    # 专项 REQ 须同时有专项用例与功能可用性用例（只验功能走通，不判指标）
    # 窄豁免：资源观测 REQ（res_req）无独立业务功能可验——「采集器能取到一次样本」
    # 属工具自检而非被测产品功能，硬补一条即凑数（SKILL.md 4.1 明禁）。
    # 豁免只对这一条 REQ 生效，理由随审计输出，防止悄悄扩大到其它专项 REQ。
    spec_companion_bad = [r for r in sorted(companion)
                          if r != res_req
                          and not any(c['req'] == r and c['ttype'] == '功能测试'
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

    # ---- 门禁 B0：ttype / cover 必须在合法枚举内（分类轴不许混填）----
    # dsl.C() 已在构建期拦一次，但项目可能自带 C()（实测咖啡项目就是），
    # 那条 assert 绕不到，故此处兜底。两层都要。
    ttype_bad, cover_enum_bad = enum_violations(CS)

    # ---- 门禁 B：覆盖类型 ↔ 测试类型 跨维度矛盾（判定见 cover_conflicts）----
    cover_bad = cover_conflicts(CS)

    # ---- 软提示 C：设计技法 ↔ 测试类型 相容性（列出待人工确认，不阻断）----
    # 技法决定了用例在测什么，与测试类型应当相容；但边界情形确实存在
    # （如状态迁移技法配边界测试），故只提示不阻断，避免误报稀释硬门禁可信度。
    # 软提示：疑似重复用例（步骤+预期逐条相同），不进 gates()
    dup_cand = duplicate_candidates(CS)

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

    res_bad = _res_gate(CS, res, spec)

    return dict(
        res=res or {}, res_bad=res_bad, res_ok=not res_bad,
        res_exempt=res_req,
        testable=testable, blocked=blocked_req, na=na_req, uncovered=uncovered,
        depth_bad=depth_bad, func_reqs=sorted(func),
        collapse_tp=collapse_tp, collapse_req=collapse_req, tp_no_tc=tp_no_tc,
        step_bad=step_bad, ready=ready, blk=blk, draft=draft, pri=pri, tot=tot,
        spec_ok=spec_ok, spec_reqs=sorted(spec_reqs),
        spec_companion=sorted(companion), spec_companion_bad=spec_companion_bad,
        pri_incons=pri_incons,
        title_meta_bad=title_meta_bad, cover_bad=cover_bad,
        ttype_bad=ttype_bad, cover_enum_bad=cover_enum_bad, tech_warn=tech_warn,
        dup_cand=dup_cand,
        dim_bad=dim_bad, sec_gap=sec_gap, num_gap=num_gap, num_dup=num_dup,
        field_bad=field_bad, denom_ok=denom_ok, req_struct_bad=req_struct_bad,
        doc_sec_total=len(doc_secs), section_na_total=len(section_na),
        tp_degenerate=tp_degenerate, tp_all=tp_all, tp_named_n=tp_named_n,
        fno_scope=fno_scope,
        fno_no_case=fno_no_case, fs_req=fs_req, fs_depth_bad=fs_depth_bad, fs_src_have=fs_src_have,
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
             + ('' if not a['res_exempt'] else
                ';%s(资源观测)按门禁19豁免:无独立业务功能可验,补一条即凑数'
                % a['res_exempt'])
             if a['spec_ok'] else '缺配套:' + ids('spec_companion_bad')),
        '资源观测覆盖达标(有专项即强制)':
            # 结论为 Blocked 时必须带上解除条件：只写「Blocked」等于挂起无期限，
            # 报告读者看不出何时能出结论。
            ('专项运行期同步采CPU/内存(%s依附%s),三类判定齐,阈值读机器,结论%s%s'
             % (a['res'].get('tc', '-'),
                '/'.join(a['res'].get('attached') or ['-']),
                a['res'].get('conclusion', '-'),
                ('(解除条件:%s)' % a['res']['unblock'])
                if str(a['res'].get('conclusion', '')).upper() == 'BLOCKED'
                and a['res'].get('unblock') else '')
             if a['res_ok'] and a['res'] else
             ('本期无专项用例,该门禁不适用' if a['res_ok']
              else '违例:' + ';'.join(a['res_bad']))),
        'TP维度与用例维度错配=0': '遍历TC比对(测试类型→维度)与(TP前缀→维度)',
        '标题写验证方法数=0':
            '正则查「手段介词+元动词收尾」(如「…由再次点击验证」);标题须写场景+预期'
            + ('' if not a['title_meta_bad'] else ';违例:' + ids('title_meta_bad')),
        '测试类型与覆盖类型枚举合法':
            ('测试类型只收六维度(反向/边界/异常属覆盖类型,不是测试类型);'
             '覆盖类型在合法枚举内'
             if not (a['ttype_bad'] or a['cover_enum_bad']) else
             '违例 测试类型:%s 覆盖类型:%s'
             % (ids('ttype_bad') or '无', ids('cover_enum_bad') or '无')),
        '覆盖类型与测试类型矛盾数=0':
            '判据:覆盖类型填了维度名(性能/稳定性/兼容性/安全/用户体验/功能)时,'
            '须与测试类型推出的维度一致;视角类(正向/反向/边界/异常/功能安全/专项)与维度无关,不约束'
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
        '测试点未1:1退化':
            '唯一用例且未给正式名称=退化(未给名称时TP描述按定义即首条用例标题);'
            'TP共%d个,其中%d个已给名称' % (len(a['tp_all']), a['tp_named_n'])
            + ('' if not a['tp_degenerate'] else ';违例:' + ids('tp_degenerate')),
        '需求编号分组完整(顶层节点数=需求数)':
            ('本期REQ清单未带需求编号,该门禁不适用'
             if not a['fno_scope'] else
             '纳入需求编号%d项(%s),每项须至少落1条用例;'
             '本门禁守「进了REQ清单却没落用例」,'
             '「压根没进清单」由Phase1.5人工逐行核对兜(放行条件B2)'
             % (len(a['fno_scope']), '、'.join(a['fno_scope'][:8])
                + ('…' if len(a['fno_scope']) > 8 else ''))
             + ('' if not a['fno_no_case'] else ';违例:' + ids('fno_no_case'))),
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
        ('测试类型与覆盖类型枚举合法',
         not (a['ttype_bad'] or a['cover_enum_bad'])),
        ('覆盖类型与测试类型矛盾数=0', not a['cover_bad']),
        ('REQ清单结构性完整', a['req_struct_bad'] == 0),
        ('测试点未1:1退化', not a['tp_degenerate']),
        # 需求编号分组完整：REQ 清单未带需求编号时该门禁不适用，恒判通过
        # （fno_scope 为空 → fno_no_case 必空），不给无编号体系的项目添恒误报。
        ('需求编号分组完整(顶层节点数=需求数)', not a['fno_no_case']),
        ('功能安全深度达标(触发+恢复,多触发源)',
         not (a['fs_depth_bad'] or a['fs_src_bad'] or a['fs_elem_bad'])),
        ('EX交叉五项全通过',
         not (a['ex_no_body'] or a['ex_cell_unrated'] or a['ex_no_basis']
              or a['ex_must_gap'] or a['ex_ref_bad'])),
        ('资源观测覆盖达标(有专项即强制)', a['res_ok']),
        ('优先级与风险一致', not a['pri_incons']),
    ]
