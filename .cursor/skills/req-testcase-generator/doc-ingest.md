# 测试设计文档摄入指南

支持输入文档类型：
- 需求文档（PRD/BRD）
- 技术方案文档（架构设计、接口设计、数据设计）
- UI 设计文档（视觉规范、页面稿）
- 交互文档（流程图、状态图、交互说明）

## 飞书文档与飞书文件

### Docx / Wiki 文档

1. 读取 [`lark-shared`](../../../.agents/skills/lark-shared/SKILL.md) 确认认证状态
2. 切 `lark-doc`：`lark-cli docs +fetch --doc "<url或token>"`
3. 文档较长时先用 `--scope simple` 获取结构，再按需局部读取
4. Wiki URL 需先 `lark-cli drive +inspect --url '<url>'` 获取底层 docx token

### 飞书云盘中的文件

| 文件类型 | 操作 |
|---------|------|
| 在线 docx | `lark-cli docs +fetch` |
| PDF / Word 附件 | `lark-cli drive +download` 下载到本地后读取 |
| 电子表格 | 切 `lark-sheets` |
| 多维表格 | 切 `lark-base` |

### 飞书思维笔记

若文档以思维笔记形式提供，切 `lark-doc` 思维笔记链路读取。

---

## 本地文件

### .txt / .md

直接使用 `Read` 工具读取。注意编码（UTF-8 优先）。

### .pdf

1. 优先 `Read` 工具（支持文本型 PDF）
2. 不可读或扫描件：

```bash
pip install pypdf
python -c "
from pypdf import PdfReader
r = PdfReader('path/to/file.pdf')
print('\n'.join(p.extract_text() or '' for p in r.pages))
"
```

3. 扫描件需 OCR 时告知用户，建议使用可复制文本的 PDF 或提供 Word/飞书版

### .docx

1. 优先 `Read` 工具
2. 不可读时：

```bash
pip install python-docx
python -c "
from docx import Document
d = Document('path/to/file.docx')
print('\n'.join(p.text for p in d.paragraphs))
"
```

### .doc（旧版 Word）

建议用户另存为 `.docx`，或通过飞书导入：

```bash
lark-cli drive +import --type docx --file path/to/file.doc
```

---

## 多文档输入

用户同时提供多份文档时：

1. 逐份摄入并标注来源
2. 合并分析前检查版本/日期冲突
3. 冲突内容列入 Phase 1 待确认问题

---

## 摄入质量检查

进入 Phase 1 前确认：

- [ ] 功能、技术约束、交互规则已完整获取（非仅目录/摘要）
- [ ] 图表/流程图内容已提取或标注「需用户补充说明」
- [ ] 附录、接口文档、原型链接、状态流转说明已识别并记录
- [ ] 文档版本号/日期已记录
