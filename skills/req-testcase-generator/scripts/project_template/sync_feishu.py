# -*- coding: utf-8 -*-
"""飞书同步入口 —— 复制到项目目录后，只改顶部 CONFIG。

前提：先跑 build.py 生成 xlsx；飞书侧已建好电子表格与各 Sheet，
      并把每个 Sheet 的 sheet_id 回填到 SHEET_ID。

用法：
    python sync_feishu.py export     # 只导出 CSV（看行列数、核对 sheet_id）
    python sync_feishu.py format     # 重建格式（清空 scope=all 后必须跑）
    python sync_feishu.py charts     # 重建审计报告饼图
    python sync_feishu.py all        # format + charts

写入单元格数据本身用 lark-cli 的 sheets 命令或 lark-sheets skill 完成；
本脚本负责「导出同源 CSV」与「重建格式/图表」这两件容易漂移的事。
"""
import sys

import _boot

_boot.setup()

from tcgen import feishu                            # noqa: E402

# ============ 项目配置（每个项目只改这一块）============
XLSX = '测试交付件-示例项目-20260907.xlsx'
CSV_DIR = '.feishu_csv'
TOKEN = 'PUT-YOUR-SPREADSHEET-TOKEN-HERE'

# Sheet 中文名 -> 飞书 sheet_id。新增 Sheet 后必须回填，
# 一律按名字映射而非序号——新增 Sheet 会让序号整体后移，按序号推会写错表。
SHEET_ID = {
    '需求原子化清单': '',
    '异常交叉适用性矩阵': '',
    '测试用例主表': '',
    '评审追溯表（含风险评估）': '',
    '追溯矩阵表（REQ-TP-TC）': '',
    '专项测试用例表': '',
    '专项数据采集表': '',
    '质量审计报告': '',
}

# (sheet_id, CSV名(半角括号), 列数, banner行数(0=无), 数据主区最后一行(None=全表))
# 审计报告的 main_last 必须填「主区最后一行」——它之后的 G/H 列是饼图辅助块，
# 不能被表格格式和筛选器覆盖。行数变了要同步改这里。
def sheets():
    S = SHEET_ID
    return [
        (S['需求原子化清单'],        '需求原子化清单',        8,  1, None),
        (S['异常交叉适用性矩阵'],     '异常交叉适用性矩阵',     9,  1, None),
        (S['测试用例主表'],          '测试用例主表',          9,  0, None),
        (S['评审追溯表（含风险评估）'], '评审追溯表(含风险评估)',  11, 0, None),
        (S['追溯矩阵表（REQ-TP-TC）'], '追溯矩阵表(REQ-TP-TC)',  5,  0, None),
        (S['专项测试用例表'],        '专项测试用例表',        10, 0, None),
        (S['专项数据采集表'],        '专项数据采集表',         6,  0, None),
        (S['质量审计报告'],          '质量审计报告',          4,  1, AUDIT_MAIN_LAST),
    ]


AUDIT_MAIN_LAST = 62   # 审计表主区最后一行，跑 export 看实际行数后回填
AUDIT_SHEET_NAME = '质量审计报告'
# =====================================================


def do_export():
    for i, name, nrow, ncol, sid, path in feishu.export_csv(XLSX, CSV_DIR, SHEET_ID):
        print('%-3d %-24s rows=%-5d cols=%-4d %-12s %s'
              % (i, name, nrow, ncol, sid, path))


def do_format():
    for sid, name, nrow, out in feishu.format_sheets(TOKEN, sheets(), CSV_DIR):
        print('%-8s %-22s rows=%-4d %s' % (sid, name, nrow, out))


def do_charts():
    for title, rng, anchor, ok in feishu.rebuild_charts(
            TOKEN, SHEET_ID[AUDIT_SHEET_NAME], AUDIT_SHEET_NAME, CSV_DIR):
        print('  %-28s %-12s @%-4s ok=%s' % (title, rng, anchor, ok))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'export'
    if cmd == 'export':
        do_export()
    elif cmd == 'format':
        do_format()
    elif cmd == 'charts':
        do_charts()
    elif cmd == 'all':
        do_format()
        do_charts()
    else:
        print(__doc__)
        sys.exit(2)
