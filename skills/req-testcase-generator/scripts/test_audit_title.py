# -*- coding: utf-8 -*-
"""tcgen.audit 门禁 A/B 与软提示 C 的回归测试。

管道改动后跑：python test_audit_title.py
覆盖：
  A 标题写「验证方法」而非「场景+预期」 —— 硬门禁，须零误报
  B 覆盖类型 ↔ 测试类型 矛盾           —— 硬门禁，须放过 EX 交叉的合规写法
  C 设计技法 ↔ 测试类型 相容性         —— 软提示，不进 gates()

存在理由：project_template 的样例数据全部合规，跑 build.py 时这三项永远为 0，
等于新门禁没被执行。本文件专门造违例数据把它们跑到。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcgen import plat  # noqa: E402

plat.force_utf8_stdout()   # Ubuntu 在 LC_ALL=C 下 print 中文会崩
from tcgen import audit  # noqa: E402

REQ = [('REQ-001', '示例需求', '软件PRD', '4.1.1 F01', '功能', '可测', '待覆盖', '-')]


def mk(tc, title, ttype, cover, tech='场景法', req='REQ-001', tp='TP-F-001'):
    return dict(tc=tc, pri='P2', title=title, ttype=ttype, pre=['1. 前置'],
                steps=['1. 步骤'], exp=['1. 预期'], req=req, tp=tp, cover=cover,
                risk='中', rbasis='依据', tech=tech, data='-', status='Ready',
                unblock='无', remark='-')


def run(cases):
    return audit.compute(cases=cases, req_src=REQ)


def t_title_meta_catches():
    """标题以「手段介词+元动词」收尾必须被抓到（真实踩过的那条）。"""
    bad = [
        '试听中不可取消由再次点击验证',      # 真实缺陷原文
        '断网后重连由心跳包检查',
        '配置生效通过重启验证',
        '权限隔离用越权请求校验',
    ]
    for t in bad:
        a = run([mk('TC-X-001', t, '功能测试', '正向')])
        assert a['title_meta_bad'] == ['TC-X-001'], '漏检: %r -> %s' % (
            t, a['title_meta_bad'])
    return '4 条元层面标题全部抓到'


def t_title_meta_no_false_positive():
    """元动词作名词或在句中时不得误报——误报会让人习惯性忽略告警。"""
    ok = [
        '用验证码登录成功',
        '验证码错误时提示重新输入',
        '通过校验和比对确认文件完整',
        '以最大音量播放不失真',
        '通过接口批量导入成功',
        '用离线包升级后配置保留',
        '试听中反复点击该语音或其他按钮均不中断播放',   # 修好后的写法
        '急停解除需旋钮复位并二次确认后才退出急停态',
        '保存提示需人工检查语音动作配置',
    ]
    for t in ok:
        a = run([mk('TC-X-001', t, '功能测试', '正向')])
        assert not a['title_meta_bad'], '误报: %r' % t
    return '9 条正常标题零误报'


def t_cover_mismatch_catches():
    """功能维度内三个专用测试类型与覆盖类型矛盾时必须抓到。"""
    for ttype, wrong in (('反向测试', '边界'), ('边界测试', '异常'),
                         ('异常测试', '反向')):
        a = run([mk('TC-X-001', '条件下行为符合预期', ttype, wrong)])
        assert a['cover_bad'] == ['TC-X-001'], '漏检 %s+%s' % (ttype, wrong)
    # 正确配对不报
    for ttype, right in (('反向测试', '反向'), ('边界测试', '边界'),
                         ('异常测试', '异常')):
        a = run([mk('TC-X-001', '条件下行为符合预期', ttype, right)])
        assert not a['cover_bad'], '误报 %s+%s' % (ttype, right)
    return '3 组矛盾抓到、3 组正确放过'


def t_cover_allows_cross_dimension():
    """EX 交叉的合规写法不得被拦。

    exception-library.md 明文：后果为「数据不一致」→ 归稳定性维度、
    测试类型 `稳定性测试`、覆盖类型用 `异常`/`反向`。把稳定性/性能/兼容性测试
    也绑定覆盖类型，就会把这种写法误判成违例（实测拦到 TC-EX-DATA-001）。
    """
    legit = [
        mk('TC-EX-1', '埋点写入中触发急停不产生半条脏数据', '稳定性测试', '异常',
           tech='异常注入(EX-001)', tp='TP-S-006'),
        mk('TC-EX-2', '运动中触发急停后可恢复继续', '稳定性测试', '反向',
           tech='异常注入(EX-001)', tp='TP-S-007'),
        mk('TC-P-1', '单次操作响应低于阈值', '性能测试', '性能', tp='TP-P-001'),
        mk('TC-C-1', '目标机型上功能可用', '兼容性测试', '兼容性', tp='TP-C-001'),
    ]
    a = run(legit)
    assert not a['cover_bad'], '误拦合规跨维度写法: %s' % a['cover_bad']
    return '跨维度类型（稳定性/性能/兼容性）不被绑定'


def t_tech_warn_is_soft():
    """C 只作软提示：能列出待确认项，但不得进入 gates() 阻断交付。"""
    a = run([mk('TC-X-001', '边界值处理正确', '边界测试', '边界', tech='状态迁移')])
    assert a['tech_warn'] == ['TC-X-001'], '软提示未命中: %s' % a['tech_warn']
    names = [n for n, _ in audit.gates(a)]
    assert not any('技法' in n for n in names), 'C 不应出现在硬门禁里: %s' % names
    assert all(ok for n, ok in audit.gates(a)
               if n in ('标题写验证方法数=0', '覆盖类型与测试类型矛盾数=0')), \
        '软提示不应带崩硬门禁'
    return '软提示命中且未进硬门禁'


def t_gates_wired():
    """A/B 必须出现在 gates() 里，且违例时判为未通过。"""
    a = run([mk('TC-X-001', '功能生效由重启验证', '反向测试', '边界')])
    g = dict(audit.gates(a))
    for k in ('标题写验证方法数=0', '覆盖类型与测试类型矛盾数=0'):
        assert k in g, '门禁未接线: %s' % k
        assert g[k] is False, '违例却判通过: %s' % k
    notes = audit.gate_notes(a)
    for k in ('标题写验证方法数=0', '覆盖类型与测试类型矛盾数=0'):
        assert k in notes and 'TC-X-001' in notes[k], '自查回执缺违例ID: %s' % k
    return 'A/B 已接线，违例判未通过且回执列出 ID'


def main():
    ts = [t_title_meta_catches, t_title_meta_no_false_positive,
          t_cover_mismatch_catches, t_cover_allows_cross_dimension,
          t_tech_warn_is_soft, t_gates_wired]
    bad = 0
    for t in ts:
        try:
            print('  PASS  %-30s %s' % (t.__name__, t()))
        except AssertionError as e:
            bad += 1
            print('  FAIL  %-30s %s' % (t.__name__, e))
    print('标题/类型门禁回归: %d/%d 通过' % (len(ts) - bad, len(ts)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
