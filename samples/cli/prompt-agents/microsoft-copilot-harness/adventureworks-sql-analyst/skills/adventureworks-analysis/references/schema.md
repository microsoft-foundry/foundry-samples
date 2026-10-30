# AdventureWorksLT Schema Map

## Business tables

| Table | Rows | Purpose |
| --- | ---: | --- |
| `SalesLT.Product` | 295 | Product catalog, prices, costs, category, and model |
| `SalesLT.ProductCategory` | 41 | Two-level product category hierarchy |
| `SalesLT.ProductModel` | 128 | Product model names and catalog XML |
| `SalesLT.ProductDescription` | 762 | Localized descriptions |
| `SalesLT.ProductModelProductDescription` | 762 | Model-to-description bridge with culture |
| `SalesLT.Customer` | 847 | People, companies, salespeople, and contact details |
| `SalesLT.Address` | 450 | Postal addresses |
| `SalesLT.CustomerAddress` | 417 | Customer-to-address bridge and address type |
| `SalesLT.SalesOrderHeader` | 32 | One row per order, customer, dates, and totals |
| `SalesLT.SalesOrderDetail` | 542 | Order lines, products, quantities, prices, and discounts |

Ignore `dbo.BuildVersion` and `dbo.ErrorLog` for business analysis.

## Verified joins

```sql
SalesLT.Product.ProductCategoryID
  -> SalesLT.ProductCategory.ProductCategoryID

SalesLT.Product.ProductModelID
  -> SalesLT.ProductModel.ProductModelID

SalesLT.ProductCategory.ParentProductCategoryID
  -> SalesLT.ProductCategory.ProductCategoryID

SalesLT.SalesOrderDetail.ProductID
  -> SalesLT.Product.ProductID

SalesLT.SalesOrderDetail.SalesOrderID
  -> SalesLT.SalesOrderHeader.SalesOrderID

SalesLT.SalesOrderHeader.CustomerID
  -> SalesLT.Customer.CustomerID

SalesLT.SalesOrderHeader.ShipToAddressID
  -> SalesLT.Address.AddressID

SalesLT.SalesOrderHeader.BillToAddressID
  -> SalesLT.Address.AddressID

SalesLT.CustomerAddress.CustomerID
  -> SalesLT.Customer.CustomerID

SalesLT.CustomerAddress.AddressID
  -> SalesLT.Address.AddressID
```

## Discovery query

Use this only when a question needs columns not covered by the focused references:

```sql
SELECT
    s.name AS SchemaName,
    t.name AS TableName,
    c.column_id,
    c.name AS ColumnName,
    ty.name AS DataType,
    c.is_nullable
FROM sys.tables AS t
JOIN sys.schemas AS s ON s.schema_id = t.schema_id
JOIN sys.columns AS c ON c.object_id = t.object_id
JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
WHERE s.name = N'SalesLT'
ORDER BY t.name, c.column_id;
```

Do not query credential columns in `SalesLT.Customer`: `PasswordHash` and `PasswordSalt`.
