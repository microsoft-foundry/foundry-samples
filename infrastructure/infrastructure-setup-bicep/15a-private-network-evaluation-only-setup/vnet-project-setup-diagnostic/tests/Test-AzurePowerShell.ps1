# Invoked inside the offline suite. All auth and HTTP results below are synthetic.
Add-Type -Path (Join-Path $PSScriptRoot 'OfflineArmHandler.cs') -ErrorAction Stop
$providerFixture = New-TopologyFixture $topologies[0]
$providerId = $providerFixture.test.account
$providerUri = "https://management.azure.com${providerId}?api-version=2025-06-01"
$tenant = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'

function New-OfflineProviderContext {
    $context = New-TestContext $providerFixture 'az-provider'
    $context.Offline = $false
    $context.AuthenticationProvider = 'AzurePowerShell'
    $context.TenantId = $tenant
    $context.TimeoutSeconds = 1
    $context.AzProfile = @{ synthetic = $true }
    $context.TestHandler = [OfflineArmHandler]::new()
    $context.HttpClient = [Net.Http.HttpClient]::new($context.TestHandler)
    return $context
}

& {
    function Get-Module { param($ListAvailable) return @() }
    $caught = $null
    try { Get-AzurePowerShellProfile } catch { $caught = $_.Exception }
    Assert-True ($caught.Data['DiagnosticPrerequisite'] -like '*installed Az.Accounts*') 'Missing module produces safe actionable prerequisite, no fallback'
}
& {
    function Get-Module { param($ListAvailable) return @{ Version = [version]'5.3.3' } }
    function Import-Module { param($Name,$MinimumVersion,$ErrorAction,$WarningAction) throw 'fixture-sensitive-sentinel' }
    $caught = $null
    try { Get-AzurePowerShellProfile } catch { $caught = $_.Exception }
    Assert-True ($caught.Message -eq 'AzAccountsImportFailed' -and $caught.ToString() -notmatch 'sensitive-sentinel') 'Import failure never echoes raw module errors'
}
& {
    $script:capturedTestProfile = @{ Account=@{Id='synthetic-account'}; Tenant=@{Id=$tenant}
        Subscription=@{Id=$providerFixture.test.sub.Split('/')[2]}; Environment=@{Name='AzureCloud';ResourceManagerUrl='https://management.azure.com/'} }
    function Get-AzurePowerShellProfile { return @{Profile=$script:capturedTestProfile;ModuleVersion='5.3.3'} }
    function New-CapturedAzProfile { param($Profile) return ($Profile | ConvertTo-Json -Depth 10 | ConvertFrom-Json -AsHashtable) }
    function Invoke-CliMetadata { throw 'CLI MUST NOT RUN' }
    function Get-Command { throw 'CLI MUST NOT BE DISCOVERED' }
    $context = New-DiagnosticContext '' 'MUST-NOT-EXIST-AZ' @() 5 -AuthenticationProvider AzurePowerShell -SubscriptionId $script:capturedTestProfile.Subscription.Id
    Assert-True ($context.AuthenticationProvider -eq 'AzurePowerShell' -and $context.TenantId -eq $tenant) 'CLI-free bootstrap needs no executable discovery or CLI token'
    $script:capturedTestProfile.Account.Id = 'later-changed-context'
    Assert-True ($context.AzProfile.Account.Id -eq 'synthetic-account') 'Selected profile is captured, not selected again later'
    Close-DiagnosticContext $context
    $script:capturedTestProfile.Environment.Name = 'AzureUSGovernment'
    $caught=$null
    try { New-DiagnosticContext '' '' @() -AuthenticationProvider AzurePowerShell } catch { $caught=$_.Exception }
    Assert-True ($caught.Message -eq 'AzContextWrongCloud') 'Wrong cloud is rejected before token or HTTP'
    $script:capturedTestProfile.Environment.Name = 'AzureCloud'
    $caught=$null
    try { New-DiagnosticContext '' '' @() -AuthenticationProvider AzurePowerShell -SubscriptionId 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' } catch { $caught=$_.Exception }
    Assert-True ($caught.Message -eq 'AzContextSubscriptionMismatch') 'Context subscription mismatch never switches subscription'
    $script:capturedTestProfile = $null
    $caught=$null
    try { New-DiagnosticContext '' '' @() -AuthenticationProvider AzurePowerShell } catch { $caught=$_.Exception }
    Assert-True ($caught.Message -eq 'AzContextMissing') 'Missing login context has safe prerequisite guidance'
}

& {
    function Initialize-AzurePowerShellProvider { throw 'AZ AUTH MUST NOT RUN' }
    function Invoke-CliMetadata { throw 'CLI MUST NOT RUN' }
    function Get-Command { throw 'COMMAND DISCOVERY MUST NOT RUN' }
    foreach ($provider in @('AzurePowerShell','AzureCli')) {
        $file = Join-Path $OutputDirectory 'az-fixture-only.fixture.json'
        $providerFixture | ConvertTo-Json -Depth 70 | Set-Content $file
        $context = New-DiagnosticContext $file 'MISSING-AZ' @() -AuthenticationProvider $provider
        Assert-True ((Read-Arm $context $providerId).Code -eq 200) 'Fixtures require neither provider nor network'
    }
}
$handler = New-ArmHttpHandler
Assert-True (!$handler.AllowAutoRedirect -and !$handler.UseCookies -and !$handler.UseDefaultCredentials) 'Production HTTP handler disallows redirect/cookie/default credential forwarding'
$handler.Dispose()

& {
    function Invoke-CliMetadata { throw 'CLI MUST NOT RUN' }
    function New-ArmTokenWorker {
        param($Context)
        $worker = [PowerShell]::Create()
        $null = $worker.AddScript({
            param($tenant)
            @{ Token = (ConvertTo-SecureString 'offline-bearer-canary' -AsPlainText -Force)
                TenantId = $tenant; ExpiresOn = [DateTimeOffset]::UtcNow.AddHours(1) }
        }).AddArgument($Context.TenantId)
        return $worker
    }
    $context = New-OfflineProviderContext
    $context.TestHandler.Body = '{"id":"/fixture","properties":{"provisioningState":"Succeeded","credentials":{"key":"fixture-sensitive-sentinel"},"instrumentationKey":"fixture-sensitive-sentinel"}}'
    $result = Invoke-AzurePowerShellMetadata $context $providerUri $false
    Assert-True ($result.Code -eq 200 -and $context.TestHandler.AuthorizationPresent) 'Actual HTTP transport uses in-memory SecureString token against synthetic handler'
    Assert-True (($result | ConvertTo-Json -Depth 20) -notmatch 'canary|sensitive-sentinel|credentials|instrumentationKey') 'Transport result exposes only projected metadata'
    $firstToken = $context.ArmToken
    $cachedToken = Get-CapturedArmToken $context
    Assert-True ($cachedToken.Code -eq 200 -and ![object]::ReferenceEquals($firstToken, $cachedToken.Token)) 'Cached auth is SecureString-only and returns a disposable copy'
    $cachedToken.Token.Dispose()
    foreach ($status in @(401,403,404,429,503,504,301,302,307,308)) {
        $context.TestHandler.Codes.Enqueue($status)
        $context.TestHandler.Location = 'https://untrusted.example/credential-sink'
        $before = $context.TestHandler.Requests.Count
        $result = Invoke-AzurePowerShellMetadata $context $providerUri $false
        Assert-True ($result.Code -eq $status -and $null -eq $result.Data) "HTTP$status preserved without raw body"
        Assert-True ($context.TestHandler.Requests.Count -eq $before+1) 'Redirect response triggers no follow-up request'
    }
    $before = $context.TestHandler.Requests.Count
    foreach ($method in @('POST','PUT','DELETE','get')) {
        Assert-Throws { Invoke-AzurePowerShellMetadata $context $providerUri $false -Method $method } 'Provider rejects unapproved method before auth/HTTP'
    }
    Assert-Throws { Invoke-AzurePowerShellMetadata $context ($providerUri.Replace('management.azure.com','untrusted.example')) $false } 'Provider rejects unapproved host'
    Assert-True ($context.TestHandler.Requests.Count -eq $before) 'Rejected requests never reach HTTP'
    foreach ($body in @('not-json fixture-sensitive-sentinel','null','[]')) {
        $context.TestHandler.Body = $body
        $result = Invoke-AzurePowerShellMetadata $context $providerUri $false
        Assert-True ($result.Code -eq 0 -and $null -eq $result.Data) 'Malformed raw response is rejected without payload echo'
    }
    $context.TestHandler.DelayMilliseconds = 2000
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $result = Invoke-AzurePowerShellMetadata $context $providerUri $false
    Assert-True ($result.Code -eq 408 -and $clock.Elapsed.TotalSeconds -lt 1.8) 'Actual HTTP cancellation enforces bounded deadline'
    Close-DiagnosticContext $context

    # Run every shared check through the real new transport with raw fixture responses.
    $fixtureContext = New-TestContext $providerFixture 'az-downstream-reference'
    $options = New-TestOptions $providerFixture @('Core','Models','Traces')
    Invoke-ConfigurationAssessment $fixtureContext $options $catalog
    $context = New-OfflineProviderContext
    $context.TimeoutSeconds = 5
    foreach ($path in $providerFixture.responses.Keys) {
        $raw = $providerFixture.responses[$path].Data
        if ($raw) { $context.TestHandler.Bodies[$path] = $raw | ConvertTo-Json -Depth 70 -Compress }
    }
    Invoke-ConfigurationAssessment $context $options $catalog
    $expected = @($fixtureContext.Checks | ForEach-Object { "$($_.id)|$($_.resource)|$($_.status)|$($_.classification)|$($_.required)" })
    $actual = @($context.Checks | ForEach-Object { "$($_.id)|$($_.resource)|$($_.status)|$($_.classification)|$($_.required)" })
    Assert-True (($expected -join "`n") -ceq ($actual -join "`n")) 'New provider yields identical downstream finding classifications to fixture metadata'
    Assert-True ((Get-Outcome $context.Checks).exitCode -eq (Get-Outcome $fixtureContext.Checks).exitCode) 'Provider does not fork exit semantics'
    Assert-True (($context.Checks | ConvertTo-Json -Depth 70) -notmatch 'offline-bearer-canary|fixture-sensitive') 'Shared findings contain no token/secret canary'
    Close-DiagnosticContext $context

    # Real retry loop, without sleeps or Azure.
    function Start-Sleep { param($Seconds) }
    foreach ($status in @(401,403,404,429,503,504)) {
        $context = New-OfflineProviderContext
        1..3 | ForEach-Object { $context.TestHandler.Codes.Enqueue($status) }
        $result = Read-Arm $context $providerId
        $expectedAttempts = if ($status -in @(429,503,504)) {3} else {1}
        Assert-True ($context.TestHandler.Requests.Count -eq $expectedAttempts -and $result.Code -eq $status) "Bounded retry policy for$status"
        Close-DiagnosticContext $context
    }
    $context = New-OfflineProviderContext
    $collection = "$providerId/connections"
    $context.TestHandler.Body = '{"value":[],"nextLink":"https://untrusted.example/page"}'
    $result = Read-Arm $context $collection -Collection
    Assert-True ($result.Reason -eq 'RejectedPaging' -and $context.TestHandler.Requests.Count -eq 1) 'Provider pagination revalidates host before forwarding credentials'
    Close-DiagnosticContext $context
    $context = New-OfflineProviderContext
    $context.TestHandler.Body = '{"value":null}'
    Assert-True ((Read-Arm $context $collection -Collection).Code -eq 0) 'Provider rejects null collection rather than reporting empty success'
    Close-DiagnosticContext $context
    $context = New-OfflineProviderContext
    $context.TestHandler.Codes.Enqueue(503)
    $context.TestHandler.Body = '{"id":"/synthetic","properties":{"provisioningState":"Succeeded"}}'
    $result = Read-Arm $context $providerId
    Assert-True ($result.Code -eq 200 -and $context.TestHandler.Requests.Count -eq 2) 'Eligible transient failure retries once and returns projected success'
    Close-DiagnosticContext $context
}

& {
    function New-ArmTokenWorker {
        param($Context)
        $worker = [PowerShell]::Create()
        $null = $worker.AddScript({ Start-Sleep -Seconds 5; throw 'never-use-late-token' })
        return $worker
    }
    $context = New-OfflineProviderContext
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $result = Invoke-AzurePowerShellMetadata $context $providerUri $false
    Assert-True ($result.Code -eq 408 -and $clock.Elapsed.TotalSeconds -lt 2 -and $context.TestHandler.Requests.Count -eq 0) 'Token acquisition deadline prevents later token use'
    Assert-True ((Get-CapturedArmToken $context).Code -eq 408 -and $context.TimedOutTokenWorkers.Count -eq 1) 'Timed-out identity acquisition is not repeatedly spawned'
    Close-DiagnosticContext $context
}
& {
    function New-ArmTokenWorker {
        param($Context)
        $worker = [PowerShell]::Create()
        $null = $worker.AddScript({ throw 'fixture-sensitive-auth-error' })
        return $worker
    }
    $context = New-OfflineProviderContext
    $result = Invoke-AzurePowerShellMetadata $context $providerUri $false
    Assert-True ($result.Code -eq 401 -and $context.TestHandler.Requests.Count -eq 0 -and ($result | ConvertTo-Json) -notmatch 'sensitive') 'Authentication failure is explicit and sanitized; no identity/CLI fallback'
    Close-DiagnosticContext $context
}

# Module command-surface check only; never read a live context or acquire a token.
$installed = @(Get-Module -ListAvailable Az.Accounts | Where-Object { $_.Version -ge [version]'5.3.3' })
if ($installed.Count) {
    Import-Module Az.Accounts -MinimumVersion 5.3.3 -ErrorAction Stop
    $command = Get-Command Get-AzAccessToken -Module Az.Accounts
    foreach ($name in @('ResourceUrl','TenantId','AsSecureString','DefaultProfile')) {
        Assert-True ($command.Parameters.ContainsKey($name)) "Installed module supports$name"
    }
    $emptyProfile = New-CapturedAzProfile ([Microsoft.Azure.Commands.Profile.Models.Core.PSAzureContext]::new())
    Assert-True ($command.Parameters['DefaultProfile'].ParameterType.IsInstanceOfType($emptyProfile)) 'Captured in-memory container implements real DefaultProfile contract'
    Assert-True ([Microsoft.Azure.Commands.Profile.Models.PSSecureAccessToken].GetProperty('Token').PropertyType -eq [Security.SecureString]) 'Installed token output contract is SecureString'
    $login = Get-Command Connect-AzAccount -Module Az.Accounts
    foreach ($name in @('Tenant','Subscription','Environment','Scope','Identity')) {
        Assert-True ($login.Parameters.ContainsKey($name)) "Documented customer login parameter$name exists in installed module"
    }
}

# Export synthetic raw ARM cases for comparison with the actual JMESPath evaluator.
$parityCases = [Collections.Generic.List[object]]::new()
foreach ($path in $providerFixture.responses.Keys) {
    $raw = $providerFixture.responses[$path].Data
    if (!$raw) { continue }
    $rule = Get-ArmRule $path
    $collection = $raw.ContainsKey('value')
    $raw['credentials'] = @{key='projection-secret-canary'}
    $items = if ($collection) { @($raw.value) } else { @($raw) }
    foreach ($item in $items) {
        if (!$item.properties) { continue }
        $item.properties['credentials'] = @{key='projection-secret-canary'}
        $item.properties['connectionString'] = 'projection-secret-canary'
        $item.properties['instrumentationKey'] = 'projection-secret-canary'
        if ($item.properties.metadata) { $item.properties.metadata['ApplicationInsightsConnectionString'] = 'projection-secret-canary' }
        if ($item.identity) { $item.identity['credentials'] = 'projection-secret-canary' }
        foreach ($property in @('ipConfigurations','permissions','customDnsConfigs')) {
            foreach ($entry in @($item.properties[$property] | Where-Object { $_ })) { $entry['secret'] = 'projection-secret-canary' }
        }
    }
    $parityCases.Add(@{kind=$rule.Kind;collection=$collection;query=(Get-MetadataProjection $rule.Kind $collection)
        data=$raw;native=(ConvertTo-ArmMetadata $raw $rule.Kind $collection)})
}
foreach ($kind in @('Resource','Connection','Authorization','Role','Deployment','Capability','PrivateConnection','Storage','Monitoring','Network','Dependency')) {
    foreach ($collection in @($false,$true)) {
        $item = @{
            id='/synthetic'; properties=@{
                condition='secret-condition-text'; category='AppInsights'; authType='ProjectManagedIdentity'
                PrivateLinkScopedResources=@(@{ResourceId='/synthetic/privateLink';ScopeId='synthetic-scope';secret='projection-secret-canary'})
                features=@{enableLogAccessUsingOnlyResourcePermissions=$true}
                metadata=@{ResourceId='/synthetic/target';ApplicationInsightsConnectionString='projection-secret-canary'}
                credentials=@{secret='projection-secret-canary'}
            }
            identity=@{type='UserAssigned';userAssignedIdentities=@{
                '/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/synthetic/providers/Microsoft.ManagedIdentity/userAssignedIdentities/synthetic'=@{
                    principalId='22222222-2222-2222-2222-222222222222';clientId='33333333-3333-3333-3333-333333333333';secret='projection-secret-canary'
                }
            }}
        }
        $data = if ($collection) { @{value=@($item);nextLink=$null} } else {$item}
        $parityCases.Add(@{kind=$kind;collection=$collection;query=(Get-MetadataProjection $kind $collection)
            data=$data;native=(ConvertTo-ArmMetadata $data $kind $collection)})
    }
}
foreach ($case in $parityCases) {
    Assert-True (($case.native | ConvertTo-Json -Depth 90) -notmatch 'projection-secret-canary|secret-condition-text') 'Native metadata excludes synthetic credentials and condition bodies at every supported kind'
}
ConvertTo-Json -InputObject @($parityCases.ToArray()) -Depth 95 | Set-Content (Join-Path $OutputDirectory 'native-projections.json')
