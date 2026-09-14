# -*- coding: utf-8 -*-
"""飞书画板同步层（思维导图）—— 与 feishu.py 对表格做的事一一对应。

**为什么必须有这一份**
表格侧有 `sync_feishu.py` 可跑，画板侧原先只有 `drawio.py` 注释里一句「该怎么手动做」。
结果实测发生过：本地 `.drawio`/`.mmd` 重建成功就宣称「导图已更新」，而线上画板
停在上一版——硬门禁 18 第一条「本地重建 ≠ 在线已更新」被违反，恰恰是因为
**画板这条链路没有可执行的脚本，全靠人记得**。补齐它，让两条链路对称。

三件事，与表格侧同构：
    read()   回读线上节点（对应 feishu.read_sheet）
    diff()   本地 mmd 与线上节点比对（对应 feishu.diff_sheets）
    push()   推送 + 强制复验（对应 csv-put + diff 复查）

**`--overwrite` 会清空画板全部节点**，故 push() 内置「先备份再推」，
备份路径随返回值给出；不提供「不备份」的选项。
"""
import json
import os
import re
import subprocess
import time

DEFAULT_LARK_CLI = os.path.expanduser(
    '~/AppData/Roaming/npm/lark-cli.cmd')

#: 回读重试：画板 push 后有处理延迟，立刻读会得到
#: `This whiteboard is not ready yet.`（code 2890007）。等待按次递增。
RETRY_TIMES = 5
RETRY_WAIT_S = 3

# 本地 mermaid mindmap 里节点文本的形态：`ID["TP-F-001 描述"]`
# ID 段数不固定：TP-F-001 是一段，TC-SP-RES-001 / TC-EX-ESTOP-001 是两段。
# 写死单段（`TC-[A-Z]+-\d+`）会让两段式 ID 整批落在比对之外——实测漏掉 25 个
# TC 节点，而本地与线上用同一个正则，于是「差异 0」看着通过，实则漏报。
# 尾部允许字母后缀：项目里真实存在 TC-STATE-008B 这种编号，若只吃 `-\d+`，
# 它会被截成 TC-STATE-008 而与同号用例撞键、在比对里被覆盖掉（实测漏 1 条）。
_ID_RX = r'(?:TP|TC)-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d+[A-Z]*'
_MMD_NODE = re.compile(r'\["(' + _ID_RX + r'[^"]*)"\]')


def _run(args, lark_cli=DEFAULT_LARK_CLI):
    """调 lark-cli，返回解析后的 JSON；非 JSON 输出原样塞进 raw。"""
    p = subprocess.run([lark_cli] + args, capture_output=True, text=True,
                       encoding='utf-8')
    out = (p.stdout or '').strip()
    try:
        return json.loads(out)
    except ValueError:
        return {'ok': False, 'raw': out[:400], 'stderr': (p.stderr or '')[:200]}


def _find_nodes(obj):
    """从 export raw 的任意嵌套结构里挖出 nodes 列表。

    不写死路径：lark-cli 的包装层级换过一次，写死 data.nodes 就会静默取到空列表，
    而空列表会让「比对通过」——漏报比误报更糟。
    """
    if isinstance(obj, dict):
        if isinstance(obj.get('nodes'), list):
            return obj['nodes']
        for v in obj.values():
            got = _find_nodes(v)
            if got:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _find_nodes(v)
            if got:
                return got
    return None


def node_text(n):
    """取节点可见文字。两种结构都要认（纯 text 与 elements 富文本）。"""
    t = n.get('text') or {}
    if not isinstance(t, dict):
        return str(t or '').strip()
    s = t.get('text') or ''
    if not s:
        for el in (t.get('elements') or []):
            s += (el.get('text_run') or {}).get('content', '')
    return s.strip()


def read(token, lark_cli=DEFAULT_LARK_CLI, save_to=None):
    """回读线上画板 -> (nodes, 原始 dict)。save_to 非空则把原始 JSON 落盘备查。"""
    # lark-cli 的 --output **只接受相对路径**（绝对路径报
    # "--output must be a relative path"），所以临时文件也得落在 cwd 下的相对目录，
    # 不能用 TEMP 绝对路径。
    tmp = save_to or os.path.join('.board_check',
                                  '_read_%d.json' % int(time.time() * 1000))
    if os.path.isabs(tmp):
        tmp = os.path.relpath(tmp, os.getcwd())
    d = os.path.dirname(tmp)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    # 刚 push 完立刻回读会撞上 `This whiteboard is not ready yet.`（code 2890007）——
    # 画板侧有处理延迟。不重试就会让「推送成功但复验失败」变成常态，
    # 而复验是 push() 唯一的正确性保证，不能因为一次时序抖动就放弃（实测踩过）。
    res = None
    for attempt in range(RETRY_TIMES):
        res = _run(['whiteboard', '+export', '--whiteboard-token', token,
                    '--output-type', 'raw', '--output', tmp, '--overwrite'],
                   lark_cli)
        if os.path.exists(tmp):
            break
        blob = json.dumps(res, ensure_ascii=False)
        if 'not ready' not in blob and '2890007' not in blob:
            break                      # 不是「还没就绪」，重试也没用，直接报
        if attempt < RETRY_TIMES - 1:
            time.sleep(RETRY_WAIT_S * (attempt + 1))    # 递增等待
    if not os.path.exists(tmp):
        raise RuntimeError('回读画板失败: %s' % json.dumps(res, ensure_ascii=False)[:300])
    with open(tmp, encoding='utf-8') as fh:
        raw = json.load(fh)
    if save_to is None:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return (_find_nodes(raw) or []), raw


