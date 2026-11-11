# MBV V0.1 — Carbon 离线交付（GitHub ZIP 镜像）

**本分支仅为离线任务包，不是主工程的开发或合并分支。**

## 操作指引

1. 在浏览器访问本分支 ZIP 存档并解压（无需 Carbon 访问 GitHub）。
2. 把解压后的整个目录交给 Carbon。
3. 让 Carbon 先读取 `00_START_HERE_CARBON.md` 以及 `01_CARBON_OFFLINE_EXECUTION_PROMPT.md`，再读 `02_TASK_INDEX_AND_ACCEPTANCE.md` 与 `03_INDEPENDENT_QA_REPORT.md`。
4. 仅在本地编写/修改代码和运行测试，不允许把 GitHub 克隆/推送作为任务前置条件。完成后将完整实现打包为 `MBV_V0.1_Carbon_Completed.zip` 回传，供独立审核。

## 内容范围

- `docs/`: 原开发计划书与执行指令。
- `project/`: Claude Code 现有 WIP 源码及一个测试，并非已通过完整验收。
- `reference/vlr_verify/`: 原 VLR B0 研究 API 的只读参考实现（需保持冻结）。
- `reference/third_party/`: Zeiierman Pine v6 参考源码与许可证边界。
- `qa_known_defects_repro.py`: 用于证明旧代码缺陷；**运行成功不代表验收成功**。

本 ZIP 为文本源码可用的完整工程移交；去除了没有必要的 `__pycache__`、`.pytest_cache` 和嵌套旧 ZIP。原先两份嵌套 ZIP 的关键文档及源码已直接展开在 `docs/`、`project/`、`reference/`。不含实盘数据、真实分钟行情或未验证的收益结论。

本分支不用于 PR 合并至 master。请勿将 Zeiierman 的 CC BY-NC-SA 4.0 源码视为 Apache-2.0 授权。
