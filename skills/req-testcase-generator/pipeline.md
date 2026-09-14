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

设 `$SKILL` 为本 skill 目录（Windows 如 `D:/P_TestCase/skills/req-testcase-generator`，
Ubuntu 如 `~/P_TestCase/skills/req-testcase-generator`）。
**管道本身跨平台**，Windows 与 Ubuntu 用同一套命令，差异只在下面第 2 步的路径写法：

```bash
# 1. 复制模板到项目目录
cp $SKILL/scripts/project_template/*.py ./

# 2. 告诉脚本去哪找 tcgen（项目不在 skill 仓库内时需要这一步）
echo "D:/P_TestCase/skills/req-testcase-generator" > .tcgen_home     # Windows
echo "$HOME/P_TestCase/skills/req-testcase-generator" > .tcgen_home  # Ubuntu

# 3. 改数据层：reqs.py（REQ清单）、cases_demo.py（用例，可拆多个）、
#    d_ex_demo.py（EX矩阵+文档章节全集）、spec.py（专项两表）
#    改 build.py 顶部 CONFIG：PROJECT / DATE / EXTRA_TP

# 4. 构建（产出 xlsx + drawio，并打印硬门禁结论）
python build.py

# 5. 飞书同步（先在飞书建表并把 sheet_id 回填 sync_feishu.py）
python sync_feishu.py export    # 导出同源 CSV，核对行列数与 sheet_id
python sync_feishu.py all       # 重建格式 + 重建饼图
```

`_boot.py` 负责定位 skill 的 `scripts/` 目录，按以下顺序查找，命中即止：

1. 环境变量 `TCGEN_HOME`（指向 skill 目录或其 `scripts` 目录，两者都接受）
2. 当前目录或任一祖先目录下的 `.tcgen_home` 文件，内容为 skill 路径
3. 逐级向上试 `skills/`、`.claude/skills/`、`.cursor/skills/`、`.agents/skills/` 各种布局
   —— 项目建在 skill 仓库内时（第 3 条的 `skills/`）无需任何配置即可命中
4. 用户级 `~/.claude/skills/`、`~/.cursor/skills/`

四条都没命中时报错并列出三种可选修复方式，不会静默失败。

## 模块职责

| 文件 | 职责 | 项目侧是否改动 |
|------|------|--------------|
| `tcgen/dsl.py` | 用例数据模型 `add()`；步骤:预期=1:1 构建期 assert；优先级→风险/定级依据映射；维度映射表；各表表头 | 不改 |
| `tcgen/audit.py` | 全部门禁的集合运算 + 违例 ID；`compute()` 返回门禁 dict，`gates()` 逐项通过判定，`gate_notes()` 数据派生说明 | 不改 |
| `tcgen/xlsx.py` | 8 个 Sheet 的建表与样式；三表统一按 `(REQ,TP,TC)` 排序；REQ/TP 列层级合并；审计报告全文 + 6 个饼图 | 不改 |
| `tcgen/drawio.py` | 层次 需求→维度→〔模块〕→测试点→测试用例；六维度配色与左→右树布局，正交无箭头，叶子驱动、父节点按子块居中。`group_min=12` 触发模块层（防大维度标签跑出屏幕），`module_names=` 给模块中文名，`tp_names=` 覆盖测试点名称，`extra_cases=` 挂不在 CASES 里的用例（如专项），`dedupe_titles` 处理 TC 与 TP 同文，`show_cases=False` 退回三级。 `group_by=` 把顶层从六维度换成自定义分组（如需求编号 F17），配色按位置轮转、`未分组` 兜底无归属 TP；默认 None 走六维度，既有项目行为不变。`build()` 出 `.drawio`（导入飞书云文档）、`mermaid()` 出 `.mmd`（写入飞书画板），两者共用 `derive()` 与 `_mod_id()` | 不改 |
| `tcgen/feishu.py` | CSV 导出、格式重建、饼图重建 | 不改 |
| `tcgen/plat.py` | 平台适配：lark-cli 定位（`TCGEN_LARK_CLI` → PATH）、缺 CLI 的报错修法、中文输出编码按需切换。**只放 OS 差异，不放业务逻辑** | 不改 |
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

按主题分六组，**出问题时按现象跳组读**，不必通读：

