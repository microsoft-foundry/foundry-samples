# Sales and Order Analysis

## Dataset boundary

The sample contains 32 orders and 542 order lines. Every order has `OrderDate = 2008-06-01`, so do not present month-over-month or time-series analysis as meaningful.

## Measures

- **Line revenue:** `SalesOrderDetail.LineTotal`
- **Order subtotal:** `SalesOrderHeader.SubTotal`
- **Order total:** `SalesOrderHeader.TotalDue`, including tax and freight
- **Units sold:** `SUM(SalesOrderDetail.OrderQty)`
- **Catalog discount:** `SalesOrderDetail.UnitPriceDiscount`

Never sum `SalesOrderHeader.TotalDue` after joining directly to order details; that repeats the header total once per line.

## Product sales ranking

```sql
SELECT TOP (10)
    p.Name,
    p.ProductNumber,
    SUM(d.OrderQty) AS UnitsSold,
    SUM(d.LineTotal) AS LineRevenue
FROM SalesLT.SalesOrderDetail AS d
JOIN SalesLT.Product AS p ON p.ProductID = d.ProductID
GROUP BY p.Name, p.ProductNumber
ORDER BY LineRevenue DESC, UnitsSold DESC, p.Name;
```

## Sales by category

```sql
SELECT
    parent.Name AS ParentCategory,
    child.Name AS Category,
    SUM(d.OrderQty) AS UnitsSold,
    SUM(d.LineTotal) AS LineRevenue
FROM SalesLT.SalesOrderDetail AS d
JOIN SalesLT.Product AS p ON p.ProductID = d.ProductID
JOIN SalesLT.ProductCategory AS child
    ON child.ProductCategoryID = p.ProductCategoryID
LEFT JOIN SalesLT.ProductCategory AS parent
    ON parent.ProductCategoryID = child.ParentProductCategoryID
GROUP BY parent.Name, child.Name
ORDER BY LineRevenue DESC;
```

## Order economics

```sql
SELECT TOP (10)
    SalesOrderNumber,
    OrderDate,
    SubTotal,
    TaxAmt,
    Freight,
    TotalDue
FROM SalesLT.SalesOrderHeader
ORDER BY TotalDue DESC, SalesOrderID;
```

## Status codes

Interpret `SalesOrderHeader.Status` as:

| Code | Meaning |
| ---: | --- |
| 1 | In process |
| 2 | Approved |
| 3 | Backordered |
| 4 | Rejected |
| 5 | Shipped |
| 6 | Cancelled |

State that these are AdventureWorks status semantics when presenting them.
