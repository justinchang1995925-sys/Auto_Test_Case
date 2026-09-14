# -*- coding: utf-8 -*-
"""专项测试用例表 + 专项数据采集表 —— 项目数据层，每个新项目重写本文件。

专项 = 需要 N 次采样统计指标的测试（成功率、误差、时长、长稳等）。
每个被专项覆盖的 REQ 还必须在普通主表里有 ≥1 条功能可用性用例
（只验功能走通、不判指标），否则门禁「专项REQ配套功能用例齐全」不通过。

采样次数 N 与指标目标值未确定时，用例标 Blocked，解除条件写明
「确认 XX 指标目标值与采样量」，不自拟数值。

本期无专项时：build.py 里传 spec=None。
"""

SP_HEADERS = ['用例序号', '优先级', '专项类型', '测试标题', '关联需求',
              '指标与目标值', '采样量N', '前置条件', '执行方法', '判定规则']

SP_ROWS = [
    ('TC-SP-PERF-001', 'P1', '性能专项', '单次操作响应时长采样', 'REQ-003',
     '响应时长 < 2s', 'N=30', '环境已就绪，无其他负载',
     '连续触发30次操作，每次记录从点击到反馈可见的时长',
     'P95 < 2s 且最大值 < 3s 判定通过；任一超限记为不达标'),
]

SPD_HEADERS = ['用例序号', '采样序号', '测量值', '是否达标', '异常现象', '备注']

SP_ROWS.append(
    # 资源观测专项项（门禁 19：有专项测试即强制）。
    # **独立一条，不与上面的专项项合并**；操作步骤依附既有专项运行，不另造工况。
    # 合格阈值写「来源与口径」而非具体数字——不同项目硬件不同，写死会把结论带偏。
    ('TC-SP-RES-001', 'P1', '资源观测专项', '专项运行期 CPU 与内存资源健康度',
     'REQ-005',
     'CPU：整机/实时核峰值/隔离核/温度/频率；内存：可用/匿名页/承诺量/'
     '不可回收slab/页表/CMA/OOM计数器。阈值取本机 sched_rt_*、'
     'trip_point_0_temp、/proc/meminfo，不写死数值',
     'N=与依附专项同长（1Hz）',
     '已启动 TC-SP-PERF-001；采集通道就绪；采集器已自证开销（每样本 0 fork）',
     '在 TC-SP-PERF-001 执行期间同步采集，全程不中断被测流程；'
     '1Hz 采样，按服务 cgroup 归因',
     '三类判定：①瞬时越界（隔离核被侵占/温度触降频点/可用内存过低/CMA将耗尽）；'
     '②趋势——回归斜率与前后段中位数变化率**同向越界**才判泄漏（只看回归会被'
     '缓存"先涨后平"和孤立尖峰骗过）；③状态量——OOM 计数器变化即判失效'),
)

# 采集表按 N 预留空行，执行时填写；此处给出前 3 行示例
SPD_ROWS = [
    ('TC-SP-PERF-001', 1, '', '', '', '待执行'),
    ('TC-SP-PERF-001', 2, '', '', '', '待执行'),
    ('TC-SP-PERF-001', 3, '', '', '', '待执行'),
    ('TC-SP-RES-001', 1, '', '', '', '待执行（逐样本原始值留档，指标可复算）'),
    ('TC-SP-RES-001', '【汇总】', '瞬时越界数/趋势斜率与中位数率/OOM计数器变化',
     '待填', '采集器开销待填', '结论：PASS/WARN/FAIL + 依据'),
]

#: 资源观测交付信息 —— 传给 xlsx.build(res=...)，供门禁 19 核对。
#: 执行完把 conclusion 改成实测结论；只采不判视为未完成。
RES = dict(
    tc='TC-SP-RES-001', req='REQ-005', tp='TP-S-001',
    attached=['TC-SP-PERF-001'],
    cpu_keys=['cpu_all', 'cpu_rt_max', 'cpu_isol_max', 'temp', 'freq'],
    mem_keys=['mem_avail', 'anon', 'committed', 'slab_unreclaim',
              'pagetables', 'cma_free', 'oom_kill', 'refault'],
    verdict_kinds=['瞬时', '趋势', '状态'],
    threshold_sources=['sched_rt_runtime_us/sched_rt_period_us',
                       'thermal_zone*/trip_point_0_temp', '/proc/meminfo'],
    hardcoded_thresholds=[],          # 非空即门禁不通过
    # 尚未执行时如实标 Blocked + 写解除条件；**不要填假的 PASS 去骗门禁**。
    # 执行后改成实测结论（PASS/WARN/FAIL）。
    conclusion='Blocked',
    unblock='TC-SP-PERF-001 执行完毕并完成资源数据采集后出结论',
    agent_cost='采集器 CPU 3.0% / RSS 10 MB / 自身 fork 0 次',
    mixed_into=[],                    # 资源指标混进了哪些既有专项用例，非空即违规
)