| 现象 | 看哪组 |
|------|--------|
| 门禁数字对不上、深度/维度判定可疑 | 一、审计门禁口径 |
| 推送飞书失败、diff 报差异修不掉 | 二、飞书表格与推送 |
| 导图维度像丢了、画板与本地不一致 | 三、思维导图与画板 |
| 饼图空白、图表引用错位 | 四、审计报告饼图 |
| 改了 bug 但新项目照旧复现 | 五、共享层与副本 |
| 换机器后飞书失效、中文乱码 | 六、跨平台 |


### 一、审计门禁口径

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

### 二、飞书表格与推送

**飞书 CSV 一律按 Sheet 中文名映射，不按序号**。新增 Sheet 会让序号整体后移，
按序号推送会把内容写进错误的 sheet_id。

**飞书图表 refs 是写死行号，每次必须删旧图重建**。审计表新增门禁行后 G/H 辅助块
整体下移，旧图会指向错误区域。行号由 `parse_chart_blocks()` 从 CSV 真实解析，不手填。

**推送飞书的固定顺序：解合并 → 写数据 → 重建合并 → 更新 G/H → 重建图表 → diff**。
少任一步都会卡住，实测每一步都踩过：
① **合并单元格挡写入**。评审追溯表/追溯矩阵有 REQ/TP 层级合并，写入非左上格会报
`cell at row X is inside a merged region`。必须先 `+cells-unmerge`（范围取 `A2:B{末行}`，
别含表头行）再写，写完按本地 xlsx 的 `merged_cells.ranges` 重建。**用例数变了合并结构也会变**
（实测 17→22→29→39 处），必须每次从本地 xlsx 重新取，不能沿用上一轮的范围。
② **审计报告第 1 行是合并 banner，推送要从 A2 起**。推 `A1:D65` 必失败，推 `A2:D65`。
③ **G/H 辅助块不在主区范围内，要单独推**。只推 `A2:D65` 会留下旧的饼图数据（实测 diff 报 7 处
差异全在 G/H），必须按 `parse_chart_blocks` 给出的块边界单独写。
④ **别手写块边界**。自己找块首/末行的循环极易越界串到下一块（实测一次串出 3 倍冗余写入），
直接用 `tcgen.feishu.parse_chart_blocks()` 的 `trow`/`last`。

**行数增长后要同步改 range 上界**。用例从 47→62→85 时，推送范围要跟着从 `A1:I48` 改到
`A1:I86`，漏改会只写一部分、diff 仍报差异且看不出原因。范围上界从 `export` 输出的 rows 数取，
不要手填。

**`lark-cli` 子命令名会变，用前先 `--help` 确认**。本轮实测：`+read` 已不存在（改名
`+cells-get`）、`+cells-clear` 需 `--yes`、`+cells-unmerge` 是独立子命令而非 `+cells-merge
--operation unmerge`、`drive +delete` 用 `--file-token` 而非 `--token`、`drive` 没有列目录的
子命令。**用错子命令时 CLI 返回的是 JSON 错误而非非零退出码**，脚本里若只看 stdout 有没有内容，
会把失败当成空结果继续跑下去。

### 三、思维导图与画板

**思维导图必须出到用例层，且大维度必须再分模块**。父节点摆在其整个子块的垂直中心，
某维度独占大半 TP 时（实测功能维度 56/79）子块高 4500px，维度标签被推到屏幕外——
现象是「维度丢了、直接显示 TP-TC」，但查 `mind_map.parent_id` 树会发现节点都在，
**是布局问题不是数据问题**，别去改数据。`group_min=12` + `module_names=`（中文）解决。

**飞书画板与飞书云文档是两回事，别混**。`.drawio` 只能导入云文档（生成**新文档**，无法原地
替换已有画板）；要更新已有画板必须走 `whiteboard +update --input_format mermaid`。
用户给的是**已有文档里的画板**时，用 `--overwrite` 原地更新，链接不变——**不要另建文档**
（实测建了重复文档，而 `drive` 没有列目录子命令，找不回先前那份的 token）。
`--overwrite` 前必须 `+query --output_as raw` 备份；写后回读复验节点数
（`1 根 + 顶层 + TP + TC`）与本地产物一致。

