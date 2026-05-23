---
name: warehouse-rent-email
description: Generate Chinese approval email copy for warehouse temporary-rent procurement projects from screenshots, images, pasted tables, Excel snippets, OCR text, warehouse lease contract content/files, or newly inserted rows produced by the 仓租采购需求整理 skill. Use this skill whenever the user mentions 仓租、临租、仓库租赁、仓租合同、临租合同、租赁协议、采购项目、商务条件确认、审批邮件, asks to turn a warehouse rent table/image/contract into an email, or has just completed 仓租采购需求整理 and needs the approval email, even if they do not explicitly say "use the skill".
---

# Warehouse Rent Procurement Email

Use this skill to convert a warehouse temporary-rent procurement table, contract-derived demand rows, or newly inserted workbook rows into a polished Chinese approval email body.

The user usually provides a screenshot, pasted table, contract file/text, or a row summary with fields like 仓库、临租面积、起租日期、到期日期、主合同单价、临租单价、租赁时间、免租期、实际单价、降幅. Your output should be an email正文 that can be pasted directly into an approval flow.

This skill also acts as the second step after `/Users/bukeyitoukano/.claude/skills/仓租采购需求整理`: when that skill fills new rows in `仓库临租需求.xlsx`, including rows extracted from a contract, generate the approval email from only those newly inserted rows.

## Workflow

1. Read the input table.
   - If the input is an image, visually extract all rows and columns.
   - If the input is a lease contract file or copied contract text, extract only the procurement-demand fields needed for the email. Do not perform a legal contract review unless the user asks for one.
   - If the input is a “newly inserted rows” summary from 仓租采购需求整理, use those rows directly.
   - If the input is a “contract-derived rows” summary from 仓租采购需求整理, use those rows directly and carry over concise business notes such as 原仓临租、定向议价、周边仓源最低、市场价说明.
   - If OCR is uncertain, preserve the likely value and flag only the uncertain cells at the end.
   - Treat rows with the same warehouse name as belonging to the same warehouse summary.

2. Extract these columns when present:
   - 仓库
   - 临租面积（平方米）
   - 起租日期
   - 到期日期
   - 主合同单价（元/平/日）
   - 临租单价（元/平/日）
   - 租赁时间（天/不含免租期）
   - 租赁时间（天/含免租期）
   - 免租期（天）
   - 实际单价（元/平/日）
   - 降幅
   - 总租金/含税总金额
   - 业务备注/价格说明

3. Calculate or verify key numbers.
   - 面积合计：同一仓库多行时求和。
   - 含税总金额：如果输入来自仓租采购需求整理，优先使用 M 列“总租金”。
   - 如果没有 M 列金额，使用 `临租面积 * 临租单价 * 租赁时间（天/含免租期）`。
   - 如果只有实际单价，使用 `临租面积 * 实际单价 * 租赁时间（天/含免租期）`。
   - 金额展示单位优先为“万元”，保留 2 位小数；若用户表格或上下文已有金额，以用户值为准。
   - 降幅为正数时写“较主合同单价降幅X%”；负数时写“较主合同单价涨幅X%”。
   - 若同一仓库多行且单价/日期不同，逐段写清楚，不要强行合并成一个租期。

4. Identify business notes.
   - 若备注说明“原仓临租”“周边仓源最低”“定向议价”等，要写入邮件说明。
   - 若某仓库临租价高于主合同价，但原因是周边仓源中价格最低、主合同约定租金上涨、旺季短租等，要单独说明。
   - 若信息来自合同，只使用合同中已经抽取出的采购事实和业务原因，不在邮件里展开合同条款原文。

5. Generate the email body using the template below.

## Email Template

Use this structure unless the user asks for a different style:

```text
[收件人称呼]，上午好/下午好

基于我司近期业务需求，以下仓需要新增临租面积满足高峰期使用需求，现已完成仓库商务条件确认，具体内容如下：

[按仓库逐条汇总]

[必要的价格差异/定向议价/市场价说明]

以上，请审批
```

Default salutation:
- If the user names a recipient, use `[姓名]，上午好/下午好` based on context.
- If no recipient is given, use `各位好`.
- If the provided example contains a specific recipient, mirror that style.

