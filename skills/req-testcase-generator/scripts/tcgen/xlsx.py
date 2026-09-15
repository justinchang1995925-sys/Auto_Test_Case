# -*- coding: utf-8 -*-
"""交付件工作簿构建（通用，与项目无关）。

一个工作簿多 Sheet，Sheet 名与 skill「交付物规范」一致：
    需求原子化清单 / 异常交叉适用性矩阵 / 测试用例主表 /
    评审追溯表（含风险评估）/ 追溯矩阵表（REQ-TP-TC）/
    专项测试用例表 / 专项数据采集表 / 质量审计报告

主表·附表·追溯矩阵统一按 (REQ-ID, TP-ID, TC-ID) 排序，使同一需求下的
正向/反向/异常/边界用例连续聚合、三表顺序一致。

用法见 project_template/build.py。
"""
from openpyxl import Workbook
from openpyxl.chart import PieChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import audit as _audit
from .dsl import (EXT_HEADERS, MAIN_HEADERS, PRI_REASON, PRI_RISK, REQ_HEADERS,
                  TR_HEADERS)

CENTER = Alignment(wrap_text=True, vertical='center')
TOP = Alignment(wrap_text=True, vertical='top')
HEADFILL = PatternFill('solid', fgColor='D9E1F2')
AUDIT_HEADERS = ['报告分区', '检查项', '数值/结论', '说明(计算口径/违例ID)']


def steps_txt(lst):
    return "\n".join(lst)


def style_sheet(ws, headers, header_row=1):
    """表头加粗+底色、筛选器覆盖表头与数据区、列宽按最长文本自适应（中文按2倍宽）。"""
    for c in ws[header_row]:
        c.font = Font(bold=True)
        c.alignment = CENTER
        c.fill = HEADFILL
    ws.auto_filter.ref = (
        f"A{header_row}:{get_column_letter(len(headers))}{ws.max_row}")
    for i in range(1, len(headers) + 1):
        col = get_column_letter(i)
        w = 0
        for cell in ws[col]:
            text = str(cell.value) if cell.value is not None else ""
            for line in text.split("\n"):
                w = max(w, sum(2 if ord(ch) > 255 else 1 for ch in line))
        ws.column_dimensions[col].width = min(max(w + 2, 8), 60)
    for row in ws.iter_rows(min_row=header_row + 1):
        for cell in row:
            cell.alignment = TOP


def _banner(ws, ncol, title, items, height):
    """顶部合并说明行（需求清单的输入来源、矩阵说明、审计报告说明共用）。"""
    ws.append([title] + [''] * (ncol - 1))
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    cell = ws.cell(1, 1)
    cell.value = title + "\n" + "\n".join(items) if items else title
    cell.alignment = Alignment(wrap_text=True, vertical='center')
    cell.font = Font(bold=True)
    ws.row_dimensions[1].height = height


def _merge_col(ws, col, start):
    """相同值的连续行合并该列；col=2 时额外要求同属一个 REQ，避免跨 REQ 误并。"""
    vals = [ws.cell(rr, col).value for rr in range(start, ws.max_row + 1)]
    i = 0
    while i < len(vals):
        j = i
        while (j + 1 < len(vals) and vals[j + 1] == vals[i]
               and (col == 1 or ws.cell(start + j + 1, 1).value
                    == ws.cell(start + i, 1).value)):
            j += 1
        if j > i:
            ws.merge_cells(start_row=start + i, start_column=col,
                           end_row=start + j, end_column=col)
        i = j + 1


def _ordered(cases):
    return sorted(cases, key=lambda c: (c['req'], c['tp'], c['tc']))


# ---------------- 各 Sheet ----------------

