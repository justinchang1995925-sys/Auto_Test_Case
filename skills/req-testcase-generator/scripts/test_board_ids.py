# -*- coding: utf-8 -*-
"""画板同步的 ID 识别回归 —— 守 tcgen.board 的比对完整性。

存在理由：这个正则连续漏报过两次，且**两次都表现为「差异 0，看着通过」**——
本地与线上用同一个正则，漏掉的节点两边同时消失，比对自然报一致。
漏报比误报危险得多：误报会有人来修，漏报没人知道。

1. 只吃单段 ID（`TC-[A-Z]+-\\d+`）→ `TC-SP-RES-001`/`TC-EX-ESTOP-001` 这类
   两段式整批落在比对之外，实测漏 25 个 TC 节点。
2. 尾部不允许字母（`-\\d+`）→ `TC-STATE-008B` 被截成 `TC-STATE-008`，
   与同号用例撞键后被覆盖，实测漏 1 条。

不联网，纯字符串。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcgen import plat                              # noqa: E402

plat.force_utf8_stdout()

from tcgen import board as B                        # noqa: E402

# (mermaid 行, 期望解析出的 ID)；None = 期望不匹配
SAMPLES = [
    ('TP_F_001["TP-F-001 保存制作流程"]', 'TP-F-001'),
    ('TP_S_007["TP-S-007 专项运行期CPU与内存资源健康度"]', 'TP-S-007'),
    ('TP_SEC_101["TP-SEC-101 急停触发后整机停止"]', 'TP-SEC-101'),
    ('TC_SAVE_001["TC-SAVE-001 [正向·P0] 已选预设时保存生效"]', 'TC-SAVE-001'),
    # 两段式：坑 1
    ('TC_SP_RES_001["TC-SP-RES-001 [专项·P1] 资源健康度"]', 'TC-SP-RES-001'),
    ('TC_SP_STAB_001["TC-SP-STAB-001 [专项·P0] 连续制作成功率"]',
     'TC-SP-STAB-001'),
    ('TC_EX_ESTOP_001["TC-EX-ESTOP-001 [功能安全-触发·P0] 急停"]',
     'TC-EX-ESTOP-001'),
    # 字母后缀：坑 2
    ('TC_STATE_008B["TC-STATE-008B [异常·P1] 连续追问不释放动作"]',
     'TC-STATE-008B'),
    # 非 TP/TC 节点不该被当成用例节点
    ('DIM_FUNC["功能"]', None),
    ('MOD_SAVE["保存与生效"]', None),
]


def t_ids_parsed():
    """每种真实 ID 形态都能被完整解析出来。"""
    bad = []
    for line, want in SAMPLES:
        got = B._MMD_NODE.findall(line)
        gid = None
        if got:
            gid = list(B._ids(got).keys())
            gid = gid[0] if gid else None
        if gid != want:
            bad.append('%s -> 得到 %r 期望 %r' % (line[:34], gid, want))
    assert not bad, '；'.join(bad)
    return '%d 种 ID 形态全部正确' % len(SAMPLES)


def t_suffix_not_collapsed():
    """`TC-STATE-008` 与 `TC-STATE-008B` 必须是两个键，不能撞成一个。"""
    texts = ['TC-STATE-008 [正向·P0] 同测试点主场景',
             'TC-STATE-008B [异常·P1] 制作中被连续追问也不释放动作']
    ids = B._ids(texts)
    assert len(ids) == 2, '带字母后缀的编号被折叠了: %s' % list(ids)
    assert 'TC-STATE-008B' in ids, '后缀 ID 丢失: %s' % list(ids)
    return '008 与 008B 各自独立成键'


def t_two_segment_counted():
    """两段式 ID 必须计入 TC 统计，不能整批消失。"""
    texts = ['TC-SP-RES-001 x', 'TC-EX-ESTOP-001 y', 'TC-SAVE-001 z']
    ids = B._ids(texts)
    n_tc = sum(1 for k in ids if k.startswith('TC-'))
    assert n_tc == 3, '两段式 ID 被漏掉，只数到 %d' % n_tc
    return '两段式与单段式都计入'


def t_diff_shape():
    """diff() 的返回结构含比对所需的全部字段（少字段会让调用方静默少查一项）。"""
    need = ('online_total', 'online_tp', 'online_tc', 'local_tp', 'local_tc',
            'only_local', 'only_online', 'changed', 'n_diff')
    import inspect
    src = inspect.getsource(B.diff)
    miss = [k for k in need if k not in src]
    assert not miss, 'diff() 未返回: %s' % ','.join(miss)
    return '返回字段齐全（%d 项）' % len(need)


def main():
    g = globals()
    ts = [g[k] for k in sorted(g) if k.startswith('t_') and callable(g[k])]
    bad = 0
    for t in ts:
        try:
            print('  PASS  %-28s %s' % (t.__name__, t()))
        except Exception as e:                       # noqa: BLE001
            bad += 1
            print('  FAIL  %-28s %s: %s' % (t.__name__, type(e).__name__, e))
    print('画板 ID 识别回归: %d/%d 通过' % (len(ts) - bad, len(ts)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
