# -*- coding: utf-8 -*-
"""tcgen — req-testcase-generator 的通用交付件管道。

分层（项目侧只写数据层，其余照搬）：
    数据层   项目自己的 cases_*.py / reqs.py / d_ex.py   ← 每个项目重写
    构建层   tcgen.dsl / tcgen.audit / tcgen.xlsx / tcgen.drawio
    同步层   tcgen.feishu

约束：本包内不得出现任何项目专有的常量（REQ 正文、飞书 token、文件名、
业务阈值）。项目专有的东西一律由调用方传参，见 project_template/。
"""
from . import audit, drawio, dsl, feishu, xlsx   # noqa: F401

__all__ = ['dsl', 'audit', 'xlsx', 'drawio', 'feishu']
