# Product Analysis

## Key fields

`SalesLT.Product` contains `ProductID`, `Name`, `ProductNumber`, `Color`, `StandardCost`, `ListPrice`, `Size`, `Weight`, `ProductCategoryID`, `ProductModelID`, `SellStartDate`, `SellEndDate`, and `DiscontinuedDate`.

A product is treated as active when both `SellEndDate` and `DiscontinuedDate` are null. The sample has 295 products and 197 active products.

## Category hierarchy

Products are assigned to leaf categories. Join each leaf to its parent:

```sql
SELECT
    parent.Name AS ParentCategory,
    child.Name AS Category,
    COUNT(*) AS ProductCount
FROM SalesLT.Product AS p
JOIN SalesLT.ProductCategory AS child
    ON child.ProductCategoryID = p.ProductCategoryID
LEFT JOIN SalesLT.ProductCategory AS parent
    ON parent.ProductCategoryID = child.ParentProductCategoryID
GROUP BY parent.Name, child.Name
ORDER BY parent.Name, child.Name;
```

The four parent categories are Bikes, Components, Clothing, and Accessories. Do not count their direct product rows; they organize child categories.

## Highest-priced products

```sql
SELECT TOP (10)
    Name,
    ProductNumber,
    Color,
    ListPrice
FROM SalesLT.Product
ORDER BY ListPrice DESC, ProductID;
```

## Catalog margin proxy

Use only when the user asks about list-price margin or catalog economics:

```sql
SELECT TOP (10)
    Name,
    ProductNumber,
    StandardCost,
    ListPrice,
    ListPrice - StandardCost AS CatalogMargin,
    CASE WHEN ListPrice = 0 THEN NULL
         ELSE (ListPrice - StandardCost) / ListPrice
    END AS CatalogMarginRate
FROM SalesLT.Product
WHERE ListPrice > 0
ORDER BY CatalogMargin DESC, ProductID;
```

Label this as a proxy. It does not include realized selling price, fulfillment cost, tax, or freight.

## Product descriptions

For English descriptions, join `Product` -> `ProductModel` -> `ProductModelProductDescription` -> `ProductDescription` and filter `Culture = N'en'`.