def local_nodes(mmd_path):
    """从本地 .mmd 抽出 TP/TC 节点文本集合。"""
    with open(mmd_path, encoding='utf-8') as fh:
        return _MMD_NODE.findall(fh.read())


def _ids(texts):
    """节点文本 -> {ID: 文本}，ID 为开头的 TP-xxx/TC-xxx。"""
    out = {}
    for s in texts:
        m = re.match('(' + _ID_RX + ')', s.strip())
        if m:
            out[m.group(1)] = s.strip()
    return out


def diff(token, mmd_path, lark_cli=DEFAULT_LARK_CLI, save_to=None):
    """本地 mmd 与线上画板比对，返回 dict。

    比 ID 集合，也比同 ID 的文本——只比数量会漏掉「改了描述但没增删节点」的改动。
    """
    online_nodes, _ = read(token, lark_cli, save_to=save_to)
    on = _ids(node_text(n) for n in online_nodes)
    loc = _ids(local_nodes(mmd_path))
    only_local = sorted(set(loc) - set(on))
    only_online = sorted(set(on) - set(loc))
    changed = sorted(k for k in (set(loc) & set(on)) if loc[k] != on[k])
    return dict(
        online_total=len(online_nodes),
        online_tp=sum(1 for k in on if k.startswith('TP-')),
        online_tc=sum(1 for k in on if k.startswith('TC-')),
        local_tp=sum(1 for k in loc if k.startswith('TP-')),
        local_tc=sum(1 for k in loc if k.startswith('TC-')),
        only_local=only_local, only_online=only_online, changed=changed,
        n_diff=len(only_local) + len(only_online) + len(changed),
        _local=loc, _online=on,
    )


def push(token, mmd_path, backup_dir, lark_cli=DEFAULT_LARK_CLI,
         idempotent_token=None):
    """备份 -> 推送 -> 回读复验。返回 dict(ok, backup, verify)。

    `--overwrite` 会删掉画板全部现有节点，所以**备份不是可选项**：
    先把线上原样落盘，再推。推完必须复验——门禁 13 要求「写入飞书画板后须回读复验，
    本地 PNG 预览通过不等于画板通过」，两者用的是不同的布局引擎。
    """
    os.makedirs(backup_dir, exist_ok=True)
    stamp = time.strftime('%Y%m%d_%H%M%S')
    backup = os.path.join(backup_dir, 'board_before_%s.json' % stamp)
    read(token, lark_cli, save_to=backup)      # 备份即回读，失败会抛

    args = ['whiteboard', '+update', '--whiteboard-token', token,
            '--input_format', 'mermaid', '--source', '@' + mmd_path,
            '--overwrite']
    if idempotent_token:
        args += ['--idempotent-token', idempotent_token]
    res = _run(args, lark_cli)
    if not res.get('ok'):
        return dict(ok=False, backup=backup, error=res, verify=None)

    v = diff(token, mmd_path, lark_cli)
    return dict(ok=(v['n_diff'] == 0), backup=backup, error=None, verify=v)


def parent_chain(nodes, needle, limit=8):
    """按 mind_map.parent_id 重建某节点的父链，用于核对层级挂对没有。

    门禁 13 要求核对层级，而「节点在画板上」不等于「挂在正确的父节点下」。
    """
    by_id = {n.get('id'): n for n in nodes}
    hits = [n for n in nodes if needle in node_text(n)]
    out = []
    for n in hits:
        chain, cur = [], n
        for _ in range(limit):
            chain.append(node_text(cur) or '(root)')
            pid = (cur.get('mind_map') or {}).get('parent_id')
            if not pid or pid not in by_id:
                break
            cur = by_id[pid]
        out.append(chain)
    return out


def preview(token, out_path, lark_cli=DEFAULT_LARK_CLI):
    """导出预览图，返回路径或 None。人工过一眼排版用。"""
    # 同 read()：--output 只接受相对路径
    if os.path.isabs(out_path):
        out_path = os.path.relpath(out_path, os.getcwd())
    d = os.path.dirname(out_path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    res = _run(['whiteboard', '+export', '--whiteboard-token', token,
                '--output-type', 'preview', '--output', out_path,
                '--overwrite'], lark_cli)
    return out_path if res.get('ok') and os.path.exists(out_path) else None