**画板里已有内容时，先分辨它是谁生成的再覆盖**。实测：目标画板有 411 个节点、0 个
`mind_map` 节点——是早先用 drawio 导入的静态形状（`composite_shape` + `connector`），
不是人工内容。覆盖前把带文字节点全取出来比对一遍（是否全部匹配 `TP-*`/`TC-*` 等自己生成的
命名），确认无人工标注再动手，并保留备份路径。

**「数值格存成文本」不必然导致空白饼图，别当阻断项**。2026-09 实测：某环境
审计报告 H 列 14 格全为字符串，5 个饼图渲染完全正常、无空白；且该环境下
**没有通道能写出真数字**——`+cells-set` 传 `{'value': 18}`（dry-run 确认 payload
就是数字）、`+workbook-import` 导入 xlsx，写进去一律变字符串。所以
`diff_charts` 返回的 `text_cells` 只作线索，**不计入退出码**（模板里
`bad = len(miss) + len(extra)`，`test_feishu_diff.t_template_text_cells_not_blocking`
守这条）。当阻断的后果是：`diff` 每次恒报十余处又修不掉，而门禁18 要求差异为 0
才算同步完成——一个修不掉的非零退出会把整道验收永久卡死，人只能绕过它，
连 `missing`/`extra` 这两项真检查一起失效。**引用错位（missing/extra）仍是硬性的**，
那个确实会让饼图指向空白区。判断顺序：先看饼图是否真空白，空白再看引用是否对齐，
引用对齐了才轮到查数值格类型。

**回读用 `+cells-get`，不是 `+read`**。`+read` 自 lark-cli 1.0.94 起已不存在
（改名 `+cells-get`，且 sheet 必须走独立 `--sheet-id`、range 里不带 sheet 前缀）。
用错子命令 → 命令报错 → values 取空 → 每格读成 `''` → `diff` 报「线上全空」
的假差异（实测 1624 处）。更麻烦的是 `diff` 一失效，「图表引用错位」这类**只能
靠回读发现**的故障就再也抓不到——实测正是它掩盖了行号错位，导致空白饼图查了三轮。
返回结构是 `data.ranges[0].cells`，每格为 `{value: ...}` 对象而非裸值。
`test_feishu_diff` 的 `t_read_sheet_uses_cells_get` 等三条守这条。

**xlsx 导入飞书会让 G/H 辅助块整体下移，行号逐块累积错位**。实测导入后
块间空行被多插一行，偏移从 +1 累积到 +6（本地 G87 的块到线上变成 G93），
而饼图引用是按**本地 CSV 行号**算的，于是引用全部落到错位区，页面上就是空白饼图。
修法是让**线上行号对齐本地**（清掉 G/H 区后按本地行号重写），不要反过来把图表
建到线上的错位行号上——那样两套行号并存，`diff` 会永远报差异、`diff_charts`
永远报引用过期，等于留下一个恒报警的检查。

**飞书画板不认 `.drawio`**，只能走 `mermaid()` 出 `.mmd` 再经 whiteboard-cli 转 openapi。
`--overwrite` 会清空画板，写前先 `+query --output_as raw` 备份；写后必须回读复验，
**本地 PNG 通过不代表画板通过**（两者布局引擎不同）。

### 四、审计报告饼图

**空白饼图有三种成因，其中一种不是故障**。① 引用地址错位（改了报告行数）；
② 数值格存成文本；③ **该块合计本来就是 0**（如零缺陷）。三者在页面上长得一模一样，
所以第③种不画饼图、改写结论文本（A 方案），让「零缺陷」和「图表坏了」可区分。
**不要塞占位 `1` 凑整圆**——那是往报告里写不真实的计数。判据是
`parse_chart_blocks` 返回的 `total`；`rebuild_charts` 对 `total==0` 的块写文本并
标 `kind='note'`；`diff_charts` 把这类块排除在 missing 外，但归零块上遗留的旧图
会进 `extra`。

