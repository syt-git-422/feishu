---
name: warehouse-rent-demand-fill
description: Fill the warehouse temporary-rent demand Excel template from newly provided warehouse leasing information or from warehouse lease contract content/files, then automatically generate the warehouse rent procurement approval email copy. Use this skill whenever the user sends 新增仓库租赁信息、仓库临租需求、临租填表、仓租需求、仓租合同、临租合同、租赁协议, or asks Claude Code to update 仓库临租需求_已填.xlsx. It must extract required demand fields from text, pasted tables, screenshots, PDFs, Word contracts, or contract text when available; auto-fill fields by the template headers; ask follow-up questions only for missing or conflicting required information; look up column F from existing rows; calculate G from M or M from G; carry formulas for N/O/P/Q; and after successful filling continue into the 仓租采购审批邮件生成 workflow unless the user explicitly says only fill the table.
---

# Warehouse Temporary-Rent Demand Fill

Use this skill to update the warehouse temporary-rent demand workbook from newly provided leasing information or warehouse lease contract content, then generate the approval email content from the newly inserted rows.

Default template path:

```text
/Users/bukeyitoukano/Desktop/工作标准/仓库临租需求_已填.xlsx
```

Default sheet:

```text
26年618临租
```

The workbook currently uses columns A-Q:

| Column | Header | Fill rule |
| --- | --- | --- |
| A | 序号 | Keep blank unless the user asks otherwise. |
| B | 仓库 | Fill from user input. For continuation rows of the same warehouse, follow the workbook style and allow blank B only when the previous row is the same warehouse. |
| C | 临租面积（平方米） | Required. |
| D | 起租日期 | Required. |
| E | 到期日期 | Required. |
| F | 主合同单价（元/平/日） | Auto-search existing rows first. Ask the user if no reliable match is found. |
| G | 临租单价（元/平/日） | Required only if M is missing. If M is present, calculate `G=M/I/C`. |
| H | 租赁时间（天/不含免租期） | Calculate from dates unless user provides it. Default formula: `=E[row]-D[row]+1`. |
| I | 租赁时间（天/含免租期） | Required directly or calculable from H and J. If missing and J is missing, default to H only after confirming no免租期. |
| J | 免租期（天） | Use user input; if not provided, use 0 only when the context clearly says no免租期. Otherwise ask. |
| K | 实际单价（元/平/日） | Follow template formula, normally `=G[row]*H[row]/I[row]` or `=G[row]` when H and I are equal. |
| L | 降幅 | Formula: `=(F[row]-K[row])/F[row]`. |
| M | 总租金 | Required only if G is missing. If G is present, calculate `M=C*G*I`. |
| N | 降本前 | Copy/adapt existing formula, normally `=F[row]*I[row]*C[row]`. |
| O | 降本金额 | Copy/adapt existing formula, normally `=N[row]-M[row]`. |
| P | 降本比例-大 | Copy/adapt existing formula, normally `=O[row]/N[row]`. |
| Q | 降本比例-小 | Copy/adapt existing formula, normally `=O[row]/M[row]`. |

## Required Intake

Before editing the workbook, extract one record per leasing row from the user's message, attachment, screenshot, or contract content.

Each record needs:

- 仓库
- 临租面积
- 起租日期
- 到期日期
- 免租期 or 租赁时间（天/含免租期） or explicit “无免租期”
- 临租单价 G or 总租金 M
- 主合同单价 F, unless it can be found from existing rows

Accept these input sources:

- Direct text from the user.
- Pasted table or OCR text.
- Screenshot/image of a demand table or contract.
- Contract files such as `.pdf`, `.docx`, or text copied from a warehouse lease contract.
- A mix of contract content plus user notes.

If any required field is missing, ask a concise follow-up question before writing the file. Group missing fields by warehouse/row.

Examples of follow-up questions:

```text
还差 2 个信息我才能填表：
1. 成都仓库：免租期是多少天？如果没有免租期，我按 0 天处理。
2. 天津仓库：你给了总租金但没有含免租租赁天数，是否按起止日期自然天计算？
```

## Contract Intake

When the user provides a warehouse lease contract, rental agreement, contract draft, contract screenshot, or copied contract text, treat the contract as a source for adding demand rows. Extract the demand fields from the contract first, then apply the same workbook lookup, calculation, and validation rules as direct text input.

Read the contract content carefully and map common contract clauses to demand fields:

| Demand field | Contract clues to search |
| --- | --- |
| 仓库 | 标的仓库、租赁场地、仓库名称、项目名称、租赁地址、仓库地址、甲方/乙方约定的场地名称 |
| 临租面积 | 租赁面积、计租面积、建筑面积、使用面积、临租面积, with units 平方米、㎡、平 |
| 起租日期 | 租赁期限起始日、起租日、交付日、计租开始日、生效日期 when it clearly starts billing |
| 到期日期 | 租赁期限截止日、终止日、到期日、租赁期满日 |
| 免租期 | 免租期、装修免租、免租天数、免计租期；if the contract says 无免租期/不设免租期, set `free_days` to 0 |
| 租赁时间（含免租期） | 合同明确写明的总租赁天数、租赁期限天数、含免租期天数 |
| 临租单价 G | 租金单价、含税单价、日租金单价、元/平/日、元/平方米/天 |
| 总租金 M | 租金总额、合同总价、含税总金额、租赁费合计、应付租金合计 |
| 主合同单价 F | 主合同单价、原合同单价、基础合同租金；若合同未写，仍按 F Column Lookup 从需求表历史行检索 |
| 业务备注 | 原仓临租、定向议价、周边仓源最低、市场价、旺季短租、主合同约定涨幅、价格说明 |

