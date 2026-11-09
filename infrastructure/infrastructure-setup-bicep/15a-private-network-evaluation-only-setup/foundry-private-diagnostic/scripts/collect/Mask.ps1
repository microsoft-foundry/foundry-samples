# Optional masking for evidence shared outside the organization. Customer-chosen names (resource groups, resources,
# child resources and their host labels) become stable tokens, applied consistently so the file still replays.
# Subscription IDs, IP addresses, GUIDs, Microsoft hosts, private DNS zone names and model deployment names are kept.

$script:DiagMaskKeepUnder = @('deployments', 'roleassignments', 'privatednszones', 'providers', 'metrics')
# Fields holding fixed vocabulary (dependency kinds, paths, outcomes); never masked even if a resource shares the word.
$script:DiagMaskEnumKeys = @('kind', 'path', 'purpose', 'category', 'authType', 'scenario', 'outcome', 'status', 'errorKind', 'source', 'method', 'tokenSource', 'ownerType', 'error')
$script:DiagMaskGeneric = @('default', 'blob', 'file', 'queue', 'table', 'dfs', 'web', 'current', 'account', 'sites', 'amw', 'gateway', 'privatelink')
$script:DiagMaskHostSuffix = '\.(?:privatelink\.)?(?:cognitiveservices\.azure\.com|openai\.azure\.com|services\.ai\.azure\.com|(?:blob|file|queue|table|dfs|web)\.core\.windows\.net|vault\.azure\.net|search\.windows\.net|documents\.azure\.com)$'

function Test-DiagMaskEnum {
    param([string]$Key, $Value)
    $Key -in $script:DiagMaskEnumKeys -and $Value -is [string] -and $Value -notmatch '[/.]'
}

function Get-DiagStrings {
    param($Node, [Collections.Generic.List[string]]$Out)
    if ($null -eq $Node) { return }
    if ($Node -is [string]) { $Out.Add($Node); return }
    if ($Node -is [Collections.IDictionary]) {
        foreach ($k in @($Node.Keys)) { if ("$k".Contains('/')) { $Out.Add("$k") }; Get-DiagStrings $Node[$k] $Out }
        return
    }
    if ($Node -is [pscustomobject]) {
        foreach ($p in $Node.PSObject.Properties) { Get-DiagStrings $p.Value $Out }
        return
    }
    if ($Node -is [Collections.IEnumerable]) { foreach ($i in $Node) { Get-DiagStrings $i $Out } }
}

function Add-DiagMaskName {
    param([hashtable]$Names, [string]$Name, [string]$Kind)
    $n = $Name.ToLowerInvariant()
    if ($n.Length -lt 3 -or $n -in $script:DiagMaskGeneric -or $n -match '^privatelink\.' -or
        $n -match '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' -or $n -match '^\d+(\.\d+){3}$') { return }
    if (!$Names.ContainsKey($n)) { $Names[$n] = $Kind }
}

function Get-DiagMaskNames {
    param([string[]]$Strings)
    $names = @{}
    foreach ($s in $Strings) {
        foreach ($m in [regex]::Matches($s, '(?i)/subscriptions/[^/\s"?#]+/resourceGroups/[^\s"?#]+')) {
            $segments = @($m.Value -split '/' | Where-Object { $_ })
            Add-DiagMaskName $names $segments[3] 'rg'
            $i = 4
            while ($i -lt $segments.Count) {
                if ($segments[$i] -ieq 'providers') { $i += 2; continue }
                $type = $segments[$i].ToLowerInvariant()
                # Record names in private zones are Microsoft-defined (api, global.in.ai) or repeat a resource name masked elsewhere.
                $isRecord = $type -in 'a', 'aaaa', 'cname' -and $i -ge 2 -and $segments[$i - 2] -ieq 'privateDnsZones'
                if ($i + 1 -lt $segments.Count -and $type -notin $script:DiagMaskKeepUnder -and !$isRecord) {
                    Add-DiagMaskName $names $segments[$i + 1] ($type -replace 'ies$', 'y' -replace 's$', '')
                }
                $i += 2
            }
        }
        foreach ($m in [regex]::Matches($s, '(?i)\b([a-z0-9][a-z0-9-]{1,62})(?:\.[a-z0-9-]+)*?' + $script:DiagMaskHostSuffix.TrimEnd('$') + '\b')) {
            Add-DiagMaskName $names $m.Groups[1].Value 'host'
        }
    }
    $names
}

function New-DiagMaskMap {
    param([hashtable]$Names)
    $map = [ordered]@{}
    $counters = @{}
    foreach ($n in @($Names.Keys | Sort-Object)) {
        $kind = $Names[$n] -replace '[^a-z0-9]', ''
        if (!$kind) { $kind = 'name' }
        $counters[$kind] = 1 + [int]$counters[$kind]
        $map[$n] = "masked-$kind$($counters[$kind])"
    }
    $map
}

function ConvertTo-DiagMaskedString {
    param([string]$Text, [regex]$Pattern, $Map)
    if (!$Text) { return $Text }
    $Pattern.Replace($Text, { param($m) $m.Groups[1].Value + $Map[$m.Groups[2].Value.ToLowerInvariant()] })
}

function ConvertTo-DiagMaskedNode {
    param($Node, [regex]$Pattern, $Map)
    if ($null -eq $Node) { return $null }
    if ($Node -is [string]) { return ConvertTo-DiagMaskedString $Node $Pattern $Map }
    if ($Node -is [Collections.IDictionary]) {
        $copy = [ordered]@{}
        foreach ($k in @($Node.Keys)) {
            $key = $(if ("$k".Contains('/')) { ConvertTo-DiagMaskedString "$k" $Pattern $Map } else { $k })
            $copy[$key] = $(if ((Test-DiagMaskEnum "$k" $Node[$k])) { $Node[$k] } else { ConvertTo-DiagMaskedNode $Node[$k] $Pattern $Map })
        }
        return $copy
    }
    if ($Node -is [pscustomobject]) {
        $copy = [ordered]@{}
        foreach ($p in $Node.PSObject.Properties) { $copy[$p.Name] = $(if ((Test-DiagMaskEnum $p.Name $p.Value)) { $p.Value } else { ConvertTo-DiagMaskedNode $p.Value $Pattern $Map }) }
        return $copy
    }
    if ($Node -is [Collections.IEnumerable]) { return , @(foreach ($i in $Node) { , (ConvertTo-DiagMaskedNode $i $Pattern $Map) }) }
    $Node
}

function ConvertTo-DiagMaskedEvidence {
    param([Parameter(Mandatory)]$Evidence)
    $strings = [Collections.Generic.List[string]]::new()
    Get-DiagStrings $Evidence $strings
    $map = New-DiagMaskMap (Get-DiagMaskNames $strings)
    $masked = $Evidence
    if ($map.Count) {
        $alternatives = @($map.Keys | Sort-Object Length -Descending | ForEach-Object { [regex]::Escape($_) }) -join '|'
        $pattern = [regex]::new("(^|[^A-Za-z0-9-])($alternatives)(?=$|[^A-Za-z0-9-])", 'IgnoreCase')
        $masked = ConvertTo-DiagMaskedNode $Evidence $pattern $map
    }
    if ($masked.run) { $masked.run.masked = $true }
    $masked
}
