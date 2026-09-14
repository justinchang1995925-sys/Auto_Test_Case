# -*- coding: utf-8 -*-
"""交付件构建入口 —— 复制到项目目录后，只改本文件顶部的 CONFIG 与数据层模块名。

用法：
    python build.py

产出：
    测试交付件-{需求名}-{日期}.xlsx   （一个工作簿多 Sheet）
    {需求名}测试点.drawio             （思维导图，可导入飞书）
"""
import os

import _boot

_boot.setup()

from tcgen import plat                           # noqa: E402

# 门禁结论与交付件名称都是中文：Ubuntu 在 LC_ALL=C / LANG 未设时
# stdout 是 ASCII，print 直接 UnicodeEncodeError。写得出就不动。
plat.force_utf8_stdout()

from tcgen import drawio, xlsx                      # noqa: E402
from tcgen.dsl import CASES                         # noqa: E402

# 数据层：import 即把用例注册进 CASES（拆多个文件就在这里全部 import）
import cases_demo                                   # noqa: F401,E402
import d_ex_demo as d_ex                            # noqa: E402
import reqs                                         # noqa: E402
import spec                                         # noqa: E402

# ============ 项目配置（每个项目只改这一块）============
PROJECT = '示例项目'
DATE = '20260907'
XLSX_OUT = '测试交付件-%s-%s.xlsx' % (PROJECT, DATE)
DRAWIO_OUT = '%s测试点.drawio' % PROJECT

# 专项等不在普通用例里的测试点，补进思维导图：{TP-ID: (维度, 描述)}
EXTRA_TP = {
    'TP-P-001': ('性能', '单次操作响应<2s'),
}

# 思维导图模块层：某维度 TP 数 >= GROUP_MIN 时，在维度与测试点之间插一层「模块」。
# 不加这层的话，占大半 TP 的维度（通常是功能）标签会被自动布局摆到巨大子块的正中间，
# 读者滚到最上面几行测试点时标签已在屏幕外，看起来像「维度丢了、直接显示 TP-TC」。
# 硬门禁 13 会检查：任一维度 TP 数 >=12 必须有模块层，且模块名必须是中文。
GROUP_MIN = 12
# {TC-ID 里的模块缩写: 中文名}，缺失会回退成英文缩写而违反中文命名要求
MODULE_NAMES = {
    'SAVE': '保存与生效',
    'PERF': '性能专项',
    'ESTOP': '急停功能安全',
}

# 测试点正式名称 {TP-ID: 名称}。**归并后一个测试点挂多条用例时必须给名称**：
# 不给会默认取「首条用例标题」，于是测试点层只是复读用例标题、不成抽象，
# 思维导图里用例节点还会因去重显示「同测试点主场景」，评审看不出测了哪些方面。
# 硬门禁「测试点未1:1退化」按此判定：唯一用例且未给名称 = 退化。
TP_NAMES = {
    # 样例：真实项目里一个测试点通常挂 2~4 条用例，名称写「该需求要测的一个方面」，
    # 用例写「这个方面怎么验」。下面每个测试点各挂 1 条只是样例数据规模小。
    'TP-F-001': '必填项齐全时的保存生效',
    'TP-F-002': '保存中断的原子性',
    'TP-F-003': '必填项缺失时的保存拦截',
    'TP-F-004': '校验解除后的恢复保存',
    'TP-F-005': '专项覆盖 REQ 的功能可用性',
    'TP-SEC-101': '面板急停触发',
    'TP-SEC-102': '急停解除与恢复确认',
    'TP-SEC-103': '外部回路急停触发',
    'TP-SEC-104': '软件指令急停触发',
    'TP-SEC-111': '运动中急停的越程行为',
}

# 思维导图输出（.mmd 供写入飞书画板；飞书画板不认 .drawio）
MMD_OUT = '%s测试点.mmd' % PROJECT

# Blocked 用例的成因摘要，写进审计报告
BLOCKED_NOTE = '待安规给出停止时限X，见附表解除条件'
# =====================================================


def main():
    a = xlsx.build(
        XLSX_OUT,
        cases=CASES,
        req_src=reqs.REQ_SRC,
        req_links=reqs.REQ_SRC_LINKS,
        report_note=reqs.REPORT_NOTE,
        ex=d_ex,                       # 本期无 EX 时传 None
        spec={'headers': spec.SP_HEADERS, 'rows': spec.SP_ROWS,
              'detail_headers': spec.SPD_HEADERS, 'detail_rows': spec.SPD_ROWS},
        spec_reqs=reqs.SPEC_REQS,
        spec_tr_rows=reqs.SPEC_TR_ROWS,
        tp_name_map=TP_NAMES,   # 测试点正式名称，供 1:1 退化门禁判定
        # 资源观测交付信息（门禁 19）。有专项测试时必填；本期无专项可传 None。
        res=spec.RES,
        blocked_note=BLOCKED_NOTE,
    )
    mm_kw = dict(root_label=PROJECT, extra_tp=EXTRA_TP,
                 group_min=GROUP_MIN, module_names=MODULE_NAMES,
                 tp_names=TP_NAMES)
    d = drawio.build(DRAWIO_OUT, CASES, **mm_kw)
    m = drawio.mermaid(MMD_OUT, CASES, **mm_kw)

    print('saved %s | 用例 %d | Ready %d | Blocked %d'
          % (XLSX_OUT, len(CASES), a['ready'], a['blk']))
    print('saved %s | 维度 %d | 模块 %d | TP节点 %d | TC节点 %d'
          % (DRAWIO_OUT, d['dims'], d['mods'], d['tps'], d['tcs']))
    print('saved %s | 维度 %d | 模块 %d | TP节点 %d | TC节点 %d'
          % (MMD_OUT, m['dims'], m['mods'], m['tps'], m['tcs']))
    assert (m['mods'], m['tps'], m['tcs']) == (d['mods'], d['tps'], d['tcs']),         'drawio 与 mermaid 层级不一致'

    # 硬门禁未通过时直接报出来，不让它静默混过去
    from tcgen.audit import gates
    bad = [name for name, ok in gates(a) if not ok]
    print('硬门禁: %s' % ('全部通过' if not bad else '未通过 -> ' + '; '.join(bad)))

    # 复用检查：项目侧不许抄一份共享实现。实测踩过两次——项目自己抄了 add_pies /
    # 建图脚本后，skill 里的修复（如「合计为 0 不画饼图」）改了也不会生效，
    # 谁跑一次就把老问题重新造回来。抄一份的代价是静默的，所以必须自动查。
    from tcgen.reuse import report as reuse_report
    reuse_report(os.path.dirname(os.path.abspath(__file__)))
    return a


if __name__ == '__main__':
    main()
