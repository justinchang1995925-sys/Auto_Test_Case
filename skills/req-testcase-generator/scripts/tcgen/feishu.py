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
import io
import json
import os
import re
import subprocess

from . import plat

#: lark-cli 可执行文件。**不写死绝对路径**：写死某台机器某个用户名下的
#: `AppData/Roaming/npm/lark-cli.cmd` 后，换机器（换用户名、换到 Linux）时
#: 全部飞书函数一律 FileNotFoundError，而本地 xlsx/drawio 照常产出——
#: 很容易被误读成"只是飞书没连上"。定位规则见 tcgen.plat.lark_cli()。
#: 自定义安装位置时设环境变量 TCGEN_LARK_CLI，不要改这行。
DEFAULT_LARK_CLI = plat.lark_cli()
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

def _exec(cmd):
    """跑 lark-cli 并返回 CompletedProcess。所有 CLI 调用都必须走这里。

    两件平台相关的事收在这一处：
      * `FileNotFoundError` 翻译成带修法的报错。裸的 FileNotFoundError 只会显示
        一个可执行文件名，看不出"要装 lark-cli 还是要设 TCGEN_LARK_CLI"。
      * `errors='replace'` 兜住解码失败。CLI 在不同 locale 下可能吐出非 UTF-8
        字节（Linux 的 LC_ALL=C 尤其容易），不兜住就是一个 UnicodeDecodeError
        崩在解析之前，看起来像飞书返回了脏数据。
    """
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding='utf-8', errors='replace')
    except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
        raise RuntimeError(plat.cli_missing_msg(cmd[0], e))


def _run(lark_cli, sub, token, jq=None, yes=False, **kw):
    cmd = [lark_cli or plat.lark_cli(), 'sheets', sub,
           '--spreadsheet-token', token]
    for k, v in kw.items():
        cmd += ['--' + k.replace('_', '-'), str(v)]
    if jq:
        cmd += ['--jq', jq]
    if yes:
        cmd.append('--yes')
    p = _exec(cmd)
    return (p.stdout or '') + (p.stderr or '')


# ---------------- 2.5 回读与逐格比对（门禁18） ----------------

def read_sheet(token, sheet_id, last_col='P', last_row=400,
               lark_cli=DEFAULT_LARK_CLI, raw=False):
    """回读飞书某 Sheet 的全部单元格，返回 [[str, ...], ...]。

    单元格值统一归一化成字符串再返回：飞书会把纯数字列存成 float
    （`147` 读回来是 `147.0`），富文本单元格读回来是 list/dict。不归一化，
    比对结果会全是假差异。

    `raw=True` 时**不归一化**，原样返回 int/float/str —— 只在需要判断
    「这一格到底是数字还是文本」时用（如饼图数值格检查）。归一化会把 `67` 和
    `'67'` 都变成 `"67"`，类型信息就丢了。
    """
    # 用 +cells-get，且 sheet 必须走独立的 --sheet-id 参数、range 里不带 sheet 前缀。
    # 历史上这里用过 `+read`，但该子命令自 lark-cli 1.0.94 起已不存在（改名
    # `+cells-get`）。命令报错 → values 取空 → 每格都读成 ''，比对结果变成
    # 「线上全空」的假差异（实测一次刷出 1624 处），而且 diff 一失效，
    # 「图表引用错位」这类只能靠回读发现的故障就再也抓不到了。
    # 校验命令是否存在：`lark-cli sheets --help`。
    cmd = [lark_cli or plat.lark_cli(), 'sheets', '+cells-get',
           '--spreadsheet-token', token,
           '--sheet-id', sheet_id,
           '--range', 'A1:%s%d' % (last_col, last_row),
           '--as', 'user']
    p = _exec(cmd)
    try:
        d = json.loads(p.stdout or '{}')
    except ValueError:
        raise RuntimeError('读 %s 失败: %s' % (sheet_id, (p.stdout or p.stderr)[:200]))
    if not d.get('ok', True):
        raise RuntimeError('读 %s 失败: %s' % (sheet_id, str(d.get('error'))[:200]))
    data = d.get('data') or {}
    # +cells-get 的形状：data.ranges[0].cells = [[{value: ...}, ...], ...]
    # 每格是 dict 而非裸值，取不到 value 时回退到旧形状，兼容其它返回结构。
    vs = []
    ranges = data.get('ranges') or []
    if ranges:
        for row in (ranges[0].get('cells') or []):
            vs.append([(c.get('value') if isinstance(c, dict) else c) for c in row])
    else:
        vs = (data.get('valueRange') or {}).get('values') or data.get('values') or []
    if raw:
        return [list(row) for row in vs]
    return [[_norm_cell(x) for x in row] for row in vs]