**渲染层格位不参与数据比对，否则是永久假差异**。审计报告的 2×3 tile（`CHART_TILES`
= J1/P1/J16/P16/J31/P31）要么被饼图对象盖住，要么写着零数据的结论文本——这些内容
**不来自 CSV**，本地 CSV 只有 A–H 八列，而 `diff_sheets` 默认读到线上 P 列。
实测：结论文本写在线上 P16 后，`diff` 每次都报一条 `(16,16)` 的差异，谁也修不掉。
修法是 `diff_sheets(..., tile_sheet=AUDIT_SHEET_NAME)` 把这些格位交给 `diff_charts`
检查——**一个格子只能有一个检查者**。屏蔽必须精确到格：屏蔽整行会连同行的真差异
一起放过，从「误报」滑到更糟的「漏报」。

**生成侧（xlsx）不要往单元格写这行结论文本**。xlsx 的格子会随 `export_csv` 流进 CSV，
而线上那行文本由 `rebuild_charts` 写在渲染层 tile，两边地址不同，写了就又造出一条
假差异。本地读者仍看得清：紧邻的 G/H 辅助块把几个 0 逐行列在原处。

### 五、共享层与副本

**修 bug 要修 `tcgen/` 里的共享实现，不是项目里的那份副本**。实测踩过两次，
第二次是这轮审计才发现的：A 方案（零合计不画图）当时只改了某项目本地的
`build_xlsx.py`，而**新项目实际调用的是 `tcgen/xlsx.py:add_pies`**——那份没改，
新项目跑起来照旧画出空白饼图，等于这条教训根本没沉淀。
**判据**：修完问， 「新项目从零跑一遍，会不会再中一次？」——若答案取决于某个项目目录里的
文件，就是没修完。落地顺序固定为 ①改 `tcgen/` 共享实现 → ②加回归测试 → ③故障注入
验证测试真能抓住回退 → ④`grep` 确认没有第二份副本还在用旧逻辑。

**项目侧脚本必须是薄封装，不许抄一份建图实现**。实测踩过：`charts_feishu.py` 曾是
完整的重复实现（自己写死 TILES、自己拼 chart-create），skill 加了 A 方案后它照旧建
6 个图——跑一次就把空白饼图重新造回来。文案与格位的唯一来源是 `feishu.zero_note`
和 `feishu.CHART_TILES`，两侧共用；各写一份，只要差一个字就是永久假差异。

**前两种坏法都不会被数据比对发现**。① 改了审计报告的行数：饼图引用绝对地址，
增删一行就让 G/H 辅助块位移而引用不动，饼图全指向空白区，修法是 `sync_feishu.py charts`
按 CSV 真实行号重建。② 数值格存成了文本：整表推送时把每格都 `str()` 一遍，H 列的
`67` 成了 `'67'`，此时引用地址全对、图表对象都在，饼图照样空白，**重建图表治不了**，
必须把数值格重写成数字。两者的共同陷阱是所有常规检查都说没问题——数据逐格比对一致
（`_norm_cell` 把 `67` 和 `'67'` 都归一化成 `"67"`，类型信息被抹掉）、图表对象还在、
辅助数据肉眼看也对。`sync_feishu.py diff` 已内置 `diff_charts`，三项都空才算健康。
**整表推送时数值列要保持原生类型，只对文本列做 `str()`。**

**模块顺序按最小 TP 号排，跨模块 TP 按多数归属**。按用例数排序会让 `TP-F-001` 开头的模块掉到
中间；跨模块 TP 取「首条用例」会判给号段不相干的模块，连带整块顺序错位（实测 `TP-F-041`）。
两者都会让评审时导图顺序与 TP 编号对不上。`test_drawio_group.py` 的 `t_module_order`
与 `t_attribution_majority` 专盯这两条，已用故障注入验证抓得住。

**模块节点 id 别用维度名拼**：中文经 `[^0-9A-Za-z_]→_` 清洗后变成 `mod____0`，
不同维度同序号组会撞 id。用 `_mod_id(dims, d, gi)`，drawio 与 mermaid 共用。

### 六、跨平台

