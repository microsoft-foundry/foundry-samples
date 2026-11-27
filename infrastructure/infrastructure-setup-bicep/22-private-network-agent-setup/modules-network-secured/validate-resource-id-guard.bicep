@allowed(['valid'])
#disable-next-line no-unused-params
param storageStatus string

@allowed(['valid'])
#disable-next-line no-unused-params
param searchStatus string

@allowed(['valid'])
#disable-next-line no-unused-params
param cosmosStatus string

@allowed(['valid'])
#disable-next-line no-unused-params
param vnetStatus string

@allowed(['valid'])
#disable-next-line no-unused-params
param accountStatus string

param resourceIds array

output resourceIds array = resourceIds