def _norm_cell(v):
    if v is None:
        return ''
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float) and v == int(v):
        v = int(v)          # 147.0 -> 147，否则与 CSV 里的 "147" 对不上
    if isinstance(v, (list, dict)):
        # 富文本/超链接单元格：抽出纯文本，抽不出就整体序列化
        if isinstance(v, list):
            out = []
            for e in v:
                if isinstance(e, dict):
                    out.append(str(e.get('text') or e.get('value') or ''))
                else:
                    out.append(str(e))
            return ''.join(out).strip()
        return json.dumps(v, ensure_ascii=False)
    return str(v).replace('\r\n', '\n').strip()


def _trim(rows):
    """去掉每行尾部空列与整表尾部空行，让飞书侧的空白区不算差异。"""
    out = []
    for r in rows:
        r = list(r)
        while r and r[-1] == '':
            r.pop()
        out.append(r)
    while out and not any(out[-1]):
        out.pop()
    return out


def diff_sheets(token, sheets, csv_dir, lark_cli=DEFAULT_LARK_CLI,
                tile_sheet=None, tiles=None):
    """逐格比对「飞书在线」与「本地 CSV」，返回 [(sheet名, [(行, 列, 线上值, 本地值)])]。

    门禁18 要求「必须机器逐格比对，不许肉眼扫」——肉眼扫表实测漏过
    `TP-UX-002 -> TP-UX-004` 这种只改两个格子的改动。

    sheets: [(sheet_id, csv名)]；csv名 用 Sheet 中文名（见模块 docstring 的坑位）。
    差异里「线上有本地无」和「本地有线上无」都会列出，行号与列号**都是 1-based**，
    可直接喂给 col_letter()（它也是 1-based：col_letter(1) == 'A'）。
    别改成 0-based 列下标：col_letter(0) 返回空串，col_letter(8) 得到 'H' 而那其实是
    第 9 列 'I'——报出来的单元格地址会整体错一位，照着地址去改就改错格子了。
    """
    out = []
    for sheet_id, name in sheets:
        path = os.path.join(csv_dir, safe_name(name) + '.csv')
        if not os.path.exists(path):
            out.append((name, [(0, 0, '(本地缺 CSV)', path)]))
            continue
        with io.open(path, encoding='utf-8', newline='') as f:
            loc = _trim([[_norm_cell(x) for x in r] for r in csv.reader(f)])
        # 线上值再过一遍 _norm_cell：read_sheet 里已经归一化过，这里重复一次是有意的。
        # _norm_cell 幂等，成本可忽略；而把归一化收在「比对点」这一处，才能保证换了
        # 读取方式（换 CLI 子命令、换成传入现成 rows）也不会因为少归一化而刷出假差异。
        fs = _trim([[_norm_cell(x) for x in r]
                    for r in read_sheet(token, sheet_id, lark_cli=lark_cli)])
        # 渲染层格位不参与数据比对：审计报告的 2×3 tile 要么被饼图对象盖住，
        # 要么（零数据时）写着结论文本。这些内容**不来自 CSV**，比下去就是一条
        # 永远修不掉的假差异——而一个会误报的检查很快就没人看了。
        # 它们的正确性由 diff_charts 负责：一个格子只能有一个检查者。
        skip = tile_cells(tiles) if (tile_sheet and name == tile_sheet) else set()
        diffs = []
        for i in range(max(len(loc), len(fs))):
            lr = loc[i] if i < len(loc) else []
            fr = fs[i] if i < len(fs) else []
            for j in range(max(len(lr), len(fr))):
                if (i + 1, j + 1) in skip:
                    continue
                lv = lr[j] if j < len(lr) else ''
                fv = fr[j] if j < len(fr) else ''
                if lv != fv:
                    diffs.append((i + 1, j + 1, fv, lv))
        out.append((name, diffs))
    return out


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

