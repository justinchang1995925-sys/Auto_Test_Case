# -*- coding: utf-8 -*-
"""飞书电子表格同步（通用）。

三步，飞书端 == 本地 xlsx == 数据模块，三者同源，避免手工拼 CSV 造成漂移：
    1. export_csv()      逐 Sheet 导出 CSV
    2. push()            用 lark-cli 写入飞书（清空 + 覆盖）
    3. format_sheets()   重建格式（清空 scope=all 会连格式一起清掉，必须重建）
    4. rebuild_charts()  重建审计报告饼图

坑位记录（都是踩过的）：
  * CSV 文件名一律用 Sheet 中文名，不用序号——新增 Sheet 会让序号整体后移，
    按序号推送会把内容写进错误的 sheet_id。
  * 图表 refs 是写死的行号。审计表新增门禁行后辅助块整体下移，旧图会指向
    错误区域，所以每次都要删旧图重建，且行号从 CSV 真实解析而非手填。
  * lark-cli 1.0.78 的 +filter-create 的 --properties 为必填，裸建筛选器
    须显式传 {"rules":[]}。
"""
import csv
import json
import os
import subprocess

DEFAULT_LARK_CLI = r"C:/Users/justinchang/AppData/Roaming/npm/lark-cli.cmd"
BANNER_FILL = '#FFF2CC'
HEADER_FILL = '#D9E1F2'


def safe_name(name):
    """Sheet 名转文件名：全角括号转半角，避免不同工具对全角字符处理不一致。"""
    return name.replace('（', '(').replace('）', ')')


def col_letter(n):
    s = ''
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


# ---------------- 1. 导出 CSV ----------------