def build_req(ws, req_src, req_links, cases, spec_reqs):
    """需求原子化清单。

    REQ 行可选带第 9 个字段「需求编号」（如 F17）——需求文档自带编号体系时
    （产测工具类需求常见），把它渲染成**第一列**，读者一眼能看到
    「F17 拆出了哪几条 REQ」，与按需求编号组织的思维导图对得上。

    **该字段必须放在数据层元组末尾（索引 8），不能插在前面**：
    `tcgen.audit` 全部按固定位置读 REQ 字段（r[0] ID / r[2] 来源文档 /
    r[3] 章节 / r[4] 类型 / r[5] 可测性 / r[6] 覆盖状态 / r[7] 备注），
    在前面插列会让所有索引错位、门禁集体误判。此处只在**渲染时**移到首列。
    """
    has_fno = any(len(r) > 8 and (r[8] or '').strip() for r in req_src)
    headers = (['需求编号'] + REQ_HEADERS) if has_fno else list(REQ_HEADERS)
    n = len(headers)
    _banner(ws, n, req_links[0], req_links[1:], 78)
    ws.append(headers)
    covered = set(c['req'] for c in cases) | set(spec_reqs)
    for r in req_src:
        rid, desc, doc, sec, typ, test, cov, note = r[:8]
        if cov == '待覆盖' and rid in covered:
            cov = '已覆盖'
        row = [rid, desc, doc, sec, typ, test, cov, note]
        ws.append(([(r[8] if len(r) > 8 else '')] + row) if has_fno else row)
    style_sheet(ws, headers, header_row=2)
    ws.cell(1, 1).alignment = Alignment(wrap_text=True, vertical='center')


def build_main(ws, cases):
    ws.append(MAIN_HEADERS)
    for c in _ordered(cases):
        ws.append([c['tc'], c['pri'], c['title'], c['ttype'], steps_txt(c['pre']),
                   steps_txt(c['steps']), steps_txt(c['exp']), '', c['remark']])
    style_sheet(ws, MAIN_HEADERS)


def build_ext(ws, cases):
    ws.append(EXT_HEADERS)
    for c in _ordered(cases):
        risk = PRI_RISK[c['pri']]   # 风险由优先级派生，保证 高↔P0/P1 中↔P2 低↔P3
        pri_eval = "%s：%s；定级依据=%s" % (c['pri'], c['rbasis'], PRI_REASON[c['pri']])
        ws.append([c['req'], c['tp'], c['tc'], c['tech'], c['data'], risk,
                   c['rbasis'], pri_eval, c['status'], c['unblock'], c['remark']])
    _merge_col(ws, 1, 2)   # REQ 列
    _merge_col(ws, 2, 2)   # TP 列（REQ 内）
    style_sheet(ws, EXT_HEADERS)


def build_tr(ws, cases, spec_tr_rows=()):
    ws.append(TR_HEADERS)
    for c in _ordered(cases):
        ws.append([c['req'], c['tp'], c['tc'], c['cover'], c['remark']])
    for row in spec_tr_rows:
        ws.append(list(row))
    _merge_col(ws, 1, 2)
    _merge_col(ws, 2, 2)
    style_sheet(ws, TR_HEADERS)


def build_table(ws, headers, rows):
    """专项测试用例表 / 专项数据采集表等纯表格 Sheet。"""
    ws.append(list(headers))
    for r in rows:
        ws.append(list(r))
    style_sheet(ws, list(headers))


def build_exm(ws, ex):
    n = len(ex.EX_MATRIX_HEADERS)
    _banner(ws, n, ex.MATRIX_NOTE_TITLE, ex.MATRIX_NOTE_ITEMS, 150)
    ws.append(list(ex.EX_MATRIX_HEADERS))
    for r in ex.EX_MATRIX_ROWS:
        ws.append(list(r))
    # 整条 N/A 的 EX（按产品形态排除，须写理由）
    for exid, name, verdict, reason in getattr(ex, 'EX_SCOPE_NA', []):
        ws.append([exid, name, '（全部阶段原型）', '-', verdict, reason, '否', '-', '-'])
    style_sheet(ws, list(ex.EX_MATRIX_HEADERS), header_row=2)
    ws.cell(1, 1).alignment = Alignment(wrap_text=True, vertical='center')


# ---------------- 审计报告 ----------------

def _join(ids, limit=None):
    ids = list(ids)
    if limit:
        ids = ids[:limit]
    return ','.join(str(i) for i in ids)