#: 审计报告饼图的 2×3 格位。**生成侧（build_xlsx 写 xlsx）与推送侧
#: （rebuild_charts 写线上）必须用同一份**：零数据块的结论文本要落在同一个单元格，
#: 地址错开一格就会让 diff_sheets 报一条永远修不掉的假差异。
CHART_TILES = ('J1', 'P1', 'J16', 'P16', 'J31', 'P31')


def tile_cells(tiles=None):
    """把 tile 地址（'P16'）解成 {(行, 列)}，均为 1-based，与 diff_sheets 的坐标一致。

    这些格位属于**渲染层**：要么被饼图对象盖住，要么（零数据时）写着结论文本。
    它们不来自 CSV，所以必须排除在 `diff_sheets` 之外，否则会报永久假差异；
    它们的正确性由 `diff_charts` 负责——**一个格子只能有一个检查者**。
    """
    cells = set()
    for t in (tiles or CHART_TILES):
        col = ''.join(ch for ch in t if ch.isalpha()).upper()
        row = int(''.join(ch for ch in t if ch.isdigit()))
        n = 0
        for ch in col:
            n = n * 26 + (ord(ch) - 64)
        cells.add((row, n))
    return cells


def zero_note(title, labels):
    """合计为 0 的辅助块，替代饼图的那行结论文本——**文案唯一来源**。

    生成侧和推送侧都必须调这个函数，不许各写一份字符串：只要有一个字不同，
    `diff_sheets` 就会报一条谁也修不掉的假差异，而一个会误报的检查很快就没人看了。
    """
    if not labels:
        return '%s：无数据' % title
    return '%s：%s 均为 0' % (title, '／'.join(labels))