def export_csv(xlsx_path, out_dir, sheet_ids=None):
    """逐 Sheet 导出为飞书上传用 CSV，返回 [(idx, name, rows, cols, sheet_id, path)]。"""
    from openpyxl import load_workbook

    os.makedirs(out_dir, exist_ok=True)
    wb = load_workbook(xlsx_path)
    out = []
    for i, name in enumerate(wb.sheetnames):
        ws = wb[name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            vals = ['' if v is None else str(v) for v in row]
            while vals and vals[-1] == '':
                vals.pop()
            rows.append(vals)
        rows = [r for r in rows if any(c.strip() for c in r)]
        path = os.path.join(out_dir, safe_name(name) + '.csv')
        with open(path, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows(rows)
        out.append((i, name, len(rows), max(len(r) for r in rows) if rows else 0,
                    (sheet_ids or {}).get(name) or 'NEW-待新建', path))
    return out


# ---------------- lark-cli 封装 ----------------

def _run(lark_cli, sub, token, jq=None, yes=False, **kw):
    cmd = [lark_cli, 'sheets', sub, '--spreadsheet-token', token]
    for k, v in kw.items():
        cmd += ['--' + k.replace('_', '-'), str(v)]
    if jq:
        cmd += ['--jq', jq]
    if yes:
        cmd.append('--yes')
    p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    return (p.stdout or '') + (p.stderr or '')


# ---------------- 3. 重建格式 ----------------

def format_sheets(token, sheets, csv_dir, lark_cli=DEFAULT_LARK_CLI):
    """sheets: [(sheet_id, csv名, 列数, banner行数(0=无), 数据主区最后一行(None=全表))]

    banner 合并行 + 表头加粗 + 冻结 + 筛选 + 列宽 + 数据区顶端对齐自动换行。
    飞书端只做 banner 合并，不做 REQ/TP 列的层级合并（那部分保留在本地 xlsx）。
    """
    results = []
    for sid, name, ncol, banner, main_last in sheets:
        with open(os.path.join(csv_dir, '%s.csv' % name), encoding='utf-8') as f:
            rows = list(csv.reader(f))
        nrow = len(rows)
        hdr = banner + 1                 # 表头行号
        last = main_last or nrow
        C = col_letter(ncol)
        out = []

        def call(sub, **kw):
            return _run(lark_cli, sub, token, jq='.ok', sheet_id=sid, **kw).strip()

        if banner:
            out.append('merge=' + call('+cells-merge', range='A1:%s1' % C,
                                       merge_type='all'))
            out.append('banner=' + call('+cells-set-style', range='A1:%s1' % C,
                                        background_color=BANNER_FILL,
                                        font_weight='bold',
                                        vertical_alignment='middle',
                                        word_wrap='auto-wrap'))
        out.append('hdr=' + call('+cells-set-style',
                                 range='A%d:%s%d' % (hdr, C, hdr),
                                 background_color=HEADER_FILL, font_weight='bold',
                                 vertical_alignment='middle', word_wrap='auto-wrap'))
        if last > hdr:
            out.append('body=' + call('+cells-set-style',
                                      range='A%d:%s%d' % (hdr + 1, C, last),
                                      vertical_alignment='top',
                                      word_wrap='auto-wrap'))
        out.append('freeze=' + call('+dim-freeze', dimension='row', count=hdr))
        # 本 CLI 版本 --properties 必填，裸建筛选器须显式传空规则
        out.append('filter=' + call('+filter-create',
                                    range='A%d:%s%d' % (hdr, C, last),
                                    properties='{"rules":[]}'))
        widths = {}
        for j in range(ncol):
            w = 8
            for r in rows:
                if j < len(r):
                    for ln in str(r[j]).split('\n'):
                        w = max(w, sum(2 if ord(ch) > 255 else 1 for ch in ln))
            widths[col_letter(j + 1)] = int(min(max(w + 2, 10), 60) * 7.5)
        out.append('cols=' + call('+cols-resize',
                                  widths=json.dumps(widths, ensure_ascii=False)))
        results.append((sid, name, nrow, '  '.join(out)))
    return results


# ---------------- 4. 重建饼图 ----------------

def parse_chart_blocks(csv_path):
    """解析审计报告 CSV 里 G/H 两列的饼图辅助块，返回 [{title,trow,last}]。

    块的形态：G 列有标题、H 列为空的行是块首，随后 G/H 都有值的行是数据行。
    行号从 CSV 真实解析，不手填——审计表增删行会让辅助块整体上下移动。
    """
    with open(csv_path, encoding='utf-8') as f:
        rows = list(csv.reader(f))
    blocks, cur = [], None
    for i, r in enumerate(rows, 1):
        g = (r[6] if len(r) > 6 else '').strip()
        h = (r[7] if len(r) > 7 else '').strip()
        if g and not h:
            if cur:
                blocks.append(cur)
            cur = dict(title=g, trow=i, last=i)
        elif g and h and cur:
            cur['last'] = i
    if cur:
        blocks.append(cur)
    return blocks


def rebuild_charts(token, sheet_id, sheet_name, csv_dir,
                   tiles=('J1', 'P1', 'J16', 'P16', 'J31', 'P31'),
                   lark_cli=DEFAULT_LARK_CLI):
    """删除旧图后按 CSV 真实行号重建饼图。"""
    blocks = parse_chart_blocks(os.path.join(csv_dir, '%s.csv' % sheet_name))
    out = _run(lark_cli, '+chart-list', token, sheet_id=sheet_id)
    old = []
    if '"ok": true' in out:
        try:
            old = json.loads(out)['data']['sheets'][0].get('charts', []) or []
        except Exception:
            old = []
    for c in old:
        _run(lark_cli, '+chart-delete', token, sheet_id=sheet_id,
             chart_id=c['chart_id'], yes=True)

    made = []
    for b, anchor in zip(blocks, tiles):
        acol = ''.join(ch for ch in anchor if ch.isalpha())
        arow = int(''.join(ch for ch in anchor if ch.isdigit()))
        props = {
            "position": {"col": acol, "row": arow},
            "offset": {"col_offset": 0, "row_offset": 0},
            "size": {"height": 260, "width": 420},
            "snapshot": {
                "data": {
                    "dim1": {"serie": {"aggregate": True, "index": 1,
                                       "nameRef": "'%s'!G%d" % (sheet_name, b['trow'])}},
                    "dim2": {"series": [{"index": 2,
                                         "nameRef": "'%s'!H%d" % (sheet_name, b['trow'])}]},
                    "direction": "column",
                    "includeHiddenOrFilter": False,
                    "isStaticData": False,
                    "refs": [{"value": "'%s'!G%d:H%d"
                              % (sheet_name, b['trow'], b['last'])}],
                },
                "legend": {"position": "bottom"},
                "plotArea": {"plot": {"extra": {"smooth": False, "step": False},
                                      "labels": {"category": True,
                                                 "percentage": True,
                                                 "value": False},
                                      "type": "pie"}},
                "style": {"border": {"color": "#dee0e3"}, "colorGradient": False},
                "title": {"text": b['title']},
            },
        }
        r = _run(lark_cli, '+chart-create', token, sheet_id=sheet_id,
                 properties=json.dumps(props, ensure_ascii=False))
        made.append((b['title'], 'G%d:H%d' % (b['trow'], b['last']), anchor,
                     '"ok": true' in r))
    return made