Contract extraction rules:

- If one contract contains multiple warehouses, multiple lease periods, or stepped prices, create one record per distinct warehouse/period/price segment.
- Prefer explicit contract values over inferred values. Use calculations only after the explicit fields are collected.
- Treat 含税/不含税 wording as evidence. The demand workbook and email use含税口径; if the contract only provides不含税价格 and no tax conversion is stated, ask before writing.
- If the contract gives a monthly, yearly, or total-period rent but not 元/平/日, calculate G only when area and含免租租赁天数 are clear. Otherwise ask.
- If dates are written as Chinese dates such as `2026年5月12日`, normalize them to ISO format in `records.json`.
- If the contract states a lease term such as `自交付之日起60天` but the actual交付/起租日期 is missing, ask for the missing date.
- If there are amendments, annexes, handwritten notes, or user notes that conflict with the contract body, ask which value should prevail before writing.
- Keep short evidence notes for each extracted record so the final response can say which contract clauses supplied key fields. Do not put evidence notes into workbook cells unless the user asks.

Example contract-derived `records.json` item:

```json
{
  "warehouse": "天津（二轮）",
  "area": 2433.12,
  "start_date": "2026-05-12",
  "end_date": "2026-06-30",
  "free_days": 0,
  "rent_days_with_free": 50,
  "temp_unit_price": null,
  "total_rent": 38917.75,
  "main_contract_price": null,
  "source": "contract",
  "evidence": {
    "area": "租赁面积为2433.12平方米",
    "term": "租期自2026年5月12日至2026年6月30日",
    "amount": "含税租金总额38917.75元"
  }
}
```

The bundled fill script ignores extra keys like `source` and `evidence`, so they are safe to keep in `records.json` for auditability.

## F Column Lookup

Column F is 主合同单价. Search existing workbook rows before asking the user.

Lookup order:

1. Exact match on column B.
2. Match after normalizing warehouse names:
   - Remove spaces.
   - Remove `仓库`.
   - Remove round labels like `（二轮）`、`(二轮)`、`（三轮）`.
   - Treat blank B rows as continuation of the previous non-empty warehouse name.
3. If multiple matches exist, prefer the latest matching data row with a non-empty F.
4. If values conflict for the same normalized warehouse, ask the user to confirm.

Never invent F. If lookup fails, ask.

## G and M Mutual Calculation

The user only needs to provide one of G or M.

- If G is provided and M is missing, set M as `=C[row]*G[row]*I[row]`.
- If M is provided and G is missing, set G as `=M[row]/I[row]/C[row]`.
- If both are provided, keep both and verify that `M` is close to `C*G*I`; if the difference is material, ask before writing.

Use the user's explicitly requested rule above even if older workbook rows use a different H-based total-rent formula.

## Formula Rules

For new rows:

- H: use `=E[row]-D[row]+1` unless the user provides an explicit H value.
- I: if user provides I, use it. Else set `=H[row]+J[row]`.
- K: if G is a value or formula, set `=G[row]*H[row]/I[row]`.
- L: set `=(F[row]-K[row])/F[row]`.
- N: set `=F[row]*I[row]*C[row]`.
- O: set `=N[row]-M[row]`.
- P: set `=O[row]/N[row]`.
- Q: set `=O[row]/M[row]`.

Also copy formatting, number formats, borders, fills, alignment, and row height from the nearest existing data row.

## Editing Procedure

Prefer using the bundled script:

```bash
python scripts/fill_warehouse_rent_demand.py \
  --workbook "/Users/bukeyitoukano/Desktop/工作标准/仓库临租需求_已填.xlsx" \
  --records records.json
```

By default, save changes directly back to the original workbook specified by `--workbook`. Do not create a new workbook unless the user explicitly asks for a copy or test output.

Create `records.json` from the user's message. Format:

```json
[
  {
    "warehouse": "天津（二轮）",
    "area": 2433.12,
    "start_date": "2026-05-12",
    "end_date": "2026-06-30",
    "free_days": 0,
    "rent_days_with_free": 50,
    "temp_unit_price": 0.32,
    "total_rent": null,
    "main_contract_price": null
  }
]
```

Field notes:

- `main_contract_price` may be `null`; the script will look it up from F.
- Provide exactly one or both of `temp_unit_price` and `total_rent`.
- Use ISO dates (`YYYY-MM-DD`) in JSON.
- Use numbers, not strings, for area, prices, days, and amount.
- For contract-derived records, optionally include `source: "contract"` and an `evidence` object with short source snippets for human checking.