**跨平台：绝对路径一律不写死，改用 `tcgen.plat`**。实测踩过：`feishu.py` 里
`DEFAULT_LARK_CLI` 曾写死 `C:/Users/<某个用户名>/AppData/Roaming/npm/lark-cli.cmd`。
换机器（换用户名、或换到 Ubuntu）后**全部飞书函数一律 FileNotFoundError，而本地
xlsx/drawio 照常产出**——现象是「交付件都出来了，只有飞书没连上」，很容易当成网络或
授权问题查半天。现由 `plat.lark_cli()` 按 `TCGEN_LARK_CLI` → PATH 定位，
Windows 优先 `lark-cli.cmd`（npm 的包装器），POSIX 只找裸名字；
找不到时**返回裸名字而不抛异常**——`DEFAULT_LARK_CLI` 在导入期求值，此处抛异常会让
根本不碰飞书的纯本地流程（`build.py`）也 import 失败。`test_plat.py` 的
`t_no_hardcoded_abs_path` 扫 `tcgen/` 全包守这条（只扫代码字符串，
docstring 里举例 `C:/Users/...` 不算违例）。

**修 Linux 不能顺手弄坏 Windows**。中文输出上踩过一次：为了让 Ubuntu 在 `LC_ALL=C`
下 print 中文不崩，两个测试文件曾**无条件**把 stdout 包成 UTF-8——结果在 Windows 的
cp936 控制台里，中文输出全成了乱码。正确做法是 `plat.force_utf8_stdout()`：
**先试当前编码能不能写中文，写得出就一动不动**，写不出才换。
`t_stdout_kept_when_encodable` 与 `t_stdout_switched_when_ascii` 成对守两个方向，
少任一个都会让「修好一边、弄坏另一边」重演。

**清空飞书 `scope=all` 会连格式一起清掉**，之后必须跑 `sync_feishu.py format` 重建。

**审计报告的 `AUDIT_MAIN_LAST`** 要填主区最后一行，它之后的 G/H 列是饼图辅助块，
不能被表格格式和筛选器覆盖。审计行数变了要同步改。

## 自检

管道改动后**八个都要跑**，缺一不可。每个都覆盖了别人覆盖不到的代码路径。

**① 门禁自检**：模板自带一份门禁全通过的样例数据，应输出「硬门禁: 全部通过」。
在 skill 仓库内建临时目录即可，`_boot.py` 会自动向上找到 `skills/` 布局，无需配置：

```bash
cd <仓库根>                 # 例如 D:/P_TestCase
mkdir -p _selftest && cp skills/req-testcase-generator/scripts/project_template/*.py _selftest/
cd _selftest && python build.py && cd .. && rm -rf _selftest
```

**② 思维导图排版回归**：应输出「思维导图回归: 8/8 通过」。

```bash
cd skills/req-testcase-generator/scripts && python test_drawio_group.py
```

**为什么必须单独跑 ②**：样例数据只有 11 个 TP，达不到 `group_min=12`，
**模块层那段代码在 ① 里根本不会被执行**——① 报「全部通过」不代表模块层没坏。
`test_drawio_group.py` 专门造够量的数据把它跑到，覆盖硬门禁 13 的思维导图各项：
模块层触发/不触发、跨模块 TP 唯一归属、模块 id 不撞、同层零重叠、
父子距离 ≤600px、无裸用例节点、drawio 与 mermaid 层级一致。
已用故障注入验证过它抓得住真问题（关掉模块层 → `t_group`/`t_mod_id_unique` 失败；
模块 id 改回用中文拼 → `t_mod_id_unique` 失败；排序键回退成按用例数 → `t_module_order` 失败；
归属回退成取首条用例 → `t_attribution_majority` 失败）。

**③ 标题/类型门禁回归**：应输出「标题/类型门禁回归: 6/6 通过」。

```bash
cd skills/req-testcase-generator/scripts && python test_audit_title.py
```

**为什么必须单独跑 ③**：样例数据全部合规，硬门禁 15 那三项在 ① 里恒为 0，
**等于新门禁根本没被执行**。本文件专门造违例数据把它们跑到：元层面标题 4 条必须抓到、
9 条易混标题（`用验证码登录成功` 等）必须零误报、覆盖↔类型三组矛盾必须抓到、
而 EX 交叉的合规写法（`稳定性测试 + 异常`）必须放过、软提示 C 必须不进 `gates()`。

**④ 飞书比对回归**：应输出「飞书比对回归: 13/13 通过」。不联网，桩掉 `read_sheet` / `_run`。

**⑤ 饼图生成回归**：`python test_xlsx_pies.py`，应输出「饼图生成回归: 5/5 通过」。
纯 openpyxl 内存构图，不联网。守 A 方案在**生成侧**的落地：零合计块不画图、
有缺陷时照画、辅助块仍写、I–P 列不许写字（否则 CSV 变宽）。

