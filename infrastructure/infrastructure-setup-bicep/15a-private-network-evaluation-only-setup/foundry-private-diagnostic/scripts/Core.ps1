# Core types and helpers shared by checks and reports. No I/O here.

$script:DiagAreas = @('Project', 'Subnet', 'PrivateEndpoint', 'Dns', 'Nsg', 'Egress', 'Firewall', 'Nva',
    'Storage', 'Monitoring', 'Models', 'Access', 'Probe', 'Runner')
$script:DiagPaths = @('Foundry', 'Storage', 'MonitorQuery', 'Models')
$script:DiagLayers = @('Name', 'Route', 'Nsg', 'Firewall', 'Tls', 'Response', 'Access', 'Config')
$script:DiagStatuses = @('OK', 'Problem', 'CouldNotCheck')
$script:DiagSeverities = @('High', 'Medium', 'Low')
$script:DiagGaps = @('Blocking', 'KnownLimit')
$script:DiagOwners = @('AzureAdmin', 'NetworkTeam', 'ResourceOwner', 'Customer')
$script:DiagSchema = 1

function New-DiagResult {
    param(
        [Parameter(Mandatory)][string]$Id,
        [Parameter(Mandatory)][string]$Area,
        [Parameter(Mandatory)][string]$Title,
        [Parameter(Mandatory)][ValidateSet('OK', 'Problem', 'CouldNotCheck')][string]$Status,
        [ValidateSet('High', 'Medium', 'Low')][string]$Severity,
        [ValidateSet('Blocking', 'KnownLimit')][string]$Gap,
        [ValidateSet('Azure', 'ThisMachine')][string]$Scope = 'Azure',
        [string]$Path,
        [Parameter(Mandatory)][ValidateSet('Name', 'Route', 'Nsg', 'Firewall', 'Tls', 'Response', 'Access', 'Config')][string]$Layer,
        [string]$Resource,
        [string]$Seen,
        [string]$Likely,
        [ValidateSet('AzureAdmin', 'NetworkTeam', 'ResourceOwner', 'Customer')][string]$Owner,
        [string]$Action,
        [string]$Needs,
        [string[]]$Evidence = @(),
        [hashtable]$Details = @{}
    )
    if ($Area -notin $script:DiagAreas) { throw "Unknown area '$Area'." }
    if ($Path -and $Path -notin $script:DiagPaths) { throw "Unknown path '$Path'." }
    if ($Status -eq 'Problem' -and !$Severity) { throw "Problem result '$Id' needs a severity." }
    if ($Status -ne 'Problem' -and $Severity) { throw "Only Problem results have a severity ('$Id')." }
    if ($Status -eq 'CouldNotCheck' -and (!$Gap -or !$Needs)) { throw "CouldNotCheck result '$Id' needs a gap and needs." }
    if ($Status -ne 'CouldNotCheck' -and $Gap) { throw "Only CouldNotCheck results have a gap ('$Id')." }
    if ($Likely -and $Likely -notmatch '^Consistent with ') { throw "Likely must start with 'Consistent with' ('$Id')." }
    [ordered]@{
        id       = $Id
        key      = "$Id|$Resource|$Path"
        area     = $Area
        title    = $Title
        status   = $Status
        severity = $(if ($Severity) { $Severity } else { $null })
        gap      = $(if ($Gap) { $Gap } else { $null })
        scope    = $Scope
        path     = $(if ($Path) { $Path } else { $null })
        layer    = $Layer
        resource = $(if ($Resource) { $Resource } else { $null })
        seen     = $(if ($Seen) { $Seen } else { $null })
        likely   = $(if ($Likely) { $Likely } else { $null })
        owner    = $(if ($Owner) { $Owner } else { $null })
        action   = $(if ($Action) { $Action } else { $null })
        needs    = $(if ($Needs) { $Needs } else { $null })
        evidence = @($Evidence)
        details  = $Details
        offPath  = $false
    }
}

function Get-DiagRequestKey {
    param([string]$Path, [string]$Method = 'GET')
    "$Method $Path"
}

# Looks up one collected request. Read=$false means this evidence never asked for it.
function Get-Ev {
    param([Parameter(Mandatory)]$Evidence, [string]$Path, [string]$Method = 'GET')
    $key = Get-DiagRequestKey $Path $Method
    if (!$Path) { return @{ Read = $false; Ok = $false; Status = $null; ErrorKind = $null; Data = $null; Key = $key; Path = $Path } }
    if (!$Evidence.Contains('_index')) {
        $index = @{}
        foreach ($request in @($Evidence.requests)) { $index[$request.key.ToLowerInvariant()] = $request }
        $Evidence['_index'] = $index
    }
    $request = $Evidence['_index'][$key.ToLowerInvariant()]
    if (!$request) { return @{ Read = $false; Ok = $false; Status = $null; ErrorKind = $null; Data = $null; Key = $key; Path = $Path } }
    @{
        Read      = $true
        Ok        = ($request.status -eq 200)
        NotFound  = ($request.status -eq 404)
        Status    = $request.status
        ErrorKind = $request.errorKind
        Data      = $request.data
        Key       = $key
        Path      = $Path
    }
}

function Get-EvRef {
    param($Read)
    "request:$($Read.Key)"
}

