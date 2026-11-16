# Access token and facts about the machine running the diagnostic. The token is kept in memory only.

$script:DiagArmResource = 'https://management.azure.com/'
$script:DiagImds = 'http://169.254.169.254/metadata'

function Invoke-DiagImds {
    param([string]$Path, [int]$TimeoutSec = 3)
    Invoke-RestMethod -Uri "$script:DiagImds/$Path" -Headers @{ Metadata = 'true' } -NoProxy -TimeoutSec $TimeoutSec -ErrorAction Stop
}

# A signed-in Az.Accounts session is used first (the person chose that identity); otherwise this VM's managed identity.
function Get-DiagToken {
    param($Ctx)
    $azError = $null
    if (Get-Module -ListAvailable -Name Az.Accounts) {
        try {
            Import-Module Az.Accounts -ErrorAction Stop -WarningAction SilentlyContinue | Out-Null
            if (Get-AzContext -ErrorAction SilentlyContinue) {
                $t = Get-AzAccessToken -ResourceUrl $script:DiagArmResource -ErrorAction Stop -WarningAction SilentlyContinue
                $token = $t.Token
                if ($token -is [securestring]) { $token = ConvertFrom-SecureString -SecureString $token -AsPlainText }
                if ($token) { return @{ Token = $token; Source = 'AzAccounts' } }
            }
        }
        catch { $azError = 'Az.Accounts could not get a token; sign in again with Connect-AzAccount.' }
    }
    try {
        $resource = [uri]::EscapeDataString($script:DiagArmResource)
        $r = & $Ctx.Imds "identity/oauth2/token?api-version=2018-02-01&resource=$resource"
        if ($r.access_token) { return @{ Token = $r.access_token; Source = 'ManagedIdentity' } }
    }
    catch { }
    $message = $(if ($azError) { $azError } else { 'No Azure sign-in found. Run Connect-AzAccount (Az.Accounts module), or run on an Azure VM with a managed identity that has Reader access.' })
    throw [InvalidOperationException]$message
}

function Get-DiagDnsServers {
    try {
        if ($IsWindows -and (Get-Command Get-DnsClientServerAddress -ErrorAction SilentlyContinue)) {
            return @(Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction Stop | ForEach-Object { $_.ServerAddresses } |
                    Where-Object { $_ } | Select-Object -Unique)
        }
        if (Test-Path '/etc/resolv.conf') {
            return @(Get-Content '/etc/resolv.conf' | Where-Object { $_ -match '^\s*nameserver\s+(\S+)' } | ForEach-Object { ($_ -split '\s+')[1] } | Select-Object -Unique)
        }
    }
    catch { }
    @()
}

# Records only whether a proxy is configured and its host; never credentials or full values.
function Get-DiagProxy {
    $system = 'none'
    try {
        $target = [uri]'https://management.azure.com/'
        $proxy = [Net.WebRequest]::GetSystemWebProxy().GetProxy($target)
        if ($proxy -and $proxy -ne $target) { $system = $proxy.Host }
    }
    catch { }
    $env = @('HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY', 'NO_PROXY' | Where-Object { [Environment]::GetEnvironmentVariable($_) -or [Environment]::GetEnvironmentVariable($_.ToLowerInvariant()) })
    [ordered]@{ system = $system; env = $env }
}

function Get-DiagRunnerVmId {
    param($Ctx)
    try {
        $compute = & $Ctx.Imds 'instance/compute?api-version=2021-02-01'
        if ($compute.resourceId -and (Test-DiagArmPath $compute.resourceId)) { return $compute.resourceId }
    }
    catch { }
    $null
}

function Get-DiagRunnerInfo {
    param($Ctx)
    [ordered]@{
        os                = $(if ($IsWindows) { 'Windows' } elseif ($IsMacOS) { 'macOS' } else { 'Linux' })
        tokenSource       = $Ctx.TokenSource
        azureVmResourceId = (Get-DiagRunnerVmId $Ctx)
        dnsServers        = @(& $Ctx.DnsServers)
        proxy             = (& $Ctx.Proxy)
    }
}
