# -*- coding: utf-8 -*-
"""复用检查 —— 揪出项目目录里「抄了一份共享实现」的文件。

存在理由（实测踩过两次，第二次是复盘审计才发现的）：
  ① 某项目的 `charts_feishu.py` 曾是一份完整的建图实现（自己写死 tile、自己拼
     chart-create）。skill 里加了「合计为 0 不画饼图」之后，它照旧建 6 个图——
     谁跑一次就把那个空白饼图重新造回来。
  ② 同一条修复只改了项目本地的 `build_xlsx.py`，而新项目实际调用的是
     `tcgen/xlsx.py:add_pies`——那份没改，新项目跑起来照旧中一次。

**用 AST 判定，不做文本 grep。** 第一版是文本匹配，结果 13 处几乎全是误报：
  - `"P1"` 是**优先级值**（P0/P1/P2/P3），不是饼图格位 P1；
  - `TITLE_META_RX` 出现在项目文件里，恰恰是**正确的 import 复用**；
  - `chart-create` 命中的是薄封装自己的文档字符串。
一个会误报的检查很快就没人看了——所以这里只认三种「真的抄了一份」的形态：
  A. 自己调 `PieChart()` 建图（该走 `tcgen.xlsx.add_pies`）
  B. 自己拼 `chart-create` CLI 调用（该走 `tcgen.feishu.rebuild_charts`）
  C. 自己**赋值定义**了共享常量／格位表（该 import，不是抄一份）
引用和 import 一律不算违例——那正是我们要的。
"""
import ast
import io
import os
import re

#: 只能由 tcgen 定义的常量：项目文件里出现 `X = ...` 即为抄了一份
COPIED_CONSTS = {
    'TITLE_META_RX': 'tcgen.audit',
    'TTYPE_COVER': 'tcgen.audit',
    'TECH_TTYPE_OK': 'tcgen.audit',
    'CHART_TILES': 'tcgen.feishu.CHART_TILES',
}

#: 格位形如 J16/P31：列 J 或 P + **两位**行号。
#: 两位是关键——优先级只有 P0..P3 一位数字，这样才不会把 'P1' 误判成格位。
_TILE_RX = re.compile(r'^[JP]\d{2}$')


def _docstrings(tree):
    """收集所有文档字符串节点 id，避免把「说明文字」判成代码。"""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            body = getattr(node, 'body', None) or []
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def _is_tile_tuple(node):
    """判断一个赋值右值是不是饼图格位表（≥3 个形如 J16/P31 的字符串）。"""
    if not isinstance(node, (ast.Tuple, ast.List)):
        return False
    vals = [e.value for e in node.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return len(vals) >= 3 and sum(bool(_TILE_RX.match(v)) for v in vals) >= 3


def scan_duplicates(project_dir='.', skip=('_boot.py',)):
    """返回 [(文件名, 违例形态, 该去哪里拿)]；空列表 = 项目侧都是薄封装。

    只看目录当层，不递归——数据层模块也在同一层，够用且不会误伤 site-packages。
    """
    found = []
    for fn in sorted(os.listdir(project_dir)):
        if not fn.endswith('.py') or fn in skip:
            continue
        path = os.path.join(project_dir, fn)
        if not os.path.isfile(path):
            continue
        src = io.open(path, encoding='utf-8', errors='replace').read()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        docs = _docstrings(tree)
        hits = []
        for node in ast.walk(tree):
            # A. 自己建饼图
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == 'PieChart':
                hits.append(('自己调 PieChart() 建图', 'tcgen.xlsx.add_pies'))
            # B. 自己拼 chart-create CLI（排除文档字符串里的提及）
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and id(node) not in docs and 'chart-create' in node.value:
                hits.append(('自己拼 chart-create 调用',
                             'tcgen.feishu.rebuild_charts'))
            # B2. 自己拼画板推送 CLI。`--overwrite` 会清空画板全部节点，
            # 手写一份必然漏掉「先备份」与「推完强制回读复验」，而漏掉复验的后果
            # 正是实测踩过的「本地重建成功就宣称导图已更新，线上还停在上一版」。
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and id(node) not in docs \
                    and ('whiteboard +update' in node.value
                         or 'whiteboard +export' in node.value):
                hits.append(('自己拼 whiteboard CLI 调用',
                             'tcgen.board.push / read / diff'))
            # C. 自己赋值定义共享常量／格位表
            elif isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id in COPIED_CONSTS:
                        hits.append(('自己定义 %s' % tgt.id,
                                     COPIED_CONSTS[tgt.id]))
                    elif isinstance(tgt, ast.Name) and _is_tile_tuple(node.value):
                        hits.append(('自己写死格位表 %s' % tgt.id,
                                     'tcgen.feishu.CHART_TILES'))
        for h in sorted(set(hits)):
            found.append((fn,) + h)
    return found


def report(project_dir='.'):
    """打印复用检查结果，返回违例条数（0 = 通过）。"""
    bad = scan_duplicates(project_dir)
    if not bad:
        print('复用检查: OK 项目侧无重复实现')
        return 0
    print('复用检查: 发现 %d 处重复实现（应改为 import 复用）' % len(bad))
    for fn, what, where in bad:
        print('    %-22s %-26s -> 改用 %s' % (fn, what, where))
    print('    理由: 两份实现只要差一个字就是永久假差异；skill 改了这里不会跟着改。')
    return len(bad)
