function Invoke-AzureRest {
    param(
        [string] $Method,
        [string] $Uri,
        [string] $Resource,
        [object] $Body,
        [switch] $AllowMissing,
        [string] $ContentType = 'application/json'
    )
    $arguments = @('rest', '--method', $Method, '--url', $Uri, '--resource', $Resource, '--output', 'json')
    $bodyFile = $null
    try {
        if ($null -ne $Body) {
            $bodyFile = Join-Path ([IO.Path]::GetTempPath()) "greeting-$([guid]::NewGuid()).json"
            [IO.File]::WriteAllText($bodyFile, ($Body | ConvertTo-Json -Depth 50), [Text.UTF8Encoding]::new($false))
            $arguments += @('--body', "@$bodyFile", '--headers', "Content-Type=$ContentType")
        }
        $result = az @arguments 2>&1
        if ($LASTEXITCODE -ne 0) {
            if ($AllowMissing -and "$result" -match '(404|Not Found)') { return $null }
            throw "Azure $Method request failed for $Uri`: $result"
        }
        return ($result | Out-String | ConvertFrom-Json)
    }
    finally {
        if ($bodyFile) { Remove-Item -LiteralPath $bodyFile -Force }
    }
}