**⑥ 复用检查回归**：`python test_reuse.py`，应输出「复用检查回归: 9/9 通过」。
守「项目侧不许抄一份共享实现」这条门禁**本身不误报**——9 项里 4 项是误报守卫。
第一版用文本 grep，在真实项目上报 13 处、其中 12 处是误报（`"P1"` 是优先级值不是
格位 P1；`TITLE_META_RX` 出现在项目文件里恰恰是正确的 import；`chart-create`
命中的是薄封装自己的文档字符串）。现改用 AST 只认三种真抄形态：自建 `PieChart()`、
自拼 `chart-create`、自己**赋值定义**共享常量或格位表。
`build.py` 已内置该检查（`tcgen.reuse.report`），每次构建都会打印一行。

```bash
cd skills/req-testcase-generator/scripts && python test_feishu_diff.py
```

**⑧ 需求编号列回归**：`python test_xlsx_req_col.py`，应输出「需求编号列回归: 5/5 通过」。
守「需求编号只能挂在 REQ 元组末尾（索引 8）、渲染时才移到首列」这条位置契约。
`tcgen.audit` 按固定位置读 REQ 字段，插在前面会让类型列读到可测性、可测性读到覆盖状态——
**门禁照样跑完只是结论全错，不报任何异常**。含一条反证：编号插首位必然改变 audit 结论。

**⑦ 跨平台回归**：`python test_plat.py`，应输出「跨平台回归: 14/14 通过」。
不联网，也不要求本机真的装了 lark-cli。守「同一份 skill 在 Windows 与 Ubuntu 都能跑」：
lark-cli 定位四条路径（env 覆盖 / `~` 展开 / 找不到时返回裸名字不抛异常 /
Windows 试 `.cmd`、POSIX 不试）、缺 CLI 的报错含三条修法、中文输出两个方向都不坏、
以及 `tcgen/` 不许再出现写死的绝对路径。
已用故障注入验证抓得住回退（恢复写死路径 → `t_no_hardcoded_abs_path` 与
`t_default_lark_cli_not_absolute_literal` 双双失败；stdout 改回无条件包 UTF-8 →
`t_stdout_kept_when_encodable` 失败；`_exec` 不翻译 `FileNotFoundError` →
`t_exec_translates_missing_cli` 直接崩在裸异常上）。

**为什么必须单独跑 ④**：`diff_sheets` 只在「改完数据同步飞书」时才被调用，
① ② ③ 全都碰不到它；而它报出的单元格地址是人照着去改的依据，**地址错一位就会改错格子**
（实测把备注列 `I9` 报成了测试结果列 `H9`——列号传了 0-based 而 `col_letter` 是 1-based）。
`t_col_is_one_based` 专盯这条，另外守着整数 `147.0` vs `"147"` 不算差异、
尾部空行空列不算差异、真差异不被归一化放过、本地缺 CSV 要显式报出。

后两项 `t_charts_ok_when_aligned` / `t_charts_catch_row_shift` 守的是另一类事故：
**审计报告增删行会打断饼图**。图表引用绝对单元格地址（`'质量审计报告'!G63:H66`），
报告增删行后 G/H 辅助块整体位移，引用不跟着动——此时逐格比对全 OK、图表对象一个不少、
辅助数据也完好，只有引用指向了空白区。实测报告插 5 行后 6 个饼图引用全偏 −5 行、
线上 6 图全空。造测试数据时**辅助块要放在第 20 行以后**：放前几行的话 −5 得到负数行号
会被正则滤掉，`extra` 少报一个，测出来的形态就和真实事故不一样了。

**做故障注入时先删 `__pycache__`**。注入若与还原「字节数相同 + 同一秒内完成」
（如把 `fv, lv` 写成 `lv, fv`），Python 会认为 `.pyc` 仍然有效、继续加载被注入的旧字节码——
**还原后测试仍然失败，看起来像 skill 被改坏了，其实文件是好的**。
判断方法：`cmp` 源文件与备份，一致就是缓存问题，`find . -name __pycache__ -type d -exec rm -rf {} +` 后重跑。