def parse_chart_blocks(csv_path):
    """解析审计报告 CSV 里 G/H 两列的饼图辅助块。

    返回 [{title, trow, last, labels, total}]：
      trow/last = 块首行/末行（1-based，可直接拼 `G%d:H%d`）
      labels    = 各扇区名，供零数据时生成结论文本
      total     = 各扇区数值之和；**为 0 表示这个块画不出饼图**

    块的形态：G 列有标题、H 列为空的行是块首，随后 G/H 都有值的行是数据行。
    行号从 CSV 真实解析，不手填——审计表增删行会让辅助块整体上下移动。

    `total` 是 A 方案的判据：合计为 0 的块（如四类质量缺陷全为 0 的零缺陷情形）
    不画饼图，改写一行结论文本。空白饼图无法自证——它和「引用错位」「数值存成文本」
    这两种真故障在页面上长得一模一样，实测为分辨它们花掉了三轮排查。
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
            cur = dict(title=g, trow=i, last=i, labels=[], total=0)
        elif g and h and cur:
            cur['last'] = i
            cur['labels'].append(g)
            try:
                cur['total'] += float(h)
            except ValueError:
                pass          # 非数值的辅助行不计入合计
    if cur:
        blocks.append(cur)
    return blocks


def diff_charts(token, sheet_id, csv_path, lark_cli=DEFAULT_LARK_CLI):
    """比对「线上图表引用的单元格范围」与「CSV 里辅助块的真实位置」。

    返回 (missing, extra, text_cells)，三者都空才算图表健康：
      missing    = CSV 有辅助块而线上没有图表引用它的范围
      extra      = 线上引用了但 CSV 里已不是辅助块的范围（过期引用）
      text_cells = 被引用的数值格里**存成了文本**的（如 `'67'` 而非 `67`）

    饼图有两种坏法，**必须都查**，实测两种都真实发生过：

    ① **引用地址错位**。图表引用的是**绝对单元格地址**
    （`'质量审计报告'!G63:H66`），审计报告增删行会让 G/H 辅助块整体上下移动，
    而图表引用**不会跟着位移**。此时数据逐格比对全部一致、图表对象也都还在，
    但每个饼图都指向空白区。实测：报告插入 5 行后 6 个饼图引用全偏 −5 行。

    ② **数值格存成了文本**（`text_cells`，**软提示，不作阻断**）。H 列存成
    `'67'` 而非 `67`。这一条 `diff_sheets` 查不出来——`_norm_cell` 为了消除
    「`147` vs `147.0`」的假差异，会把 `67` 和 `'67'` 都归一化成 `"67"`，
    类型信息正好被抹掉，所以这里用 `read_sheet(raw=True)` 拿原值判类型。

    **但「文本必空白」并不普遍成立，故本项只提示不阻断**。实测（2026-09）：
    某环境下 H 列 14 格全为字符串，5 个饼图**渲染完全正常、无空白**。并且
    该环境下无可用通道能写出真数字——`+cells-set` 传 `{'value': 18}`
    （dry-run 确认 payload 是数字）、`+workbook-import` 导入 xlsx，两条路径
    写进去一律变字符串。若把本项当阻断，`diff` 会每次恒报十余处、且**无法修复**，
    那就成了「一个会误报又修不掉的检查」——很快没人看，反过来削弱 missing/extra
    这两项真检查的可信度。
    因此：`missing`/`extra` 是硬性的（引用错位确实会让饼图指向空白区，实测过），
    `text_cells` 仅作线索——**当饼图确实空白、且引用已对齐时，再来看这一项**。

    **合计为 0 的块被排除在检查之外**：按 A 方案它本就不该有饼图（改写结论文本），
    若仍算进 `exp` 就会把「按设计没有图表」报成 `missing` 假差异。反过来，某块从
    非零变成 0 后，线上那个旧图会落进 `extra`——这正是需要重跑 `charts` 的信号。
    """
    blocks = parse_chart_blocks(csv_path)
    charted = [b for b in blocks if b['total']]
    exp = set('G%d:H%d' % (b['trow'], b['last']) for b in charted)
    out = _run(lark_cli, '+chart-list', token, sheet_id=sheet_id)
    online = set(re.findall(r"!\$?([A-Z]+\$?\d+:\$?[A-Z]+\$?\d+)", out))
    online = set(r.replace('$', '') for r in online)

    # 数值格类型检查：标题行 (trow) 的 H 本就是空的，数据行是 trow+1..last。
    # 只查会被画成饼图的块——不画图的块，其单元格类型不影响任何渲染结果。
    text_cells = []
    if charted:
        last = max(b['last'] for b in charted)
        grid = read_sheet(token, sheet_id, last_col='H', last_row=last,
                          lark_cli=lark_cli, raw=True)
        for b in charted:
            for row in range(b['trow'] + 1, b['last'] + 1):
                cells = grid[row - 1] if row - 1 < len(grid) else []
                v = cells[7] if len(cells) > 7 else None
                if v in (None, ''):
                    continue
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    text_cells.append('H%d=%r' % (row, v))
    return sorted(exp - online), sorted(online - exp), text_cells


def rebuild_charts(token, sheet_id, sheet_name, csv_dir,
                   tiles=CHART_TILES,
                   lark_cli=DEFAULT_LARK_CLI):
    """删除旧图后按 CSV 真实行号重建饼图。

    **合计为 0 的辅助块不画饼图**（A 方案），改在该格位写一行结论文本。
    因为空白饼图无法自证：它和「引用错位」「数值格存成文本」这两种真故障在页面上
    长得一模一样，实测为分辨它们花掉了三轮排查。而往 H 列塞个占位 `1` 凑出整圆
    属于伪造数据——报告里出现不是真实计数的数字，和「门禁造假」是同一类问题。

    返回 [(title, range, anchor, ok, kind)]，kind 为 'chart' 或 'note'。
    """
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

        # A 方案：合计为 0 画不出饼图，改写一行结论文本，让「零缺陷」和
        # 「图表坏了」在页面上可区分（空白饼图两者长得一样）。
        if not b['total']:
            note = zero_note(b['title'], b['labels'])
            out = _run(lark_cli, '+cells-set', token, sheet_id=sheet_id,
                       range='%s%d' % (acol, arow),
                       cells=json.dumps([[{'value': note}]], ensure_ascii=False))
            made.append((b['title'], 'G%d:H%d' % (b['trow'], b['last']),
                         anchor, '"ok": true' in out, 'note'))
            continue

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
                     '"ok": true' in r, 'chart'))
    return made
