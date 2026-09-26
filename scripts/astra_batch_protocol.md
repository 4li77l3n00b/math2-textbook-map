# Astra 历年数学二独立作答与校对协议

工作根目录：`/home/ctrwaz/数学二`。用户要求由 Astra 批量独立解答 1987–2026 年全部试卷，先解后校对，答案可逐题索引。最多三个工作代理同时运行。不得再创建代理。

## 独立阶段（必须先完成你被分配的全部年份）

1. 只读取 `output/astra/input/YYYY-exam.md`、其中链接指向的试卷插图，及 `output/pdf/YYYY/YYYY-exam.pdf`（纯试卷整理 PDF）。不得读取答案、解析、editorial、其他代理作答、以前对话、网络答案。你的上下文未继承主任务历史。
2. 独立解答每道题，含所有子问；给出实际推导，不能只写方法名、引用参考解、占位或用脚本生成没有推导的模板。选择题保留选项字母及正确命题；证明题必须写完整论证。数学计算可用本地 Python 辅助核算。
3. 注意原稿可能有 OCR 错误。图形题必须查看链接图片。若需核对文字，先看纯试卷 PDF；独立阶段不要打开试题解析合订 PDF。无法确认的题明确记录不确定及按何种题意作答，不猜成已解决。不要修改输入。
4. 每年生成 `output/astra/drafts/YYYY.json`，格式见下。早年重复小题号必须包含大题编号，不能漏掉无编号但实际存在的题（例如 1995 一(4)）。现代连续编号保留原题号。
5. 在全部分配年份的 draft 写完后，用 SHA-256 将每个 draft 的散列与 UTC 时间写入 `output/astra/audit/BATCH_ID-blind-lock.json`。后续绝对不能覆盖或修改这些 draft。
6. 每完成一份试卷即向主代理发送简洁进度消息，但不暂停继续下一年。

## 校对阶段（全部分配年份的独立稿锁定后才能开始）

7. 读取 `output/astra/reference_manifest.json`，只校对你负责的年份。参考为 `output/markdown/YYYY/` 下原有解析、仅答案。多份解析均可核对；不要把参考答案视为必然正确。若发现参考/OCR错误，重新推导并记录依据，必要时查看对应原 PDF 页面（此阶段允许）。
8. 逐题对照结果与步骤。代数等价算一致；自己错了就明确记录独立稿错误与修正；参考错了则记录 reference_issue；不能确定则 unresolved，不能硬标一致。校对可修改最终稿，但必须保留初稿。
9. 输出 `output/astra/final/YYYY.json`。逐题填 `review`，记录对照材料、结论、具体差异与修正理由。不要用全卷一句“核对通过”代替逐题校对。question_id、题目顺序与初稿保持一致。
10. 输出 `output/astra/reports/YYYY.md`，简述题数、独立结果一致/修正/来源问题/未决项，列有实质问题的题号。最后重新验证 draft 散列未变，将完成时间、结果计数和锁定核验写入 `output/astra/audit/BATCH_ID-complete.json`。
11. 不改其他年份、共享索引或共享脚本。JSON 必须可被标准 json 解析；用 Python 原始字符串/字典 json.dump 避免 LaTeX 转义错误。每个文件用临时文件加 replace 原子保存。

## JSON 约定

顶层：
`{"year":1987,"model":"gpt-6-astra","phase":"independent"或"reviewed","exam_source":"output/markdown/1987/1987-exam.md","questions":[...]}`

每题必填：
- `question_id`：ASCII 稳定 ID。现代如 `math2-2026-q17`；早年如 `math2-1987-I-01`、`math2-1987-VI-02`、`math2-1987-X`。同一主解答题含多个子问可保留一个主条目，在正文用(1)(2)明确分开；早年大题下独立的小题应分别建条目。
- `label`：读者可见的原题号，如 `一（1）`、`六（2）`、`17`、`22`。
- `section`：如 `选择题`、`填空题`、`解答题`。
- `stem`：完整题干（含必要选项/条件，LaTeX 用 $...$ 与 $$...$$）；图形用原插图的项目根相对路径并在 notes 说明。不能写“见原卷”代替全部题干。
- `answer`：简明最终答案，证明题写已证结论；多子问标清编号。
- `solution`：独立的完整推导 Markdown，保证可读、数学条件准确。校对稿中保留正确独立解法，仅在必要处修正。
- `status`：`solved`、`uncertain` 或 `blocked_by_source`。
- `notes`：字符串数组，记录题干歧义、条件、图形来源等；无则 []。
- 可选 `subparts`：如 [{"label":"(1)","answer":"..."},{"label":"(2)","answer":"..."}]，用于读者定位多子问，主 solution 仍需完整。

final 每题还必须包含：
`"review":{"verdict":"agree"或"equivalent"或"corrected"或"reference_issue"或"unresolved","references":["output/markdown/YYYY/YYYY-solutions.md"],"explanation":"具体说明与参考哪一结论一致，或什么地方不同及推导理由"}`。

严禁伪称人工审核、官方满分或完全客观独立评测。以保存的输入和锁定记录说明过程，未决问题如实保留。质量优先；请完成分配的全部年份，不要只做示例或脚手架。
