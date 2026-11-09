#Requires -Version 7.2
function New-CleanProcess([string]$Executable,[string[]]$Arguments) {
    $start = [Diagnostics.ProcessStartInfo]::new($Executable)
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true; $start.RedirectStandardError = $true
    foreach ($key in @($start.Environment.Keys)) {
        if ($key -like 'PYTHON*' -or $key -like 'PIP_*') { $null = $start.Environment.Remove($key) }
    }
    $start.Environment['AZURE_EXTENSION_USE_DYNAMIC_INSTALL'] = 'no'
    $start.Environment['AZURE_CORE_COLLECT_TELEMETRY'] = 'no'
    $start.Environment['AZURE_CORE_CHECK_VERSION'] = 'no'
    $start.Environment['AZ_INSTALLER'] = 'MSI'
    foreach ($arg in $Arguments) { $start.ArgumentList.Add($arg) }
    return $start
}
function Invoke-NativeProcess($Start,[int]$TimeoutSeconds = 120,[scriptblock]$OnStart) {
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $Start
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $started = $false
    try {
        $null = $process.Start()
        $started = $true
        if ($OnStart) { & $OnStart }
        $stdout = $process.StandardOutput.ReadToEndAsync(); $stderr = $process.StandardError.ReadToEndAsync()
        if (!$process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill($true)
            return @{ code = 408; stdout = ''; stderr = ''; elapsedMs = $timer.Elapsed.TotalMilliseconds }
        }
        @{ code = $process.ExitCode; stdout = $stdout.GetAwaiter().GetResult(); stderr = $stderr.GetAwaiter().GetResult()
            elapsedMs = $timer.Elapsed.TotalMilliseconds }
    } finally { if ($started -and !$process.HasExited) { $process.Kill($true) }; $process.Dispose() }
}
function Get-SetupToolchain {
    if (Get-Variable -Name SetupTools -Scope Script -ErrorAction SilentlyContinue) { return $script:SetupTools }
    $manifest = Get-Content (Join-Path $PSScriptRoot '..\assets\toolchain.json') -Raw | ConvertFrom-Json -AsHashtable
    if ($PSVersionTable.PSVersion -lt [version]$manifest.minimumPowerShell) { throw 'PowerShell 7.2+ is required; preinstall it offline. No profile/global package changes are performed.' }
    $az = $env:FOUNDRY_SETUP_AZURE_CLI
    if (!$az) {
        $commands = @(Get-Command az -CommandType Application -All -ErrorAction SilentlyContinue)
        if (!$commands.Count) { throw 'Azure CLI missing. Preinstall a compatible CLI offline or set FOUNDRY_SETUP_AZURE_CLI to its supported launcher.' }
        $az = $commands[0].Source
    }
    if (!(Test-Path -LiteralPath $az -PathType Leaf)) { throw 'Explicit Azure CLI launcher does not exist.' }
    $python = ''; $executable = $az; $prefix = @(); $versions = @{ python = 'CLI-managed'; azureCli = 'Unknown' }
    if ([IO.Path]::GetExtension($az) -ieq '.cmd') {
        $python = Join-Path (Split-Path (Split-Path $az)) 'python.exe'
        if (!(Test-Path -LiteralPath $python)) { throw 'CLI-owned Python missing beside az.cmd. Repair the preinstalled CLI or select a supported native launcher; no global Python fallback.' }
        $probe = Invoke-NativeProcess (New-CleanProcess $python @('-I','-B','-c','import sys,json,azure.cli.core;print(json.dumps({"python":sys.version.split()[0],"azureCli":azure.cli.core.__version__}))'))
        if ($probe.code -ne 0) { throw 'CLI-owned Python cannot load CLI in isolation. Repair the local CLI installation offline; do not install global packages.' }
        $versions = $probe.stdout | ConvertFrom-Json -AsHashtable
        $executable = $python; $prefix = @('-I','-B','-m','azure.cli')
    }
    $requirements = @(
        @{ command = @('deployment','group','create','--help'); flags = @('--no-wait','--template-file','--parameters','--resource-group') },
        @{ command = @('deployment','group','what-if','--help'); flags = @('--no-pretty-print','--result-format') },
        @{ command = @('rest','--help'); flags = @('--method','--body','--headers') })
    foreach ($requirement in $requirements) {
        $help = Invoke-NativeProcess (New-CleanProcess $executable ($prefix + $requirement.command))
        if ($help.code -ne 0) { throw 'Required local Azure CLI command cannot load. Repair/preinstall compatible CLI offline; no download attempted.' }
        foreach ($flag in $requirement.flags) { if (!$help.stdout.Contains($flag)) { throw "Required CLI capability missing: $flag. Preinstall a compatible CLI offline." } }
    }
    if ($versions.azureCli -eq 'Unknown') {
        $version = Invoke-NativeProcess (New-CleanProcess $executable ($prefix + @('version','--output','json')))
        if ($version.code -eq 0) { $versions.azureCli = ($version.stdout | ConvertFrom-Json -AsHashtable)['azure-cli'] }
    }
    $bicep = $env:FOUNDRY_SETUP_BICEP
    if (!$bicep) { $candidate = Get-Command bicep -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1; if ($candidate) { $bicep = $candidate.Source } }
    if (!$bicep) { $bicep = Join-Path $HOME $(if ($IsWindows) { '.azure\bin\bicep.exe' } else { '.azure/bin/bicep' }) }
    if (!(Test-Path -LiteralPath $bicep -PathType Leaf)) { throw 'Local Bicep missing. Preinstall offline, expose bicep on PATH or set FOUNDRY_SETUP_BICEP. No download attempted.' }
    $compiler = Invoke-NativeProcess (New-CleanProcess $bicep @('--version'))
    if ($compiler.code -ne 0 -or $compiler.stdout -notmatch 'Bicep CLI version (\d+\.\d+\.\d+)') { throw 'Local Bicep cannot report its version; no installation attempted.' }
    $script:SetupTools = @{ python = $python; executable = $executable; prefix = $prefix; bicep = $bicep
        bicepVersion = $Matches[1]; versions = $versions; manifest = $manifest }
    return $script:SetupTools
}
function Invoke-LocalBicep([string]$File) {
    $tools = Get-SetupToolchain
    $result = Invoke-NativeProcess (New-CleanProcess $tools.bicep @('build',$File,'--stdout')) $tools.manifest.budgets.nativeSeconds
    if ($result.stderr) { Write-Warning $result.stderr.Trim() }
    if ($result.code -ne 0) { throw 'Local Bicep compilation failed; diagnostics are visible. No Azure request was made.' }
    return ConvertFrom-SetupJson $result.stdout
}
