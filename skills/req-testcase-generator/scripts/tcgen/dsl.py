# -*- coding: utf-8 -*-
"""用例单一事实源的数据模型（通用，与项目无关）。

每条用例自带 REQ/TP/覆盖类型/风险/状态，主表·附表·追溯矩阵全部从此派生，
结构上杜绝「一对多坍缩」与「深度单向缺口」——这是 skill 审计三铁律的落地基础。

项目侧用法：
    from tcgen.dsl import add
    add("TC-XXX-001","P0","标题","功能测试",
        ["1. 前置"], ["1. 步骤"], ["1. 预期"],
        "REQ-001","TP-F-001","正向","高","风险依据","场景法","测试数据")
"""

CASES = []


def C(tc, pri, title, ttype, pre, steps, exp, req, tp, cover,
      risk, rbasis, tech, data, status="Ready", unblock="无", remark="-"):
    # 反模式硬约束：步骤与预期必须 1:1，构建期即失败，不留到审计阶段
    assert len(steps) == len(exp), f"{tc} 步骤{len(steps)}≠预期{len(exp)}"
    return dict(tc=tc, pri=pri, title=title, ttype=ttype, pre=pre, steps=steps,
                exp=exp, req=req, tp=tp, cover=cover, risk=risk, rbasis=rbasis,
                tech=tech, data=data, status=status, unblock=unblock, remark=remark)


def add(*a, **k):
    CASES.append(C(*a, **k))


def reset():
    del CASES[:]


# ---- 优先级 → 定级依据基准 / 风险等级（附表两列由此派生，保证口径一致）----
PRI_REASON = {
    'P0': '核心主流程/安全/资损,失败即阻塞发布',
    'P1': '重要分支/高频路径,影响体验或转化',
    'P2': '次要/边界/一般异常,影响有限',
    'P3': '低频便利项,可延后',
}
PRI_RISK = {'P0': '高', 'P1': '高', 'P2': '中', 'P3': '低'}

# ---- 维度映射（门禁：TP 维度与用例维度错配）----
# 功能/接口/反向/异常/边界 同属功能维度，不算错配
TT2DIM = {'功能测试': '功能', '接口测试': '功能', '反向测试': '功能',
          '异常测试': '功能', '边界测试': '功能',
          '性能测试': '性能', '稳定性测试': '稳定性', '兼容性测试': '兼容性',
          '安全测试': '安全', '用户体验测试': '用户体验'}
PFX2DIM = {'TP-F': '功能', 'TP-P': '性能', 'TP-S': '稳定性',
           'TP-C': '兼容性', 'TP-SEC': '安全', 'TP-UX': '用户体验'}
# TP-SEC 必须先匹配，否则 TP-S 前缀会吞掉它
DIM_PREFIX_ORDER = ('TP-SEC', 'TP-F', 'TP-P', 'TP-S', 'TP-C', 'TP-UX')


def tp_dim(tp):
    for p in DIM_PREFIX_ORDER:
        if tp.startswith(p):
            return PFX2DIM[p]
    return '?'


REQ_HEADERS = ['REQ-ID', '需求描述', '来源文档', '来源章节/段落', '类型',
               '可测性', '覆盖状态', '备注']
MAIN_HEADERS = ['用例序号', '优先级（P0-P3）', '测试标题', '测试类型', '前置条件',
                '操作步骤', '预期结果', '测试结果（PASS/FAIL）', '备注']
EXT_HEADERS = ['关联需求/方案条目', '关联测试点', '用例序号', '设计技法', '测试数据',
               '风险等级', '风险评估依据', '优先级评估', '用例状态', '解除条件', '备注']
TR_HEADERS = ['REQ-ID', 'TP-ID', 'TC-ID', '覆盖类型', '备注']
