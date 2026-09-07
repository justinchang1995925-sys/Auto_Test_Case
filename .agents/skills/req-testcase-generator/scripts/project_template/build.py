# -*- coding: utf-8 -*-
"""交付件构建入口 —— 复制到项目目录后，只改本文件顶部的 CONFIG 与数据层模块名。

用法：
    python build.py

产出：
    测试交付件-{需求名}-{日期}.xlsx   （一个工作簿多 Sheet）
    {需求名}测试点.drawio             （思维导图，可导入飞书）
"""
import _boot

_boot.setup()

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
        blocked_note=BLOCKED_NOTE,
    )
    d = drawio.build(DRAWIO_OUT, CASES, root_label=PROJECT, extra_tp=EXTRA_TP)

    print('saved %s | 用例 %d | Ready %d | Blocked %d'
          % (XLSX_OUT, len(CASES), a['ready'], a['blk']))
    print('saved %s | 维度 %d | TP节点 %d' % (DRAWIO_OUT, d['dims'], d['tps']))

    # 硬门禁未通过时直接报出来，不让它静默混过去
    from tcgen.audit import gates
    bad = [name for name, ok in gates(a) if not ok]
    print('硬门禁: %s' % ('全部通过' if not bad else '未通过 -> ' + '; '.join(bad)))
    return a


if __name__ == '__main__':
    main()
