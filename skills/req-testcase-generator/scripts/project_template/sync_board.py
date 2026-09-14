# -*- coding: utf-8 -*-
"""飞书画板（思维导图）同步 —— 薄封装，实现在 skill 的 `tcgen.board` 里。

**不要在这里抄一份推送逻辑。** 与 `charts_feishu.py` 同样的道理：抄一份之后
skill 改了备份/复验口径，这里照旧跑老逻辑，跑一次就把问题造回来。
本文件只该有三样东西：画板 token、本地 mmd 路径、备份目录。

用法
----
    python sync_board.py diff      # 只比对，不改线上；有差异退出码 1
    python sync_board.py push      # 备份 -> 推送 -> 强制回读复验
    python sync_board.py preview   # 导出预览图，人工过一眼排版

**为什么必须有这个脚本**
硬门禁 18 第一条是「本地重建 ≠ 在线已更新」。表格侧有 sync_feishu.py 顶着，
画板侧原先什么都没有——实测就发生过本地 .drawio/.mmd 重建成功便宣称
「思维导图已更新」，而线上画板还停在上一版。缺的不是记性，是这个脚本。

画板 token 怎么找：画板通常嵌在某篇飞书文档里，
    lark-cli docs +fetch --doc <文档ID> --doc-format xml
输出里的 `<whiteboard token="...">` 就是。找到后填进下面 BOARD_TOKEN，不要每次翻文档。
"""
import os
import sys

import _boot

_boot.setup()

from tcgen import board, plat                        # noqa: E402

plat.force_utf8_stdout()

# ============ 项目配置（每个项目只改这一块）============
#: 画板 token（见模块 docstring 的找法）。留空则脚本报错并给出查找命令。
BOARD_TOKEN = ''
#: 本地 mermaid 思维导图（飞书画板不认 .drawio，只认 mermaid/DSL）
MMD_PATH = '示例项目测试点.mmd'
#: 线上内容备份目录。--overwrite 会清空画板，故每次 push 前必存一份
BACKUP_DIR = '.board_backup'
#: 预览图落盘位置
PREVIEW_PATH = os.path.join('.board_check', 'whiteboard_preview.jpg')
#: 复验层级时要核对的关键节点（挂错父节点时「节点存在」也不算通过）
CHECK_NODES = ()
# =====================================================


def _need_token():
    if BOARD_TOKEN:
        return
    print('请先在本文件里填 BOARD_TOKEN。查找方式：\n'
          '  lark-cli docs +fetch --doc <文档ID> --doc-format xml\n'
          '输出里 <whiteboard token="..."> 即是。')
    sys.exit(2)


def _show(v):
    print('线上 TP/TC: %d/%d   本地 TP/TC: %d/%d   线上节点总数 %d'
          % (v['online_tp'], v['online_tc'], v['local_tp'], v['local_tc'],
             v['online_total']))
    for key, label in (('only_local', '本地有线上无(待推)'),
                       ('only_online', '线上有本地无(疑他人改动或已删)'),
                       ('changed', '同ID文本不一致')):
        ids = v[key]
        if ids:
            print('  %s %d: %s' % (label, len(ids), ', '.join(ids[:12])
                                   + ('…' if len(ids) > 12 else '')))
            if key == 'changed':
                for k in ids[:3]:
                    print('      %s\n        线上=%r\n        本地=%r'
                          % (k, v['_online'][k][:70], v['_local'][k][:70]))
    print('差异合计: %d' % v['n_diff'])


def cmd_diff():
    _need_token()
    v = board.diff(BOARD_TOKEN, MMD_PATH)
    _show(v)
    # 「线上有本地无」要单独提醒：可能是别人在线上加的节点，
    # push 会用 --overwrite 抹掉它。门禁18 要求这类差异先报人、不得静默覆盖。
    if v['only_online']:
        print('\n[!] 线上存在本地没有的节点。push 用 --overwrite 会抹掉它们。\n'
              '    先确认这些是本地已删除的旧节点，还是他人在线上的编辑。')
    return 1 if v['n_diff'] else 0


def cmd_push():
    _need_token()
    before = board.diff(BOARD_TOKEN, MMD_PATH)
    if before['n_diff'] == 0:
        print('线上与本地已一致，无需推送。')
        return 0
    print('推送前差异：')
    _show(before)
    r = board.push(BOARD_TOKEN, MMD_PATH, BACKUP_DIR)
    print('\n备份: %s' % r['backup'])
    if not r['ok']:
        print('推送或复验未通过: %s' % (r['error'] or ''))
        if r['verify']:
            _show(r['verify'])
        return 1
    print('推送成功，回读复验：')
    _show(r['verify'])
    # 层级复核：节点在画板上 ≠ 挂在正确父节点下
    if CHECK_NODES:
        nodes, _ = board.read(BOARD_TOKEN)
        for needle in CHECK_NODES:
            for chain in board.parent_chain(nodes, needle):
                print('  层级: ' + ' <- '.join(s[:36] for s in chain))
    return 0


def cmd_preview():
    _need_token()
    p = board.preview(BOARD_TOKEN, PREVIEW_PATH)
    print('预览图: %s' % (p or '导出失败'))
    return 0 if p else 1


def main():
    cmds = {'diff': cmd_diff, 'push': cmd_push, 'preview': cmd_preview}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print('用法: python sync_board.py {diff|push|preview}')
        return 2
    return cmds[sys.argv[1]]()


if __name__ == '__main__':
    sys.exit(main())