Insert new records after the last contiguous data row and before helper/summary rows. In the current workbook this is after row 38.

## Linked Email Generation

After the workbook is updated successfully, automatically generate the procurement approval email body. Do this in the same response unless the user explicitly says “只填表”“不要生成邮件”“先不写邮件”.

Use the companion skill:

```text
/Users/bukeyitoukano/.claude/skills/仓租采购审批邮件生成
```

Pass only the newly inserted rows to the email-generation step, not the whole historical workbook. Build a compact row summary with these fields:

- 仓库：B
- 临租面积：C
- 起租日期：D
- 到期日期：E
- 主合同单价：F
- 临租单价：G
- 租赁时间（不含免租期）：H
- 租赁时间（含免租期）：I
- 免租期：J
- 实际单价：K
- 降幅：L
- 总租金：M

If formula values have not been recalculated by Excel yet, calculate the values yourself from the row data:

- G: if formula is `M/I/C`, calculate from M, I, C.
- K: calculate `G*H/I`.
- L: calculate `(F-K)/F`.
- M: if formula is `C*G*I`, calculate from C, G, I.

Email amount should use M converted to 万元 and rounded to 2 decimals.

If multiple new rows belong to the same warehouse, group them in the email according to the email skill’s same-warehouse rules.

If the user provided business notes such as 原仓临租、定向议价、周边仓源最低、价格高于主合同原因, pass those notes to the email skill and include them in the approval email.

If the demand rows came from a contract, pass along extracted business notes and a brief source summary to the email-generation step. Do not paste long contract clauses into the email; use the extracted table values and concise business reasons only.

## Automatic Feishu Sending

After the approval email draft is generated, automatically send it to Feishu when Feishu webhook configuration is available. Do not ask for a second confirmation unless the user explicitly requested a review-before-send workflow.

Use the bundled script:

```bash
python scripts/send_feishu_message.py --text email_body.txt
```

Configuration:

- Preferred secure storage: macOS Keychain.
  - Webhook service name: `codex-feishu-webhook`
  - Optional signature secret service name: `codex-feishu-webhook-secret`
  - Account name: `warehouse-rent-demand-fill`
- Environment variable fallback:
  - `FEISHU_WEBHOOK_URL`: required if Keychain is not configured.
  - `FEISHU_WEBHOOK_SECRET`: optional. Use it when the Feishu bot has signature verification enabled.

Security rules:

- Never write the webhook URL or secret into `SKILL.md`, `records.json`, logs, or the workbook.
- If neither Keychain nor `FEISHU_WEBHOOK_URL` is configured, do not pretend the message was sent. Tell the user that the email draft is ready but Feishu sending needs webhook configuration.
- If sending fails, keep the email draft in the final response and report the failure reason briefly.

Recommended full workflow:

1. Fill the workbook in place.
2. Generate approval email body from newly inserted rows.
3. Save the email body to a temporary text file.
4. Call `scripts/send_feishu_message.py --text <temp-file>`.
5. Report “已发送至飞书” only after the script returns success.

## Feishu Inbound Trigger

When the user wants Feishu to be the input port, use the bundled inbound service:

```bash
python3 scripts/feishu_inbound_service.py --port 8787
```

This service is for Feishu self-built app bots with event subscription enabled. It accepts URL verification, listens for `im.message.receive_v1`, downloads message attachments, calls Codex CLI with this skill, and replies to the original Feishu message with the workflow result.

Required environment variables:

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`

Optional environment variables:

- `FEISHU_VERIFICATION_TOKEN`
- `FEISHU_INBOUND_PORT`
- `FEISHU_WORKFLOW_TIMEOUT_SECONDS`
- `FEISHU_WORKFLOW_COMMAND` for replacing the default Codex CLI command

Use a public HTTPS URL or an intranet tunnel to expose the service endpoint to Feishu. Keep secrets in environment variables or Keychain; never write app secrets into skill files, records, logs, or workbook cells.

## Output To User

After filling the workbook, report:

- Updated workbook path.
- Rows inserted.
- Any F values auto-filled from lookup.
- Any G/M values calculated.
- For contract-derived rows, the key contract evidence used for extraction.
- Approval email draft.
- Feishu send status, such as 已发送至飞书 or 未发送：缺少 FEISHU_WEBHOOK_URL.
- Any fields that still need confirmation.

Do not provide a long explanation unless the user asks.

## Self-Check

Before final response:

- Confirm no row was written with missing warehouse, area, start date, end date, F, and at least one of G/M.
- For contract-derived rows, confirm each required value is either explicitly supported by contract text, calculated from supported values, or confirmed by the user.
- Confirm every new row has formulas or values in G, H, I, K, L, M, N, O, P, Q.
- Confirm N/O/P/Q formulas reference the same row number.
- Confirm the workbook was saved in place only after all required-field checks passed.
- Confirm the email draft uses only the newly inserted rows and matches the newly filled workbook values.
- Confirm Feishu send status is truthful and based on the script result.
