# -*- coding: utf-8 -*-
"""飞书同步入口 —— 复制到项目目录后，只改顶部 CONFIG。

前提：先跑 build.py 生成 xlsx；飞书侧已建好电子表格与各 Sheet，
      并把每个 Sheet 的 sheet_id 回填到 SHEET_ID。

用法：
    python sync_feishu.py export     # 只导出 CSV（看行列数、核对 sheet_id）
    python sync_feishu.py diff       # 回读飞书逐格比对本地 CSV（差异非0 -> 退出码1）
    python sync_feishu.py format     # 重建格式（清空 scope=all 后必须跑）
    python sync_feishu.py charts     # 重建审计报告饼图
    python sync_feishu.py all        # format + charts

改完数据源后的完整收尾（门禁18 交付件全链路同步）：
    python build.py && python sync_feishu.py export
    <推送改动到飞书>
    python sync_feishu.py diff       # 必须差异=0 才算同步完成

写入单元格数据本身用 lark-cli 的 sheets 命令或 lark-sheets skill 完成；
本脚本负责「导出同源 CSV」与「重建格式/图表」这两件容易漂移的事。
"""
import os
import sys

import _boot

_boot.setup()

from tcgen import plat                           # noqa: E402

# 门禁结论与交付件名称都是中文：Ubuntu 在 LC_ALL=C / LANG 未设时
# stdout 是 ASCII，print 直接 UnicodeEncodeError。写得出就不动。
plat.force_utf8_stdout()

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
    for title, rng, anchor, ok, kind in feishu.rebuild_charts(
            TOKEN, SHEET_ID[AUDIT_SHEET_NAME], AUDIT_SHEET_NAME, CSV_DIR):
        # kind='note'：该块合计为 0，画不出饼图，已改写一行结论文本（A 方案）。
        # 空白饼图无法自证——和「引用错位」「数值存成文本」两种真故障长得一样。
        tag = '饼图' if kind == 'chart' else '结论文本（合计为0）'
        print('  %-28s %-12s @%-4s %-16s ok=%s' % (title, rng, anchor, tag, ok))


def do_diff():
    """回读飞书逐格比对本地 CSV，差异非 0 时退出码 1。

    门禁18 要求「必须机器逐格比对，不许肉眼扫」：本地重建成功不等于线上已更新，
    肉眼扫表实测漏过只改两个格子的改动。差异若不属于本次改动（可能是别人在线上
    手工改的），先报给用户判断，不要直接整表覆盖。
    """
    pairs = [(sid, name) for name, sid in SHEET_ID.items() if sid]
    missing = [name for name, sid in SHEET_ID.items() if not sid]
    if missing:
        print('!! 未回填 sheet_id，跳过比对: %s' % '，'.join(missing))
    # 审计报告的 2×3 tile 是渲染层格位（饼图对象，或零数据时的结论文本），
    # 不来自 CSV，交由 diff_charts 检查；比进数据差异里会成为永久假差异。
    res = feishu.diff_sheets(TOKEN, pairs, CSV_DIR,
                             tile_sheet=AUDIT_SHEET_NAME)
    total = 0
    for name, diffs in res:
        total += len(diffs)
        print('%-24s %s' % (name, 'OK 一致' if not diffs else '差异 %d 处' % len(diffs)))
        for row, col, online, local in diffs[:12]:
            print('    %s%-4d 线上=%-28r 本地=%r'
                  % (feishu.col_letter(col), row, online[:28], local[:28]))
        if len(diffs) > 12:
            print('    ... 另有 %d 处' % (len(diffs) - 12))
    print()
    print('合计差异单元格 = %d -> %s'
          % (total, '飞书已与本地一致' if not total else '飞书落后，需推送后重跑本命令'))

    # 图表引用必须单独查：数据逐格一致 **不代表** 图表没坏。图表引用的是绝对
    # 单元格地址，审计报告增删行会让 G/H 辅助块整体位移，而引用不会跟着动——
    # 此时上面的逐格比对全部 OK、图表对象也都在，但每个饼图都指向空白区。
    # 实测：报告插入 5 行后 6 个饼图引用全部偏 -5 行，线上看到 6 个空图。
    bad = 0
    rep = SHEET_ID.get(AUDIT_SHEET_NAME)
    if rep:
        path = os.path.join(CSV_DIR, feishu.safe_name(AUDIT_SHEET_NAME) + '.csv')
        miss, extra, text_cells = feishu.diff_charts(TOKEN, rep, path)
        # 只有引用错位（miss/extra）算阻断。数值格文本是软提示：实测某环境
        # 全为字符串时饼图照样正常渲染，且该环境下无通道能写出真数字，
        # 当阻断会变成每次恒报又修不掉的告警，反而拖垮真检查的可信度。
        bad = len(miss) + len(extra)
        print()
        print('图表健康检查: %s' % ('OK 引用对齐'
                                   if not bad else '异常 %d 处' % bad))
        if miss:
            print('    CSV 有辅助块但线上无图表引用: %s' % '，'.join(miss))
        if extra:
            print('    线上引用了但 CSV 已非辅助块（过期引用）: %s' % '，'.join(extra))
        if miss or extra:
            print('    修法: python sync_feishu.py charts   # 按 CSV 真实行号重建图表')
        if text_cells:
            # 软提示，不计入 bad。仅当饼图确实空白、且引用已对齐时才需追这一项。
            print('    提示(不阻断) 数值格为文本 %d 处，如 %s'
                  % (len(text_cells), '、'.join(text_cells[:3])))
            print('    仅当饼图确实空白且引用已对齐时才需处理；'
                  '部分环境文本格照样正常渲染')
    return 0 if not total and not bad else 1


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'export'
    if cmd == 'export':
        do_export()
    elif cmd == 'diff':
        sys.exit(do_diff())
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