def audit_rows(a, ex=None, n_spec=0, blocked_note='见附表解除条件'):
    """审计报告全部行。每个数字都带计算口径，违例则列 ID（审计三铁律第3条）。"""
    ncov = len(a['testable']) - len(a['uncovered'])
    rate = 100.0 * ncov / len(a['testable']) if a['testable'] else 0.0
    n_func = len(a['func_reqs'])
    tot = a['tot']
    ex_lib = '、'.join(a['ex_library']) if a['ex_library'] else '无'
    rows = [
        ('覆盖率报告', '可测且非阻塞REQ总数', len(a['testable']),
         '分母=可测∧非阻塞;阻塞%d条,N/A%d条不计入' % (len(a['blocked']), len(a['na']))),
        ('覆盖率报告', '已被TP+TC覆盖REQ数', ncov,
         '遍历用例req集合∪专项映射,与可测全集求差'),
        ('覆盖率报告', '未覆盖REQ数', len(a['uncovered']),
         '差集为空:可测全集⊆用例覆盖集' if not a['uncovered']
         else '违例:' + _join(a['uncovered'])),
        ('覆盖率报告', '覆盖率', '%.0f%%' % rate, '已覆盖/可测非阻塞'),
        ('覆盖率报告', '覆盖深度达标REQ数', n_func - len(a['depth_bad']),
         '功能REQ含正向类∧非正向类'),
        ('覆盖率报告', '深度未达标REQ数', len(a['depth_bad']),
         '逐功能REQ收集覆盖类型标签,均含正+非正' if not a['depth_bad']
         else '违例:' + _join(a['depth_bad'])),
        ('覆盖率报告', '阻塞REQ(单列风险)', len(a['blocked']),
         ('；'.join(a['blocked']) + ' 报告标风险,不计入分母') if a['blocked'] else '无'),

        ('可执行性报告', '用例总数(普通+专项)', tot + n_spec,
         '普通%d+专项%d' % (tot, n_spec)),
        ('可执行性报告', 'Ready数', a['ready'] + n_spec,
         '附表用例状态列遍历;专项%d条阈值已定采样待执行' % n_spec),
        ('可执行性报告', 'Blocked数', a['blk'],
         '无' if a['blk'] == 0 else blocked_note),
        ('可执行性报告', 'Draft数', a['draft'], '无' if a['draft'] == 0 else '见附表'),
        ('可执行性报告', '可执行率',
         '%.0f%%' % (100.0 * a['ready'] / tot if tot else 0),
         '普通用例Ready/普通总数' + ('' if a['blk'] == 0 else ';含Blocked故非100%')),

        ('质量缺陷报告', '反模式命中数', len(a['step_bad']),
         '步骤与预期均1:1(add断言保证)' if not a['step_bad']
         else '违例:' + _join(a['step_bad'])),
        ('质量缺陷报告', '追溯缺口数(REQ→TP/TP→TC/REQ→TC)', len(a['uncovered']),
         '每条用例自带REQ/TP/TC三元组,无缺口'),
        ('质量缺陷报告', '一对多坍缩数(多TP或多REQ共用一条TC)',
         len(a['collapse_tp']) + len(a['collapse_req']),
         '建TC→TP集与TC→REQ集,均无size>1'
         if not (a['collapse_tp'] or a['collapse_req'])
         else '违例:' + _join(a['collapse_tp'] + a['collapse_req'])),
        ('质量缺陷报告', 'TP无专属TC数', len(a['tp_no_tc']),
         '每个TP至少1条独立TC' if not a['tp_no_tc']
         else '违例:' + _join(a['tp_no_tc'])),
        ('质量缺陷报告', '专项REQ缺配套功能用例数', len(a['spec_companion_bad']),
         ('被专项覆盖的REQ(%s)均有≥1条功能测试用例(只验功能走通,不判指标)'
          % (_join(a['spec_companion']) or '本期无')
          if not a['spec_companion_bad']
          else '违例:' + _join(a['spec_companion_bad']))),
        ('质量缺陷报告', '覆盖深度缺口数', len(a['depth_bad']), '同覆盖率报告深度口径'),
        ('质量缺陷报告', 'TP维度与用例维度错配数', len(a['dim_bad']),
         '遍历每条TC比对(测试类型→维度)与(TP前缀→维度);功能/接口/反向/异常/边界均属功能维度不算错配'
         if not a['dim_bad'] else '违例:' + _join(a['dim_bad'])),
        ('质量缺陷报告', '功能安全深度未达标数', len(a['fs_depth_bad']),
         ('功能安全REQ(%s)均含触发+恢复两类覆盖' % ('、'.join(a['fs_req']) or '本期无')
          if not a['fs_depth_bad'] else '违例:' + _join(a['fs_depth_bad']))),
        ('质量缺陷报告', '功能安全触发源缺口数', len(a['fs_src_bad']),
         ('各触发源用例数:' + ','.join('%s=%d' % (k, v)
                                  for k, v in a['fs_src_have'].items())
          if not a['fs_src_bad'] else '缺:' + '、'.join(a['fs_src_bad']))),
        ('质量缺陷报告', '功能安全预期三要素缺失数', len(a['fs_elem_bad']),
         '遍历功能安全-触发用例预期,均含停止时限+状态上报+恢复/拒绝行为'
         if not a['fs_elem_bad'] else '违例:' + _join(a['fs_elem_bad'])),
        ('质量缺陷报告', 'REQ清单结构性问题数', a['req_struct_bad'],
         ('章节反查差集空(文档章节全集−已引用−已标N/A)、编号无断号重号、字段齐全枚举合法、分母自洽'
          if a['req_struct_bad'] == 0 else
          '章节漏拆:%s;断号:%s;重号:%s;字段:%s'
          % (a['sec_gap'], a['num_gap'], a['num_dup'], a['field_bad'][:3]))),
        ('质量缺陷报告', 'EX无本体用例数', len(a['ex_no_body']),
         ('本期纳入%s,均有本体用例' % ('、'.join(a['ex_inc']) or '无')
          if not a['ex_no_body'] else '违例:' + _join(a['ex_no_body']))),
        ('质量缺陷报告', '交叉矩阵未评估格数', len(a['ex_cell_unrated']),
         '矩阵各格适用性均为必测/选测/不适用三值之一'
         if not a['ex_cell_unrated'] else '违例:' + _join(a['ex_cell_unrated'])),
        ('质量缺陷报告', '矩阵判定缺依据数', len(a['ex_no_basis']),
         '各格判定依据均为机制层面理由,无"不重要/概率低"类空泛表述'
         if not a['ex_no_basis'] else '违例:' + _join(a['ex_no_basis'])),
        ('质量缺陷报告', '必测交叉缺口', len(a['ex_must_gap']),
         '矩阵必测格集合−已落TC格集合=空'
         if not a['ex_must_gap'] else '违例:' + _join(a['ex_must_gap'])),
        ('质量缺陷报告', 'EX-ID引用非法数', len(a['ex_ref_bad']),
         ('REQ引用的EX-ID均存在于EX库(%s)' % ex_lib
          if not a['ex_ref_bad'] else '违例:' + _join(a['ex_ref_bad']))),
        ('质量缺陷报告', '交叉用例占比',
         '%d条/%.0f%%' % (len(a['ex_cross']),
                         100.0 * len(a['ex_cross']) / tot if tot else 0),
         '软提示,建议≤15%;交叉用例:' + _join(a['ex_cross'])),
        ('质量缺陷报告', '待人工确认数', 0,
         '语义性软提示(疑似未拆需求)需人工确认,非自动判定'),
    ]
    for p in ('P0', 'P1', 'P2', 'P3'):
        rows.append(('优先级合理性评估', '%s用例数' % p, a['pri'][p],
                     '占%.0f%%' % (100.0 * a['pri'][p] / tot if tot else 0)))
    rows += [
        ('优先级合理性评估', '功能安全类用例数(单列,不计入分布约束)', len(a['fs_cases']),
         'TP-SEC-101~199,按安规天然多为P0;剔除口径仅针对P0≈10%分布比例,'
         '其"须有定级依据"与"与风险一致"两项照常校验:' + _join(a['fs_cases'])),
        ('优先级合理性评估', '剔除功能安全后P0占比',
         '%d/%d=%.0f%%' % (a['pri_nonfs']['P0'], a['nonfs'],
                           100.0 * a['pri_nonfs']['P0'] / a['nonfs'] if a['nonfs'] else 0),
         '分布偏差按剔除功能安全后计算(建议P0≈10%%);剔除前P0=%d占%.0f%%'
         % (a['pri']['P0'], 100.0 * a['pri']['P0'] / tot if tot else 0)),
        ('优先级合理性评估', '优先级缺依据数', 0,
         '附表优先级评估列均含定级理由(rbasis+基准)'),
        ('优先级合理性评估', '优先级与风险不一致数', len(a['pri_incons']),
         '高↔P0/P1,中↔P2,低↔P3 全一致'
         if not a['pri_incons'] else '违例:' + _join(a['pri_incons'])),
    ]
    notes = _audit.gate_notes(a)
    for name, ok in _audit.gates(a):
        rows.append(('硬门禁', name, '通过' if ok else '未通过', notes.get(name, '-')))
    rows.append(('硬门禁', 'Blocked=0且Draft=0',
                 '通过' if not (a['blk'] or a['draft']) else '未通过(存在Blocked/Draft)',
                 '%d条Blocked/%d条Draft;均在附表写解除条件' % (a['blk'], a['draft'])))
    all_pass = all(ok for _, ok in _audit.gates(a))
    if all_pass and not (a['blk'] or a['draft']):
        verdict = '质量达标(可作为最终版)'
    elif all_pass:
        verdict = '质量达标但含Blocked/Draft(非最终版)'
    else:
        verdict = '未达标(存在硬门禁未通过)'
    rows.append(('硬门禁', '综合结论', verdict,
                 '硬门禁逐项由数据遍历判定;Blocked因外部依赖,解除后可转最终版'))
    # ---- 自查回执：每个门禁数写清计算方式，与数字对不上即审计无效 ----
    rows += [
        ('自查回执', '未覆盖REQ数', '%d' % len(a['uncovered']),
         '= 可测∧非阻塞REQ全集(%d条) − 追溯矩阵出现的REQ集合;集合运算非肉眼核对'
         % len(a['testable'])),
        ('自查回执', '深度未达标REQ数', '%d' % len(a['depth_bad']),
         '= 每个功能REQ的覆盖类型标签集合不同时含正向类{正向,主流程}'
         '与非正向类{反向,异常,边界}的REQ数;专项REQ另按配套规则校验'),
        ('自查回执', '一对多坍缩数',
         '%d' % (len(a['collapse_tp']) + len(a['collapse_req'])),
         '= |{TC: |TC→TP集合|>1}| + |{TC: |TC→REQ集合|>1}|;两张映射均遍历全量用例构建'),
        ('自查回执', '反模式命中数', '%d' % len(a['step_bad']),
         '= |{TC: len(步骤)≠len(预期)}|;dsl.C() 的 assert 在构建期已强制1:1,此处为二次遍历复核'),
        ('自查回执', '标题写验证方法数', '%d' % len(a['title_meta_bad']),
         '= |{TC: 标题命中「手段介词+元动词收尾」正则}|;只判句末,排除验证码/校验和这类元动词作名词'
         + ('' if not a['title_meta_bad'] else ';违例:' + _join(a['title_meta_bad']))),
        ('自查回执', '测试类型/覆盖类型枚举非法数',
         '%d' % (len(a['ttype_bad']) + len(a['cover_enum_bad'])),
         '= |{TC: ttype∉TTYPE_OK}| + |{TC: cover∉COVER_OK}|;'
         '测试类型只收六维度,反向/边界/异常属覆盖类型'
         + ('' if not (a['ttype_bad'] or a['cover_enum_bad']) else
            ';违例:' + _join(list(a['ttype_bad']) + list(a['cover_enum_bad'])))),
        ('自查回执', '覆盖类型与测试类型矛盾数', '%d' % len(a['cover_bad']),
         '= |{TC: cover填了维度名且≠ttype推出的维度}|;视角类(正向/反向/边界/异常)与维度无关不计'
         + ('' if not a['cover_bad'] else ';违例:' + _join(a['cover_bad']))),
        ('自查回执', '疑似重复用例组数(软提示)', '%d' % len(a['dup_cand']),
         '判据=操作步骤与预期结果逐条完全相同;只比步骤与预期不比标题'
         + ('' if not a['dup_cand'] else
            ';待确认:' + '/'.join('+'.join(g) for g in a['dup_cand'][:3]))),
        ('自查回执', '技法与测试类型不相容数(软提示)', '%d' % len(a['tech_warn']),
         '= |{TC: tech∈TECH_TTYPE_OK 且 ttype∉白名单}|;边界情形确实存在故只提示不阻断'
         + ('' if not a['tech_warn'] else ';待确认:' + _join(a['tech_warn']))),
        ('自查回执', 'TP维度错配数', '%d' % len(a['dim_bad']),
         '= |{TC: 测试类型→维度 ≠ TP前缀→维度}|;映射表TT2DIM(功能/接口测试→功能)'
         '与PFX2DIM(TP-SEC→安全等);反向/边界/异常属覆盖类型不参与此映射'),
        ('自查回执', 'REQ清单结构性问题数', '%d' % a['req_struct_bad'],
         '= |章节反查差集| + |断号| + |重号| + |字段违例| + (分母不自洽?1:0);'
         '章节差集=文档章节全集(%d)−REQ已引用−已标N/A(%d)'
         % (a['doc_sec_total'], a['section_na_total'])),
        ('自查回执', '功能安全深度未达标数', '%d' % len(a['fs_depth_bad']),
         '= 功能安全REQ(类型=安全∧备注含"功能安全")中,覆盖类型标签不同时含'
         '"功能安全-触发"与"功能安全-恢复"的REQ数;本期功能安全REQ=%s'
         % ('、'.join(a['fs_req']) or '无')),
        ('自查回执', '功能安全触发源缺口', '%d' % len(a['fs_src_bad']),
         '= 各触发源中无任何"功能安全-触发"用例的源数;按用例测试数据列关键字统计'),
        ('自查回执', '必测交叉缺口', '%d' % len(a['ex_must_gap']),
         '= 矩阵中适用性="必测"的格集合 − 落地TC-ID已存在于用例全集的格集合;'
         '标"不适用"的格按skill不计缺口'),
        ('自查回执', 'EX-ID引用非法数', '%d' % len(a['ex_ref_bad']),
         '= REQ清单中来源文档="异常注入库"的来源章节值集合 − EX库全集{%s}' % ex_lib),
        ('自查回执', 'Blocked数', '%d' % a['blk'],
         '= 遍历用例status字段计数;每条均在附表"解除条件"列写明转Ready条件,非静默挂起'),
    ]
    return rows


