function New-ProviderPrerequisiteError {
    param([string]$Code)
    # Only identifiers from this local table are ever shown; no module/HTTP errors.
    $messages = @{
        AzAccountsMissing = 'AzurePowerShell requires installed Az.Accounts 5.3.3 or later. Install prerequisites separately; this diagnostic does not install modules.'
        AzAccountsImportFailed = 'Az.Accounts could not be loaded. Verify the installed module in this PowerShell session.'
        AzAccountsContractUnsupported = 'Az.Accounts does not expose the required context/token command parameters.'
        AzContextMissing = 'AzurePowerShell requires an existing authenticated context. Run Connect-AzAccount with the intended tenant/subscription separately before diagnosis.'
        AzContextWrongCloud = 'Only an AzureCloud context with the public ARM endpoint is supported.'
        AzContextSubscriptionMismatch = 'The captured AzurePowerShell context subscription must match the selected project subscription. Establish the intended context separately.'
    }
    $error = [InvalidOperationException]::new($Code)
    $error.Data['DiagnosticPrerequisite'] = $messages[$Code]
    throw $error
}

function Get-AzurePowerShellProfile {
    if (!(Get-Module -ListAvailable Az.Accounts | Where-Object { $_.Version -ge [version]'5.3.3' })) {
        New-ProviderPrerequisiteError 'AzAccountsMissing'
    }
    try { Import-Module Az.Accounts -MinimumVersion 5.3.3 -ErrorAction Stop -WarningAction SilentlyContinue }
    catch { New-ProviderPrerequisiteError 'AzAccountsImportFailed' }
    $contextCommand = Get-Command 'Az.Accounts\Get-AzContext' -ErrorAction Stop
    $tokenCommand = Get-Command 'Az.Accounts\Get-AzAccessToken' -ErrorAction Stop
    foreach ($name in @('DefaultProfile','TenantId','ResourceUrl','AsSecureString')) {
        if (!$tokenCommand.Parameters.ContainsKey($name)) { New-ProviderPrerequisiteError 'AzAccountsContractUnsupported' }
    }
    if (!$contextCommand.Parameters.ContainsKey('DefaultProfile')) { New-ProviderPrerequisiteError 'AzAccountsContractUnsupported' }
    try { $profile = & $contextCommand -ErrorAction Stop -WarningAction SilentlyContinue }
    catch { New-ProviderPrerequisiteError 'AzContextMissing' }
    return @{ Profile = $profile; ModuleVersion = [string]$tokenCommand.Version }
}

function Initialize-AzurePowerShellProvider {
    param($Context, [string]$SubscriptionId)
    $capture = Get-AzurePowerShellProfile
    $profile = $capture.Profile
    if (!$profile -or !$profile.Account.Id -or !$profile.Tenant.Id -or !$profile.Subscription.Id) {
        New-ProviderPrerequisiteError 'AzContextMissing'
    }
    if ($profile.Environment.Name -ne 'AzureCloud' -or
        ([string]$profile.Environment.ResourceManagerUrl).TrimEnd('/') -ne 'https://management.azure.com') {
        New-ProviderPrerequisiteError 'AzContextWrongCloud'
    }
    if ($SubscriptionId -and $profile.Subscription.Id -ine $SubscriptionId) {
        New-ProviderPrerequisiteError 'AzContextSubscriptionMismatch'
    }
    # Capture a context copy once. No Set-AzContext, login, CLI or backend fallback.
    $Context.AzProfile = New-CapturedAzProfile $profile
    $Context.TenantId = [string]$profile.Tenant.Id
    $Context.AzModuleVersion = $capture.ModuleVersion
    $Context.HttpClient = New-ArmHttpClient
}

function New-CapturedAzProfile {
    param($Profile)
    $captured = [Microsoft.Azure.Commands.Profile.Models.Core.PSAzureContext]::new($Profile)
    $container = [Microsoft.Azure.Commands.Common.Authentication.Models.AzureRmProfile]::new()
    $container.DefaultContext = $captured
    return $container
}