## Warehouse Summary Style

Write one paragraph per warehouse. Keep it compact, factual, and approval-ready.

Single-line warehouse:

```text
[仓库]：本次临租面积[面积]平，租期为[起租日期]-[到期日期]，含税单价为[实际单价]元/平/日，较主合同单价[降幅/涨幅][百分比]，含税总金额为[金额]万元
```

Multi-line same warehouse:

```text
[仓库]：本次临租面积[面积1]+[面积2]平，[面积1]平租期为[起租日期1]-[到期日期1]，[面积2]平租期为[起租日期2]-[到期日期2]，含税单价为[实际单价]元/平/日，较主合同单价[降幅/涨幅][百分比]，含税总金额为[金额]万元
```

If the same warehouse has different actual prices, mention each segment:

```text
[仓库]：本次临租面积[面积1]+[面积2]平，[面积1]平租期为[日期1]，含税单价为[单价1]元/平/日；[面积2]平租期为[日期2]，含税单价为[单价2]元/平/日，整体含税总金额为[金额]万元
```

## Wording Rules

- Use Chinese punctuation.
- Use “平” in prose, even if the table says “平方米”.
- Dates should use `YYYY.M.D` style in the email body, for example `2026.5.1-2026.7.31`.
- Keep numbers faithful to the source table; do not round areas unless they are clearly whole numbers.
- Use “含税单价” for actual/settlement price.
- Use “主合同单价” for the benchmark contract price.
- Use “较主合同” when comparing against the contract price.
- Do not include Markdown tables in the final email unless the user explicitly asks for a table.
- Do not invent approvers, departments, supplier names, or business reasons not present in the input.
- Do not invent contract reasons. If the contract/source row only contains price and term values, write the normal approval summary and leave原因为空.
- If information is missing, write a clean draft and add a short “需确认” section after the email body.

## Price Explanation Rules

Add a separate explanatory paragraph when:

- Any warehouse has a negative 降幅, meaning price is higher than main contract.
- The input includes market or negotiation notes.
- Some rows are 定向议价 or 周边仓源最低价.

Example:

```text
沈阳主合同价格低于市场价，故本次临租价格高于主合同价格，但仍为周围仓源中价格最优；天津主合同约定租金年涨幅为3%，故今年临租价格较主合同有效价上涨3%。
```

## Final Self-Check

Before answering, verify:

- Every table row is represented in the email.
- Same-warehouse rows are grouped correctly.
- Dates and areas match the input.
- Positive 降幅 is written as 降幅; negative 降幅 is written as 涨幅.
- Total amount math is plausible.
- The final answer contains only the email draft plus a short confirmation note if needed.

## Example

Input summary:

```text
福州（一轮）：1200平，2026/5/1-2026/7/31，实际单价0.391，降幅9.00%；1000平，2026/5/16-2026/7/31，实际单价0.390，降幅9.39%
沈阳仓库：718.6平，2026/5/2-2026/6/30，实际单价0.330，降幅-3.13%；718.6平，2026/5/11-2026/6/30，实际单价0.330，降幅-3.13%
备注：沈阳主合同价格低于市场价，本次临租价格高于主合同价格，但仍为周围仓源中价格最优。
```

Output:

```text
各位好

基于我司近期业务需求，以下仓需要新增临租面积满足高峰期使用需求，现已完成仓库商务条件确认，具体内容如下：

福州（一轮）：本次临租面积1200+1000平，1200平租期为2026.5.1-2026.7.31，1000平租期为2026.5.16-2026.7.31，含税单价分别为0.391元/平/日、0.390元/平/日，较主合同单价降幅约9%，含税总金额为7.32万元
沈阳仓库：本次临租面积718.6+718.6平，718.6平租期为2026.5.2-2026.6.30，另718.6平租期为2026.5.11-2026.6.30，含税单价为0.330元/平/日，较主合同单价涨幅3.13%，含税总金额为2.63万元

沈阳主合同价格低于市场价，故本次临租价格高于主合同价格，但仍为周围仓源中价格最优。

以上，请审批
```