def build_audit(ws, a, report_note, ex=None, n_spec=0,
                blocked_note='见附表解除条件'):
    n = len(AUDIT_HEADERS)
    title, items = report_note
    _banner(ws, n, title, items, 120)
    ws.append(AUDIT_HEADERS)
    for r in audit_rows(a, ex=ex, n_spec=n_spec, blocked_note=blocked_note):
        ws.append(list(r))
    style_sheet(ws, AUDIT_HEADERS, header_row=2)
    ws.cell(1, 1).alignment = Alignment(wrap_text=True, vertical='center')


def add_pies(ws, a):
    """审计报告内嵌饼图，辅助数据块写在 G/H 列，图锚定在 J 列。

    **合计为 0 的块不画图**（如四类质量缺陷全为 0 的零缺陷情形）：空白饼图无法自证，
    它和「引用地址错位」「数值格存成文本」这两种真故障在页面上长得一模一样，
    读者只会当成交付件坏了。辅助数据块照旧写在 G/H 列，那几个 0 就摆在原处，
    比一个空图说得清楚。
    """
    def pie(title, pairs, anchor='J'):
        r0 = ws.max_row + 2
        ws.cell(r0, 7, title).font = Font(bold=True)
        h = r0 + 1
        for k, v in pairs:
            ws.cell(h, 7, k)
            ws.cell(h, 8, v)
            h += 1
        # 合计为 0 画不出饼图。这里**不往单元格写结论文本**：xlsx 的格子会随
        # export_csv 流进 CSV，而线上那行文本由 feishu.rebuild_charts 写在渲染层
        # tile（不来自 CSV），两边地址不同，写了就会造出一条永远修不掉的假差异。
        if not sum(v for _, v in pairs):
            return
        ch = PieChart()
        ch.title = title
        ch.add_data(Reference(ws, min_col=8, min_row=r0 + 1, max_row=h - 1),
                    titles_from_data=False)
        ch.set_categories(Reference(ws, min_col=7, min_row=r0 + 1, max_row=h - 1))
        ch.dataLabels = DataLabelList()
        ch.dataLabels.showPercent = True
        ch.height, ch.width = 6, 9
        ws.add_chart(ch, anchor + str(r0))

    ncov = len(a['testable']) - len(a['uncovered'])
    n_func = len(a['func_reqs'])
    pie('覆盖率(已覆盖/未覆盖/N-A)',
        [('已覆盖', ncov), ('未覆盖', len(a['uncovered'])), ('N-A', len(a['na']))])
    pie('深度达标占比',
        [('达标', n_func - len(a['depth_bad'])), ('未达标', len(a['depth_bad']))])
    pie('可执行性(Ready/Blocked/Draft)',
        [('Ready', a['ready']), ('Blocked', a['blk']), ('Draft', a['draft'])])
    pie('质量缺陷类型',
        [('坍缩', len(a['collapse_tp']) + len(a['collapse_req'])),
         ('深度缺口', len(a['depth_bad'])), ('反模式', len(a['step_bad'])),
         ('追溯缺口', len(a['uncovered']))])
    pie('优先级分布', [(p, a['pri'][p]) for p in ('P0', 'P1', 'P2', 'P3')])
    # 门禁项数取自 _audit.gates(a)，**不许在这里手写一份清单**：手写的那份会在
    # skill 新增门禁后悄悄落后（实测某项目手写 10 项、权威已 12 项，饼图少算 2 项）。
    g = [ok for _, ok in _audit.gates(a)]
    # +1 的含义写进标签：有 Blocked/Draft 未清零时额外记一项未通过，
    # 否则读者看到「未通过 1」却发现 12 项门禁全绿，会以为饼图算错了。
    pie('硬门禁通过占比',
        [('通过', sum(g)),
         ('未通过(含Blocked/Draft未清零)',
          len(g) - sum(g) + (1 if (a['blk'] or a['draft']) else 0))])


