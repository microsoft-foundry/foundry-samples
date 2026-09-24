param([Parameter(ValueFromRemainingArguments)][string[]]$Arguments)
if (($Arguments -join ' ') -match '/failure403[?]') {
    Write-Error 'ERROR: (AuthorizationFailed) 403 fixture-only-sensitive-sentinel' -ErrorAction Continue
    exit 1
}
if (($Arguments -join ' ') -match '/failure404[?]') {
    Write-Error 'ERROR: (ResourceNotFound) 404 fixture-only-sensitive-sentinel' -ErrorAction Continue
    exit 1
}
if (($Arguments -join ' ') -match '/failure503[?]') {
    Write-Error 'ERROR: (ServiceUnavailable) 503 fixture-only-sensitive-sentinel' -ErrorAction Continue
    exit 1
}
if ('account' -in $Arguments) {
    '{"tenantId":"99999999-9999-9999-9999-999999999999","cloud":"AzureCloud"}'
    exit 0
}
'{"id":"/fixture","properties":{"provisioningState":"Succeeded"}}'
