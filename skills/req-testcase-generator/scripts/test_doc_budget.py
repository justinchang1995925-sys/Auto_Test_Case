# -*- coding: utf-8 -*-
"""文档体量预算回归 —— 守「skill 还能继续加规则」这件事。

存在理由：`SKILL.md` 每次调用都要整份进上下文。它膨胀到一定程度，模型读不完
前面的强制规则，**先前那些门禁就等于不存在了**——规则越加越多，反而越不生效。
所以体量是有效性问题，不是风格问题，必须有机器可算的上限。

本测试不联网、不依赖 lark-cli，纯文件统计。

为什么把预算定在这个数：
- 触发本 skill 时 `SKILL.md` 必然全量载入，其余四份按需加载。
- 中文约 1.3 字符/token，故 45000 字符 ≈ 34.6k token。当前 43982 字符（≈33.8k），
  留约 1000 字符余量给下一条规则的**指针**（不是正文）。
- 想加正文时不是抬高这个数，而是按 SKILL.md「新增规则该写到哪」把正文放进
  pipeline.md / templates.md，本文件只留一行。抬预算是最后手段，且必须在
  提交信息里说明为什么这条规则非留在 SKILL.md 不可。
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # skill 目录
sys.path.insert(0, HERE)

from tcgen import plat                                # noqa: E402

plat.force_utf8_stdout()

#: 每份文档的字符上限。SKILL.md 卡得最紧——它是唯一「每次都全量载入」的。
BUDGET = {
    'SKILL.md': 45000,
    'templates.md': 60000,
    'pipeline.md': 32000,
    'exception-library.md': 20000,
    'doc-ingest.md': 8000,
}

#: 全套上限：五份加起来的字符数。防「总量失控但每份都刚好不超」。
TOTAL_BUDGET = 160000


def _read(name):
    with io.open(os.path.join(ROOT, name), encoding='utf-8') as fh:
        return fh.read()


def t_each_within_budget():
    """每份文档不得超各自预算。"""
    bad = []
    for name, cap in sorted(BUDGET.items()):
        n = len(_read(name))
        if n > cap:
            bad.append('%s %d > %d（超 %d，约 %.1fk token）'
                       % (name, n, cap, n - cap, (n - cap) / 1300.0))
    assert not bad, '；'.join(bad) + \
        '。按 SKILL.md「新增规则该写到哪」把正文移出，本文件只留指针'
    return '5 份均在预算内'


def t_total_within_budget():
    """全套总量不得超顶。"""
    n = sum(len(_read(f)) for f in BUDGET)
    assert n <= TOTAL_BUDGET, \
        '全套 %d > %d 字符（约 %.1fk token）' % (n, TOTAL_BUDGET, n / 1300.0)
    return '全套 %d 字符（约 %.1fk token），余 %d' % (n, n / 1300.0,
                                                  TOTAL_BUDGET - n)


def t_skill_is_smallest_growing():
    """SKILL.md 必须比 templates.md 小。

    这条是**结构判据**而非体量判据：templates.md 是「照着抄」的模板集，天然会长；
    SKILL.md 是「动手前必读」的规则集，一旦它反超模板集，说明正文又堆回主文件了。
    """
    s, t = len(_read('SKILL.md')), len(_read('templates.md'))
    assert s < t, ('SKILL.md(%d) 已超过 templates.md(%d)：'
                   '说明规则正文在往主文件堆，应按放置规则移出' % (s, t))
    return 'SKILL.md(%d) < templates.md(%d)' % (s, t)


def t_placement_rule_present():
    """放置规则本身必须在 SKILL.md 里，否则后来人不知道往哪放。"""
    s = _read('SKILL.md')
    need = ['新增规则该写到哪', '门禁正文只写', '能进代码的不要留在文档里']
    miss = [k for k in need if k not in s]
    assert not miss, 'SKILL.md 缺放置规则要点: %s' % ','.join(miss)
    return '放置规则在位（%d 项要点）' % len(need)


def t_gate_body_not_in_skill():
    """门禁正文里不许再出现长篇踩坑叙述。

    判据：单条门禁（`^NN. ` 开头到下一条）不得超过 2000 字符。
    超了说明踩坑经过又写回主文件了——它该进 pipeline.md「易错点」。
    2000 的来处：门禁 18 压缩后 1153 字符已含牵动表+三条纪律，是合理上限的实测参照。
    """
    import re
    lines = _read('SKILL.md').splitlines(True)
    idx = [i for i, l in enumerate(lines) if re.match(r'^\d+\. \*\*', l)]
    bad = []
    for k, i in enumerate(idx):
        j = idx[k + 1] if k + 1 < len(idx) else len(lines)
        # 边界必须**遇到下一个标题就止**，不能只看「下一个编号项」：
        # 最后一条门禁后面紧跟「放行条件」等章节，只按编号项算会把整节吞进来，
        # 把 977 字符的门禁 19 算成 4447 而误报（首版实测踩过）。
        # 误报的检查很快就没人看，反过来削弱其他门禁的可信度。
        for m in range(i + 1, j):
            if re.match(r'^#{2,4} ', lines[m]):
                j = m
                break
        # 只看「硬门禁」区那些编号项：以数字+**开头且含「检查」「扫描」「门禁」
        head = lines[i][:60]
        if not any(w in head for w in ('检查', '扫描', '矩阵', '完整')):
            continue
        n = sum(len(x) for x in lines[i:j])
        if n > 2000:
            bad.append('%s… %d 字符' % (head.strip()[:34], n))
    assert not bad, ('门禁正文过长，踩坑经过应移进 pipeline.md: %s'
                     % '；'.join(bad))
    return '门禁正文均 ≤2000 字符'


def main():
    g = globals()
    ts = [g[k] for k in sorted(g) if k.startswith('t_') and callable(g[k])]
    bad = 0
    for t in ts:
        try:
            print('  PASS  %-30s %s' % (t.__name__, t()))
        except Exception as e:                        # noqa: BLE001
            bad += 1
            print('  FAIL  %-30s %s: %s' % (t.__name__, type(e).__name__, e))
    print('文档体量预算回归: %d/%d 通过' % (len(ts) - bad, len(ts)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
