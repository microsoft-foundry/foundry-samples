# Customer and Location Analysis

## Key fields

Use `SalesLT.Customer` for names, `CompanyName`, `SalesPerson`, and contact fields. Never select `PasswordHash` or `PasswordSalt`.

Use `SalesLT.CustomerAddress` to connect customers to `SalesLT.Address`. A customer can have multiple addresses, so filter or group by `AddressType` when counting customers by geography.

## Largest customers by order total

Do not join order details for this metric. Sum one header total per order:

```sql
SELECT TOP (10)
    c.CustomerID,
    c.CompanyName,
    COUNT(*) AS Orders,
    SUM(h.TotalDue) AS TotalOrderValue
FROM SalesLT.Customer AS c
JOIN SalesLT.SalesOrderHeader AS h
    ON h.CustomerID = c.CustomerID
GROUP BY c.CustomerID, c.CompanyName
ORDER BY TotalOrderValue DESC, c.CompanyName;
```

The dataset has 847 customer records and 439 distinct non-null companies, but only customers with order headers contribute to sales rankings.

## Customer order detail

```sql
SELECT TOP (25)
    h.SalesOrderNumber,
    h.OrderDate,
    p.Name AS Product,
    d.OrderQty,
    d.UnitPrice,
    d.UnitPriceDiscount,
    d.LineTotal
FROM SalesLT.SalesOrderHeader AS h
JOIN SalesLT.SalesOrderDetail AS d
    ON d.SalesOrderID = h.SalesOrderID
JOIN SalesLT.Product AS p
    ON p.ProductID = d.ProductID
WHERE h.CustomerID = @CustomerID
ORDER BY h.SalesOrderID, d.SalesOrderDetailID;
```

Replace `@CustomerID` with a validated integer literal because the MCP query tool does not expose a formal-parameter binding workflow.

## Customers by location

Use shipping addresses for fulfilled-order geography:

```sql
SELECT
    a.CountryRegion,
    a.StateProvince,
    COUNT(DISTINCT h.CustomerID) AS Customers,
    COUNT(*) AS Orders,
    SUM(h.TotalDue) AS TotalOrderValue
FROM SalesLT.SalesOrderHeader AS h
JOIN SalesLT.Address AS a
    ON a.AddressID = h.ShipToAddressID
GROUP BY a.CountryRegion, a.StateProvince
ORDER BY TotalOrderValue DESC;
```

For customer-master geography instead, use `CustomerAddress` and explain that customers can have multiple address records.