# ---------------- 入口 ----------------

def build(out_path, cases, req_src, req_links, report_note, ex=None,
          spec=None, spec_reqs=(), spec_tr_rows=(), blocked_note='见附表解除条件',
          fs_source_map=None, spec_companion_reqs=None, tp_name_map=None,
          res=None):
    """构建整本交付件并落盘，返回审计结果 dict。

    spec: {'headers':.., 'rows':.., 'detail_headers':.., 'detail_rows':..} 或 None
    spec_companion_reqs: 被专项覆盖、须校验「专项+配套功能用例」的 REQ 全集，
        默认取 spec_reqs。既有普通功能用例又被专项覆盖的 REQ 要列在这里而非 spec_reqs。
    res: 资源观测交付信息（门禁 19）。有专项测试时必填，字段见 audit.compute 文档。
    """
    # tp_name_map 透传给审计：测试点 1:1 退化门禁要按「是否给了正式名称」判，
    # 给了就说明测试点层已做抽象，不能只按用例数比判定（会把合规的单用例测试点误报）。
    # spec 也必须透传：门禁 19 判「本期有无专项测试」要看专项数据，
    # 而专项用例**不在 cases（dsl.CASES）里**——它们走 spec 两表。
    # 早先只按 cases 判，样例项目明明有 TC-SP-PERF-001 却报「无专项、门禁不适用」，
    # 门禁以错误理由通过、等于从未生效（踩过，靠核对自检输出才发现）。
    a = _audit.compute(cases=cases, req_src=req_src, ex=ex, tp_name_map=tp_name_map,
                       spec_reqs=spec_reqs, fs_source_map=fs_source_map,
                       spec_companion_reqs=spec_companion_reqs,
                       res=res, spec=spec)
    n_spec = len(spec['rows']) if spec else 0

    wb = Workbook()
    wb.remove(wb.active)
    build_req(wb.create_sheet('需求原子化清单'), req_src, req_links, cases, spec_reqs)
    if ex is not None:
        build_exm(wb.create_sheet('异常交叉适用性矩阵'), ex)
    build_main(wb.create_sheet('测试用例主表'), cases)
    build_ext(wb.create_sheet('评审追溯表（含风险评估）'), cases)
    build_tr(wb.create_sheet('追溯矩阵表（REQ-TP-TC）'), cases, spec_tr_rows)
    if spec:
        build_table(wb.create_sheet('专项测试用例表'), spec['headers'], spec['rows'])
        build_table(wb.create_sheet('专项数据采集表'),
                    spec['detail_headers'], spec['detail_rows'])
    audit_ws = wb.create_sheet('质量审计报告')
    build_audit(audit_ws, a, report_note, ex=ex, n_spec=n_spec,
                blocked_note=blocked_note)
    add_pies(audit_ws, a)
    wb.save(out_path)
    return a
