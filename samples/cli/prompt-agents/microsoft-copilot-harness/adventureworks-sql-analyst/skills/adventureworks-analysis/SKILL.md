---
name: adventureworks-analysis
description: Use this skill whenever the user asks about AdventureWorksLT products, categories, pricing, customers, addresses, orders, sales, revenue, or database structure. It provides verified joins, metric definitions, and read-only SQL patterns for the deployed sample database.
---

# AdventureWorksLT Analysis

Use the Azure SQL MCP tools to answer business questions from the deployed AdventureWorksLT sample.

## Choose the minimum reference

Read only the reference needed for the request:

| Question | Reference |
| --- | --- |
| Unknown tables, columns, keys, or joins | [references/schema.md](references/schema.md) |
| Products, prices, models, categories, or product descriptions | [references/products.md](references/products.md) |
| Orders, revenue, quantities, sales ranking, or order status | [references/sales.md](references/sales.md) |
| Customers, companies, locations, or customer order value | [references/customers.md](references/customers.md) |

For a cross-domain question, read each relevant reference. Do not load every reference by default.

## Query workflow

1. Clarify an ambiguous metric only when different interpretations would materially change the result.
2. Use `sql_GetTables_V2` if the requested area is unfamiliar.
3. Prefer `sql_GetItems_V2` for simple reads from one table.
4. Use `sql_ExecutePassThroughNativeQuery_V2` for joins and aggregates.
5. Generate only bounded `SELECT` statements. Never generate data modification, DDL, permission, or procedure-execution statements.
6. Qualify all business tables with `SalesLT`.
7. Limit detailed output to 25 rows unless the user requests another bound.
8. State the tables and metric definition used, especially for revenue and customer rankings.

## Dataset cautions

- This is a small demonstration dataset, not current production data.
- It contains 32 orders, all dated June 1, 2008. Do not claim a meaningful time trend from it.
- Never query or return `Customer.PasswordHash` or `Customer.PasswordSalt`.
- Product parent categories contain no products directly. Aggregate through their child categories.
- `SalesOrderDetail.LineTotal` is the line-level realized amount after quantity and discount.
- `SalesOrderHeader.TotalDue` includes subtotal, tax, and freight. Sum it once per order, never after joining to detail rows unless you first deduplicate orders.
- `ListPrice - StandardCost` is only a catalog margin proxy, not realized profit.

## Response style

Lead with the answer, then show a compact table or short list. Include the row limit when results are truncated. Add one sentence describing the metric or join when it is not obvious.