function Get-ArmScopeName {
    param([string]$Id)
    if ($Id -match '(?i)^(/subscriptions/[^/]+/resourceGroups/[^/]+)') { return $Matches[1] }
    if ($Id -match '(?i)^(/subscriptions/[^/]+)') { return $Matches[1] }
    $Id
}

function Get-ArmName {
    param([string]$Id)
    if (!$Id) { return $null }
    ($Id.TrimEnd('/') -split '/')[-1]
}

function Get-ArmParent {
    param([string]$Id, [int]$Levels = 1)
    if (!$Id) { return $null }
    $parts = $Id.TrimEnd('/') -split '/'
    ($parts[0..($parts.Count - 1 - 2 * $Levels)]) -join '/'
}

function Test-SameArmId {
    param([string]$A, [string]$B)
    $A -and $B -and ($A.TrimEnd('/') -ieq $B.TrimEnd('/'))
}

# Turns an unreadable request into a CouldNotCheck result, or returns $null when the read succeeded or was a 404.
function New-ReadGap {
    param(
        [Parameter(Mandatory)]$Read,
        [Parameter(Mandatory)][string]$Id,
        [Parameter(Mandatory)][string]$Area,
        [Parameter(Mandatory)][string]$Title,
        [Parameter(Mandatory)][string]$Layer,
        [string]$Path,
        [string]$Resource,
        [string]$What
    )
    if ($Read.Ok -or $Read.NotFound) { return $null }
    $label = $(if ($What) { $What } else { Get-ArmName $Read.Path })
    $resource = $(if ($Resource) { $Resource } else { $Read.Path })
    if (!$Read.Read) {
        return New-DiagResult -Id $Id -Area $Area -Title $Title -Status CouldNotCheck -Gap KnownLimit -Path $Path -Layer $Layer `
            -Resource $resource -Seen "This evidence file has no data for $label." `
            -Needs 'Run the current version of the diagnostic to collect it.'
    }
    $needs = switch ($Read.ErrorKind) {
        'Forbidden' { "Read access (Reader) on $(Get-ArmScopeName $Read.Path)." }
        'Unauthorized' { 'A valid sign-in for the subscription that holds this resource.' }
        'Throttled' { 'Run again in a few minutes (Azure throttled the request).' }
        'Timeout' { 'Run again; the request timed out.' }
        default { "Run again; the request failed ($($Read.ErrorKind))." }
    }
    New-DiagResult -Id $Id -Area $Area -Title $Title -Status CouldNotCheck -Gap Blocking -Path $Path -Layer $Layer `
        -Resource $resource -Seen "Couldn't read $label ($($Read.Status) $($Read.ErrorKind))." -Needs $needs -Evidence @(Get-EvRef $Read)
}

function Get-DiagPathsUsed {
    param($Evidence)
    $paths = $Evidence.discovery.paths
    @($script:DiagPaths | Where-Object { $paths -and $paths[$_] -and $paths[$_].used })
}

function Test-DiagPathUsed {
    param($Evidence, [string]$Path)
    [bool]($Evidence.discovery.paths -and $Evidence.discovery.paths[$Path] -and $Evidence.discovery.paths[$Path].used)
}

# Runs every Test-Diag<Area> check that is loaded. A check that throws becomes a Blocking gap; other checks keep running.
function Invoke-DiagAnalysis {
    param([Parameter(Mandatory)]$Evidence)
    if ($Evidence.schema -ne $script:DiagSchema) { throw "Unsupported evidence schema '$($Evidence.schema)'." }
    $results = [Collections.Generic.List[object]]::new()
    foreach ($area in $script:DiagAreas) {
        $command = Get-Command "Test-Diag$area" -ErrorAction SilentlyContinue
        if (!$command) { continue }
        try {
            # Checks may return a wrapped array; flatten one level.
            foreach ($item in @(& $command -Evidence $Evidence)) {
                foreach ($result in @($item)) { if ($result) { $results.Add($result) } }
            }
        }
        catch {
            $results.Add((New-DiagResult -Id "$($area.ToLowerInvariant()).error" -Area $area -Title "$area checks failed to run" `
                -Status CouldNotCheck -Gap Blocking -Layer Config -Seen "The diagnostic hit an internal error: $($_.Exception.Message)" `
                -Needs 'Send evidence.json to support; this is a diagnostic bug.' -Details @{ error = $_.Exception.Message }))
        }
    }
    $seen = @{}
    foreach ($result in $results) {
        if ($seen.ContainsKey($result.key)) { throw "Duplicate result key '$($result.key)'." }
        $seen[$result.key] = $true
    }
    Set-DiagOffPath $results
    , $results.ToArray()
}

# When this machine isn't confirmed on the agent network, its own network findings say nothing about the agent path:
# they are marked offPath and shown apart from the problems instead of counting as them.
function Set-DiagOffPath {
    param($Results)
    $runner = @($Results | Where-Object { $_.id -eq 'runner.match' })[0]
    if (!$runner -or $runner.details.runnerMatch -eq 'Match') { return }
    foreach ($r in $Results) {
        if ($r.scope -eq 'ThisMachine' -and $r.status -ne 'OK' -and $r.id -ne 'runner.match') { $r.offPath = $true }
    }
}

# Callers load checks at script scope (dot-sourcing inside a function would drop them):
#   foreach ($file in Get-ChildItem (Join-Path $PSScriptRoot 'checks') -Filter *.ps1) { . $file.FullName }
