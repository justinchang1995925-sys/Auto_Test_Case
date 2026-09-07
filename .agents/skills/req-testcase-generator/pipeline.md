# 交付件构建管道（scripts/tcgen）

> **强制**：Phase 3/4 落地交付件时**必须复用 `scripts/` 下的现成管道**，
> 禁止现场重写 openpyxl 建表、审计集合运算、drawio 拼 XML、飞书格式重建这些代码。
> 现场重写会导致配色、审计口径、列宽规则、图表行号解析逐项漂移，
> 同一 skill 在不同项目产出不同范式的交付件——这正是本管道要消灭的问题。

## 分层

```
数据层  项目自己的 reqs.py / cases_*.py / d_ex.py / spec.py   ← 每个项目重写（这是测试设计本身）
构建层  tcgen.dsl / tcgen.audit / tcgen.xlsx / tcgen.drawio    ← 照搬，不改
同步层  tcgen.feishu                                          ← 照搬，只改 token 与 sheet_id
```

**判断标准**：凡与业务无关的（表格样式、门禁算法、六维度配色、饼图重建）都在 `tcgen/`；
凡业务专有的（REQ 正文、用例正文、飞书 token、文件名、业务阈值）都在项目侧。
**严禁**把项目专有常量写进 `tcgen/`。

## 快速开始

```bash
# 1. 复制模板到项目目录
cp <skill>/scripts/project_template/*.py ./

# 2. 改数据层：reqs.py（REQ清单）、cases_demo.py（用例，可拆多个）、
#    d_ex_demo.py（EX矩阵+文档章节全集）、spec.py（专项两表）
#    改 build.py 顶部 CONFIG：PROJECT / DATE / EXTRA_TP

# 3. 构建（产出 xlsx + drawio，并打印硬门禁结论）
python build.py

# 4. 飞书同步（先在飞书建表并把 sheet_id 回填 sync_feishu.py）
python sync_feishu.py export    # 导出同源 CSV，核对行列数与 sheet_id
python sync_feishu.py all       # 重建格式 + 重建饼图
```

`_boot.py` 负责定位 skill 的 `scripts/` 目录（环境变量 `TCGEN_HOME` → 逐级向上找
`.claude/skills/...` → 用户级 `~/.claude/...`），项目脚本无需关心绝对路径。

## 模块职责

| 文件 | 职责 | 项目侧是否改动 |
|------|------|--------------|
| `tcgen/dsl.py` | 用例数据模型 `add()`；步骤:预期=1:1 构建期 assert；优先级→风险/定级依据映射；维度映射表；各表表头 | 不改 |
| `tcgen/audit.py` | 全部门禁的集合运算 + 违例 ID；`compute()` 返回门禁 dict，`gates()` 逐项通过判定，`gate_notes()` 数据派生说明 | 不改 |
| `tcgen/xlsx.py` | 8 个 Sheet 的建表与样式；三表统一按 `(REQ,TP,TC)` 排序；REQ/TP 列层级合并；审计报告全文 + 6 个饼图 | 不改 |
| `tcgen/drawio.py` | 六维度配色与左→右树布局，正交无箭头，坐标按块居中 | 不改 |
| `tcgen/feishu.py` | CSV 导出、格式重建、饼图重建 | 不改 |
| `project_template/reqs.py` | REQ 清单、输入来源、专项 REQ 集合、审计报告说明 | **重写** |
| `project_template/cases_demo.py` | 全部测试用例 | **重写** |
| `project_template/d_ex_demo.py` | EX 交叉矩阵 + `DOC_SECTIONS`/`SECTION_NA` | **重写** |
| `project_template/spec.py` | 专项测试用例表 + 专项数据采集表 | **重写** |
| `project_template/build.py` | 入口，顶部 CONFIG | 改 CONFIG |
| `project_template/sync_feishu.py` | 飞书入口，顶部 CONFIG | 改 CONFIG |

## 门禁由脚本算，不靠肉眼

`build.py` 跑完直接打印硬门禁结论。`tcgen.audit.compute()` 覆盖的门禁：

未覆盖 REQ / 覆盖深度（每条功能 REQ 各自须含正向类+非正向类）/ 一对多坍缩（TC→TP、TC→REQ）/
TP 无专属 TC / 反模式（步骤:预期错位）/ 专项 REQ 配套功能用例 / TP 维度与用例维度错配 /
REQ 清单结构性完整（章节反查差集、编号连续、字段枚举、分母自洽）/
功能安全深度（触发+恢复、多触发源各≥1、预期三要素）/ EX 交叉五项 / 优先级与风险一致。

每项都输出违例 ID 清单，审计报告的「自查回执」分区写明每个数字的计算方式。
**数字与计算方式对不上即审计无效**，见 SKILL.md「审计三铁律」。

## 易错点（都是踩过的）

**深度门禁按 REQ 逐条判**，不是「REQ-001 写正向、REQ-002 写反向」就算覆盖全。
每条功能 REQ 各自都要有正向类与非正向类。

**安全类 REQ 的「类型」列一律填 `安全`**，子域（信息安全/功能安全）写进备注。
填成「功能安全」会因含「功能」二字被误判为功能类 REQ，叠加正向+反向要求造成双重判定。

**`TP-SEC` 必须先于 `TP-S` 匹配**，否则安全测试点会被归进稳定性维度。
`dsl.DIM_PREFIX_ORDER` 与 `drawio._ORDER` 已保证顺序，别改。

**矩阵标「必测」的格，落地 TC-ID 必须真实存在**且编号一致，否则算必测缺口——
矩阵不能是空头承诺。

**`spec_reqs` 与 `spec_companion_reqs` 是两个集合**：前者是「仅专项覆盖、不在普通用例里」
的 REQ（计入覆盖集、不参与深度判定）；后者是「被专项覆盖、须校验配套功能用例」的全集，
通常 ⊇ 前者。既有普通功能用例又被专项覆盖的 REQ（如成功率类）要列进后者而非前者。

**飞书 CSV 一律按 Sheet 中文名映射，不按序号**。新增 Sheet 会让序号整体后移，
按序号推送会把内容写进错误的 sheet_id。

**飞书图表 refs 是写死行号，每次必须删旧图重建**。审计表新增门禁行后 G/H 辅助块
整体下移，旧图会指向错误区域。行号由 `parse_chart_blocks()` 从 CSV 真实解析，不手填。

**清空飞书 `scope=all` 会连格式一起清掉**，之后必须跑 `sync_feishu.py format` 重建。

**审计报告的 `AUDIT_MAIN_LAST`** 要填主区最后一行，它之后的 G/H 列是饼图辅助块，
不能被表格格式和筛选器覆盖。审计行数变了要同步改。

## 自检

模板自带一份门禁全通过的样例数据。管道改动后跑一遍，应输出「硬门禁: 全部通过」：

```bash
mkdir /tmp/t && cp <skill>/scripts/project_template/*.py /tmp/t/ && cd /tmp/t && python build.py
```