function New-ArmHttpHandler {
    $handler = [Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $false
    $handler.UseCookies = $false
    $handler.UseDefaultCredentials = $false
    return $handler
}

function New-ArmHttpClient {
    $client = [Net.Http.HttpClient]::new((New-ArmHttpHandler), $true)
    $client.Timeout = [Threading.Timeout]::InfiniteTimeSpan
    $client.MaxResponseContentBufferSize = 16MB
    return $client
}

function New-ArmTokenWorker {
    param($Context)
    # In-process runspace: context and SecureString result never cross a process,
    # command line, environment variable or file boundary. Disallow prompting.
    $worker = [PowerShell]::Create()
    $null = $worker.AddScript({
        param($profile, $tenant)
        $ErrorActionPreference = 'Stop'
        $ProgressPreference = 'SilentlyContinue'
        $WarningPreference = 'SilentlyContinue'
        $VerbosePreference = 'SilentlyContinue'
        $DebugPreference = 'SilentlyContinue'
        Import-Module Az.Accounts -MinimumVersion 5.3.3 -ErrorAction Stop
        Az.Accounts\Get-AzAccessToken -ResourceUrl 'https://management.azure.com/' -TenantId $tenant `
            -DefaultProfile $profile -AsSecureString -ErrorAction Stop -WarningAction SilentlyContinue
    }).AddArgument($Context.AzProfile).AddArgument($Context.TenantId)
    return $worker
}

function Get-CapturedArmToken {
    param($Context)
    if ($Context.TokenAcquisitionTimedOut) { return @{ Code = 408; Token = $null } }
    if ($Context.ArmToken -and $Context.ArmTokenExpiresOn -gt [DateTimeOffset]::UtcNow.AddMinutes(5)) {
        return @{ Code = 200; Token = $Context.ArmToken.Copy() }
    }
    if ($Context.ArmToken) { $Context.ArmToken.Dispose(); $Context.ArmToken = $null }
    $worker = New-ArmTokenWorker $Context
    $pending = $worker.BeginInvoke()
    if (!$pending.AsyncWaitHandle.WaitOne([TimeSpan]::FromSeconds($Context.TimeoutSeconds))) {
        # BeginStop is nonblocking. Keep the handle for cleanup; never let a token
        # acquired after the deadline become an HTTP credential for this attempt.
        $null = $worker.BeginStop($null, $null)
        $Context.TimedOutTokenWorkers.Add($worker)
        $Context.TokenAcquisitionTimedOut = $true
        return @{ Code = 408; Token = $null }
    }
    try {
        $result = @($worker.EndInvoke($pending))
        if ($worker.HadErrors -or $result.Count -ne 1 -or $result[0].Token -isnot [Security.SecureString] -or
            !$result[0].Token.Length -or $result[0].TenantId -ine $Context.TenantId -or
            $result[0].ExpiresOn -le [DateTimeOffset]::UtcNow) {
            return @{ Code = 401; Token = $null }
        }
        $Context.ArmToken = $result[0].Token.Copy()
        $Context.ArmTokenExpiresOn = $result[0].ExpiresOn
        return @{ Code = 200; Token = $Context.ArmToken.Copy() }
    }
    catch { return @{ Code = 401; Token = $null } }
    finally {
        foreach ($item in $result) { if ($item.Token -is [Security.SecureString]) { $item.Token.Dispose() } }
        $worker.Dispose()
    }
}

function Invoke-AzurePowerShellMetadata {
    param($Context, [string]$Uri, [bool]$Collection, [string]$Method = 'GET')
    $rule = Assert-ArmRequest $Uri -Method $Method
    if ($Context.Offline -or $Context.AuthenticationProvider -ne 'AzurePowerShell') { throw 'ProviderMismatch' }
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $token = Get-CapturedArmToken $Context
    if ($token.Code -ne 200) { return @{ Code = $token.Code; Data = $null } }
    $request = $null; $response = $null; $cancellation = $null
    $pointer = [IntPtr]::Zero
    try {
        $remaining = [TimeSpan]::FromSeconds($Context.TimeoutSeconds) - $clock.Elapsed
        if ($remaining -le [TimeSpan]::Zero) { return @{ Code = 408; Data = $null } }
        $request = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::Get, $Uri)
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($token.Token)
        $request.Headers.Authorization = [Net.Http.Headers.AuthenticationHeaderValue]::new(
            'Bearer', [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer))
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $pointer = [IntPtr]::Zero
        $cancellation = [Threading.CancellationTokenSource]::new($remaining)
        $response = $Context.HttpClient.SendAsync($request, [Net.Http.HttpCompletionOption]::ResponseContentRead, $cancellation.Token).
            WaitAsync($remaining).GetAwaiter().GetResult()
        $code = [int]$response.StatusCode
        # Redirects and all non-200 bodies are discarded without logging or parsing.
        if ($code -ne 200) { return @{ Code = $code; Data = $null } }
        $body = $response.Content.ReadAsStringAsync($cancellation.Token).GetAwaiter().GetResult()
        $raw = $body | ConvertFrom-Json -AsHashtable -Depth 80 -ErrorAction Stop
        return @{ Code = 200; Data = (ConvertTo-ArmMetadata $raw $rule.Kind $Collection) }
    }
    catch [OperationCanceledException] { return @{ Code = 408; Data = $null } }
    catch [TimeoutException] { return @{ Code = 408; Data = $null } }
    catch { return @{ Code = 0; Data = $null } }
    finally {
        if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
        $token.Token.Dispose()
        if ($request) { $request.Headers.Authorization = $null; $request.Dispose() }
        if ($response) { $response.Dispose() }
        if ($cancellation) { $cancellation.Dispose() }
        $body = $null; $raw = $null
    }
}

function Close-DiagnosticContext {
    param($Context)
    if (!$Context) { return }
    if ($Context.ArmToken) { $Context.ArmToken.Dispose(); $Context.ArmToken = $null }
    if ($Context.HttpClient) { $Context.HttpClient.Dispose() }
    foreach ($worker in $Context.TimedOutTokenWorkers) {
        # A stopped worker is disposed without waiting on an unresponsive auth provider.
        if ($worker.InvocationStateInfo.State -notin @('Running','Stopping')) { $worker.Dispose() }
    }
    $Context.AzProfile = $null
}
