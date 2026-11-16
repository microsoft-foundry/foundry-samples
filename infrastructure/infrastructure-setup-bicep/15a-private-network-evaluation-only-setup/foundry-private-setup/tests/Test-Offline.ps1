#Requires -Version 7.2
[CmdletBinding()]
param([Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$skill = Join-Path $PSScriptRoot '..'
$null = New-Item -ItemType Directory -Path $OutputDirectory -Force
. (Join-Path $skill 'scripts\SetupEngine.ps1')
$script:checks = 0
function Check([bool]$Value,[string]$Message) { if (!$Value) { throw "ASSERTION: $Message" }; $script:checks++ }
function Reject([scriptblock]$Body,[string]$Message) { $bad=$false;try{& $Body|Out-Null}catch{$bad=$true}; Check $bad $Message }

foreach($case in @(@{name='empty';json='[]'},@{name='single';json='[{"id":"one"}]'},
    @{name='nested';json='[[],[1],null]'},@{name='null';json='null'},
    @{name='dates';json='{"time":"2026-10-21T20:40:00Z","date":"2026-10-21"}'})){
    $value=ConvertFrom-SetupJson $case.json
    $copy=Copy-Data $value
    $same=if($case.name -eq 'dates'){$copy.time -is [string] -and $copy.time -ceq '2026-10-21T20:40:00Z' -and $copy.date -is [string] -and $copy.date -ceq '2026-10-21'}
        else{(ConvertTo-Json -InputObject $copy -Compress -Depth 100) -ceq $case.json}
    Check $same "Independent JSON clone shape $($case.name)"
    $path=Join-Path $OutputDirectory "json-$($case.name).json"
    Write-Json $path $value
    $loaded=Read-Json $path
    $same=if($case.name -eq 'dates'){$loaded.time -is [string] -and $loaded.time -ceq '2026-10-21T20:40:00Z' -and $loaded.date -is [string] -and $loaded.date -ceq '2026-10-21'}
        else{(ConvertTo-Json -InputObject $loaded -Compress -Depth 100) -ceq $case.json}
    Check $same "JSON file boundary $($case.name)"
}
$distinct=ConvertFrom-SetupJson '{"ResourceId":"upper","resourceId":"lower"}'
Check ($distinct.Count -eq 2 -and $distinct['ResourceId'] -ceq 'upper' -and $distinct['resourceId'] -ceq 'lower') 'Case-distinct JSON keys retained'
$deep='"leaf"';for($i=0;$i -lt 70;$i++){$deep='{"child":'+$deep+'}'}
$deepValue=ConvertFrom-SetupJson $deep
Check ((ConvertTo-Json -InputObject (Copy-Data $deepValue) -Compress -Depth 100) -ceq $deep) 'Depth70 roundtrip matches supported write depth'

$tools = Get-SetupToolchain
Check ($tools.versions.azureCli -and $tools.bicepVersion) 'Installed tool versions recorded without exact locks'
$polluted = $env:PYTHONPATH; $env:PYTHONPATH = 'C:\not-the-cli\poison'
try {
    $start = New-CleanProcess $tools.python @('-I','-B','-c','import sys,json,azure.cli.core;print(json.dumps({"version":azure.cli.core.__version__,"isolated":sys.flags.isolated,"path":sys.path}))')
    Check (!$start.Environment.ContainsKey('PYTHONPATH') -and $start.Environment['AZURE_EXTENSION_USE_DYNAMIC_INSTALL'] -eq 'no') 'Poison/global install environment excluded'
    $probe = Invoke-NativeProcess $start
    $data = $probe.stdout | ConvertFrom-Json -AsHashtable
    Check ($probe.code -eq 0 -and $data.version -and $data.isolated -eq 1 -and !@($data.path | Where-Object { $_ -like '*poison*' }).Count) 'Real isolated local CLI version import ignores PYTHONPATH'
    Check ($env:PYTHONPATH -eq 'C:\not-the-cli\poison') 'Caller environment not mutated by child cleaning'
} finally { $env:PYTHONPATH = $polluted }
$script:realNative = ${function:Invoke-NativeProcess}
$script:realTools = $tools
Remove-Variable SetupTools -Scope Script
$script:missingCapability=$false
function Invoke-NativeProcess {
    param($Start,$TimeoutSeconds,$OnStart)
    $text=if($Start.ArgumentList -contains '--version'){'Bicep CLI version 0.42.99 (compatible)'}
        elseif($Start.ArgumentList -contains '-c'){'{"python":"3.14.8","azureCli":"2.91.1"}'}
        elseif($script:missingCapability){'Required command unavailable'}
        else{'--no-wait --template-file --parameters --resource-group --no-pretty-print --result-format --method --body --headers'}
    @{code=0;stdout=$text;stderr='';elapsedMs=0}
}
$compatible=Get-SetupToolchain
Check ($compatible.versions.azureCli -eq '2.91.1' -and $compatible.versions.python -eq '3.14.8' -and $compatible.bicepVersion -eq '0.42.99') 'Compatible version differences accepted by capability checks'
Remove-Variable SetupTools -Scope Script
$script:missingCapability=$true
Reject { Get-SetupToolchain } 'Missing required capability fails explicitly without install'
${function:Invoke-NativeProcess} = $script:realNative
$script:SetupTools = $script:realTools

$setupInput = Read-SetupInput (Join-Path $skill 'assets\input.no-monitoring.example.json')
$config = $setupInput.config; $options = $setupInput.options
$graph = New-SetupPlan $config $options
Check ($graph.planHash -ceq (New-SetupPlan (Copy-Data $config) (Copy-Data $options)).planHash) 'Deterministic local DAG'
Assert-SetupPlan $graph
Check (@($graph.nodes | Where-Object id -eq 'ProjectHost').Count -eq 0) 'Project host not unconditional'
Check (@($graph.nodes | Where-Object { $_.id -match 'Monitor|Insights|Workspace' }).Count -eq 0) 'No-monitoring graph omits all monitoring nodes'
foreach ($id in @('Network','Storage','Account')) { Check ((Get-Digest ($graph.nodes | Where-Object id -eq $id).dependsOn) -eq (Get-Digest @('ResourceGroup'))) "Independent $id follows only RG" }
Check ((Get-Digest ($graph.nodes | Where-Object id -eq 'Project').dependsOn) -eq (Get-Digest @('Account'))) 'Project after account only'
Check ((Get-Digest ($graph.nodes | Where-Object id -eq 'StorageConnectivity').dependsOn) -eq (Get-Digest @('Network','Storage'))) 'Storage PE needs only network/storage'
$monitorInput = Read-SetupInput (Join-Path $skill 'assets\input.example.json')
$monitorConfig = $monitorInput.config; $monitorOptions = $monitorInput.options
$monitorGraph = New-SetupPlan $monitorConfig $monitorOptions
Check (@($monitorGraph.nodes | Where-Object id -eq 'ProjectHost').Count -eq 1) 'Requested host is an explicit selectable node'
Check (@($monitorGraph.nodes | Where-Object id -eq 'MonitorConnectivity').Count -eq 1) 'Monitor grouped dependencies generated'
$bad = Copy-Data $graph; $bad.nodes[1].writeScopes = @('different'); $bad.Remove('planHash');$bad.planHash=Get-Digest $bad
Reject { Assert-SetupPlan $bad } 'Forged nodes not accepted even with recomputed JSON hash'
Reject { Assert-IntegrationOptions $monitorOptions $config } 'Mismatched no-monitoring options rejected'
Check ($monitorConfig.workload.intent -ceq 'trace' -and $monitorConfig.workload.routeGoal -ceq 'direct-private' -and $monitorConfig.workload.projectHost -ceq 'requested') 'Omitted workload defaults to trace/direct-private/requested with monitoring'
Check ($config.workload.projectHost -ceq 'not-requested') 'Explicit workload choices are kept'
Check (!$monitorConfig.Contains('privateNetworking') -and @($monitorOptions.dnsZones.Keys).Count -eq 8 -and @($monitorOptions.privateEndpoints.Keys).Count -eq 3 -and
    !@($monitorOptions.dnsZones.Values | Where-Object mode -cne 'create').Count) 'Omitted privateNetworking defaults every zone/PE to create'
Check ($monitorOptions.monitorPrivateLink.mode -ceq 'create' -and $monitorOptions.monitorPrivateLink.name -ceq 'ampls-evaluation-example') 'Default AMPLS name derived from account'
Check (!$options.Contains('monitorPrivateLink') -and @($options.dnsZones.Keys).Count -eq 4) 'No-monitoring defaults omit monitor zones/AMPLS'
$mixedRaw = Read-Json (Join-Path $skill 'assets\input.example.json')
$mixedRaw.privateNetworking = @{ dnsZones = @{ 'privatelink.blob.core.windows.net' = @{ mode = 'existing'; resourceId = "/subscriptions/$($config.subscriptionId)/resourceGroups/dns/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"; linkVnet = $false } } }
$mixedPath = Join-Path $OutputDirectory 'input-mixed.json'; Write-Json $mixedPath $mixedRaw
$mixed = Read-SetupInput $mixedPath
Check ($mixed.options.dnsZones['privatelink.blob.core.windows.net'].mode -ceq 'existing' -and $mixed.options.dnsZones['privatelink.monitor.azure.com'].mode -ceq 'create') 'Partial BYO networking merges with create defaults'
$mixedRaw.privateNetworking.unknown = @{}; Write-Json $mixedPath $mixedRaw
Reject { Read-SetupInput $mixedPath } 'Unknown privateNetworking section rejected'
$noMonitorRaw = Read-Json (Join-Path $skill 'assets\input.no-monitoring.example.json')
$noMonitorRaw.privateNetworking = @{ monitorPrivateLink = @{ mode = 'create'; name = 'ampls-x' } }
Write-Json $mixedPath $noMonitorRaw
Reject { Read-SetupInput $mixedPath } 'Monitoring-none rejects AMPLS options'
Check ((ConvertTo-PackagePath 'assets\bicep\storage.bicep') -ceq (ConvertTo-PackagePath 'assets/bicep/storage.bicep')) 'Cross-platform package path normalization'
$win=@{};$unix=@{};$win[(ConvertTo-PackagePath 'scripts\Input.ps1')]='abcd';$unix[(ConvertTo-PackagePath 'scripts/Input.ps1')]='abcd'
Check ((Get-Digest $win) -ceq (Get-Digest $unix)) 'Windows/Linux same-byte package maps hash identically'

Add-Type -TypeDefinition @'
using System.Threading;
public static class SetupTestSignals {
    public static long Sequence;
    public static int Calls;
    public static Barrier Branches = new Barrier(3);
    public static long Next() { return Interlocked.Increment(ref Sequence); }
    public static void Called() { Interlocked.Increment(ref Calls); }
}
'@
$worker = @'
param($Root,$Graph,$Node,$Mode,$Directory,$Approval,$Ack)
[SetupTestSignals]::Called()
$begin=[SetupTestSignals]::Next()
if($Node.id -in @('Network','Storage','Account')) {
    if(![SetupTestSignals]::Branches.SignalAndWait([TimeSpan]::FromSeconds(30))) { throw 'Branch barrier did not receive all independent workers' }
}
@{node=$Node.id;state='Succeeded';begin=$begin;end=[SetupTestSignals]::Next()}
'@
$parallel = Invoke-SetupSelection $graph @('ResourceGroup','Network','Storage','Account','Project') 'Apply' (Join-Path $OutputDirectory 'dag-parallel') @{} 3 $false $worker
foreach($id in @('Network','Storage','Account')) { Check ($parallel.nodes[$id].begin -ge $parallel.nodes.ResourceGroup.end) "Actual worker $id after RG" }
$branch = @($parallel.nodes.Network,$parallel.nodes.Storage,$parallel.nodes.Account)
Check ((($branch.begin | Measure-Object -Maximum).Maximum) -lt (($branch.end | Measure-Object -Minimum).Minimum)) 'Actual independent worker execution overlaps'
Check ($parallel.nodes.Project.begin -ge $parallel.nodes.Account.end) 'Actual project waits account'
$conflicts = Invoke-SetupSelection $graph @('FoundryConnectivity','StorageConnectivity') 'Apply' (Join-Path $OutputDirectory 'dag-conflicts') @{} 3 $false $worker
$a=$conflicts.nodes.FoundryConnectivity;$b=$conflicts.nodes.StorageConnectivity
Check ($a.end -le $b.begin -or $b.end -le $a.begin) 'Actual shared-subnet writes never overlap'
Check (Test-ScopeConflict @('/a/b') @('/a/b/c')) 'Ancestor scope conflicts'
Check (!(Test-ScopeConflict @('/a/b') @('/a/b-other'))) 'Unrelated prefix is not a scope conflict'
$rejectWorker = 'param($Root,$Graph,$Node,$Mode,$Directory,$Approval,$Ack); [SetupTestSignals]::Called(); @{node=$Node.id;state="NotSubmitted"}'
$calls=[SetupTestSignals]::Calls
$terminal = Invoke-SetupSelection $graph @('Account','Project','Storage') 'Apply' (Join-Path $OutputDirectory 'dag-terminal') @{} 3 $false $rejectWorker
Check ($terminal.nodes.Project.state -eq 'Blocked' -and ([SetupTestSignals]::Calls-$calls) -eq 2) 'Terminal NotSubmitted is not polled/retried; dependent never invoked'

$runWorker = @'
param($Root,$Graph,$Node,$Mode,$Directory,$Approval,$Ack)
$parent=Split-Path $Directory
Add-Content (Join-Path $parent 'calls.log') "$Mode $($Node.id)"
if($Node.kind -eq 'Reference'){return @{node=$Node.id;state='Succeeded'}}
switch($Mode){
    'Preview' { @{node=$Node.id;state='PreviewReady';previewPath=(Join-Path $Directory 'p.json');approvalHash="h-$($Node.id)"} }
    'Apply' {
        if($Approval.approvalHash -cne "h-$($Node.id)"){throw 'Wrong per-node approval passed'}
        $flag=Join-Path $parent 'unknown-storage.flag'
        if($Node.id -eq 'Storage' -and (Test-Path $flag)){Remove-Item $flag;@{node=$Node.id;state='OutcomeUnknown';nextAction='ReadOnlyReconcileNoResubmit'}}
        elseif($Node.id -eq 'Injection' -and !$Ack){throw 'Injection without acknowledgment'}
        else{@{node=$Node.id;state='Succeeded'}}
    }
    'Reconcile' { @{node=$Node.id;state='Succeeded';nextAction='None'} }
}
'@
$runDir=Join-Path $OutputDirectory 'plan-run'
$null=New-Item -ItemType Directory $runDir -Force;Set-Content (Join-Path $runDir 'unknown-storage.flag') 'x'
Reject {Invoke-SetupRun $monitorGraph $runDir 'not-the-plan' $false 1 $runWorker} 'Run requires the exact reviewed planHash'
$first=Invoke-SetupRun $monitorGraph $runDir $monitorGraph.planHash $false 1 $runWorker
$log=@(Get-Content (Join-Path $runDir 'calls.log'))
Check ($first.status -eq 'Stopped' -and $first.nodes.Storage -eq 'OutcomeUnknown') 'Run stops on unconfirmed outcome'
Check (!@($log|Where-Object {$_ -match 'StorageConnectivity|GrantStorage|Connections'}).Count) 'Dependents of an unconfirmed node never start'
$second=Invoke-SetupRun $monitorGraph $runDir $monitorGraph.planHash $false 1 $runWorker
$log=@(Get-Content (Join-Path $runDir 'calls.log'))
Check ($second.status -eq 'AwaitingAccountWideConfirmation' -and @($log|Where-Object {$_ -ceq 'Reconcile Storage'}).Count -eq 1) 'Resume reconciles once and holds at account-wide injection'
Check (@($log|Where-Object {$_ -ceq 'Apply Storage'}).Count -eq 1 -and @($log|Where-Object {$_ -ceq 'Apply ResourceGroup'}).Count -eq 1) 'Resume never resubmits unknown or Succeeded nodes'
Check (!@($log|Where-Object {$_ -match 'Injection|AccountHost|ProjectHost'}).Count) 'No injection/host work without acknowledgment'
$third=Invoke-SetupRun $monitorGraph $runDir $monitorGraph.planHash $true 1 $runWorker
$log=@(Get-Content (Join-Path $runDir 'calls.log'))
Check ($third.status -eq 'Completed' -and !@($third.nodes.Values|Where-Object {$_ -ne 'Succeeded'}).Count -and $third.nodes.Count -eq @($monitorGraph.nodes).Count) 'Acknowledged rerun completes every node'
Check (@($log|Where-Object {$_ -ceq 'Apply Injection'}).Count -eq 1 -and @($log|Where-Object {$_ -ceq 'Apply ProjectHost'}).Count -eq 1) 'Injection and hosts applied exactly once'
$beforeCount=$log.Count
$fourth=Invoke-SetupRun $monitorGraph $runDir $monitorGraph.planHash $true 1 $runWorker
Check ($fourth.status -eq 'Completed' -and @(Get-Content (Join-Path $runDir 'calls.log')).Count -eq $beforeCount) 'Completed run is idempotent with zero worker calls'
Reject {Invoke-SetupRun $graph $runDir $graph.planHash $true 1 $runWorker} 'State directory bound to one plan'
$rejectDir=Join-Path $OutputDirectory 'plan-run-rejected'
$rejectPreview='param($Root,$Graph,$Node,$Mode,$Directory,$Approval,$Ack); if($Node.id -eq ''Network''){throw ''what-if Modify''}; if($Mode -eq ''Preview''){@{node=$Node.id;state=''PreviewReady'';previewPath=''x'';approvalHash=''h''}}else{@{node=$Node.id;state=''Succeeded''}}'
$rejected=Invoke-SetupRun $graph $rejectDir $graph.planHash $false 1 $rejectPreview
$rejectedRun=Read-Json (Join-Path $rejectDir 'run.json')
Check ($rejected.status -eq 'Stopped' -and $rejectedRun.nodes.Storage.state -eq 'NotSubmitted' -and !@($rejectedRun.history|Where-Object step -eq 'Apply'|Where-Object node -ne 'ResourceGroup').Count) 'A rejected preview stops the wave before any sibling apply'
$driftWorker = @'
param($Root,$Graph,$Node,$Mode,$Directory,$Approval,$Ack)
$parent=Split-Path $Directory
Add-Content (Join-Path $parent 'calls.log') "$Mode $($Node.id)"
if($Mode -eq 'Preview'){return @{node=$Node.id;state='PreviewReady';previewPath='x';approvalHash='h'}}
$flag=Join-Path $parent "drift-$($Node.id).flag"
if(Test-Path $flag){ if((Get-Content $flag) -ne 'always'){Remove-Item $flag}; return @{node=$Node.id;state='NotSubmitted';nextAction='FreshScopedPreview'} }
@{node=$Node.id;state='Succeeded'}
'@
$driftDir=Join-Path $OutputDirectory 'plan-run-drift'
$null=New-Item -ItemType Directory $driftDir -Force;Set-Content (Join-Path $driftDir 'drift-GrantAccount.flag') 'once'
$drifted=Invoke-SetupRun $monitorGraph $driftDir $monitorGraph.planHash $true 1 $driftWorker
$driftLog=@(Get-Content (Join-Path $driftDir 'calls.log'))
Check ($drifted.status -eq 'Completed' -and @($driftLog|Where-Object {$_ -ceq 'Apply GrantAccount'}).Count -eq 2 -and @($driftLog|Where-Object {$_ -ceq 'Preview GrantAccount'}).Count -eq 2) 'Sibling-caused prewrite drift gets exactly one fresh preview and completes'
$driftDir2=Join-Path $OutputDirectory 'plan-run-drift-always'
$null=New-Item -ItemType Directory $driftDir2 -Force;Set-Content (Join-Path $driftDir2 'drift-GrantAccount.flag') 'always'
$stuckDrift=Invoke-SetupRun $monitorGraph $driftDir2 $monitorGraph.planHash $true 1 $driftWorker
$driftLog2=@(Get-Content (Join-Path $driftDir2 'calls.log'))
Check ($stuckDrift.status -eq 'Stopped' -and @($driftLog2|Where-Object {$_ -ceq 'Apply GrantAccount'}).Count -eq 2 -and !@($driftLog2|Where-Object {$_ -match 'Injection'}).Count) 'Repeated drift stops after one fresh preview; dependents never start'
$midRun=Read-Json (Join-Path $driftDir2 'run.json')
Check ($midRun.status -eq 'Stopped') 'Stopped run is recorded as Stopped'
$progressDir=Join-Path $OutputDirectory 'plan-run-progress'
$progressWorker='param($Root,$Graph,$Node,$Mode,$Directory,$Approval,$Ack); $s=Join-Path (Split-Path $Directory) ''run.json''; if((Test-Path $s) -and (Get-Content $s -Raw) -match ''"status":\s*"Completed"''){ Add-Content (Join-Path (Split-Path $Directory) ''bad.log'') $Node.id }; if($Mode -eq ''Preview''){@{node=$Node.id;state=''PreviewReady'';previewPath=''x'';approvalHash=''h''}}else{@{node=$Node.id;state=''Succeeded''}}'
$progress=Invoke-SetupRun $graph $progressDir $graph.planHash $false 1 $progressWorker
Check (!(Test-Path (Join-Path $progressDir 'bad.log'))) 'Mid-run state is InProgress, not Completed'
$script:armCalls=0
function Invoke-SetupArm { param($Method,$Id); $script:armCalls++; if($script:armCalls -eq 1){@{Code=0;ErrorCode='CliFailure'}}else{@{Code=200;Data=@{properties=@{provisioningState='Succeeded'}}}} }
$waited=Wait-SetupResource '/x' 30 0
Check ($waited.properties.provisioningState -eq 'Succeeded' -and $script:armCalls -eq 2) 'Read-back retries a CLI failure with no HTTP status'
function Invoke-SetupArm { param($Method,$Id); @{Code=403;ErrorCode='AuthorizationFailed'} }
Reject {Wait-SetupResource '/x' 30 0} 'Read-back still fails fast on authorization errors'
$script:SetupReadRetrySeconds=0;$script:armCalls=0
function Invoke-SetupArm { param($Method,$Id); $script:armCalls++; if($script:armCalls -lt 3){@{Code=0;ErrorCode='CliFailure';Detail='ERROR: connection reset'}}else{@{Code=200;Data=@{ok=$true}}} }
Check ((Get-SetupResource '/x').ok -and $script:armCalls -eq 3) 'Read-only GET retries a transient CLI failure'
function Invoke-SetupArm { param($Method,$Id); $script:armCalls++; @{Code=0;ErrorCode='CliFailure';Detail='ERROR: connection reset'} }
$script:armCalls=0;$readError='';try{$null=Get-SetupResource '/x'}catch{$readError=$_.Exception.Message}
Check ($script:armCalls -eq 3 -and $readError -match 'connection reset' -and $readError -match 'changed nothing' -and $readError -match 'rerun the same Run command') 'Persistent read failure names the CLI detail and the safe recovery'
function Invoke-SetupArm { param($Method,$Id); $script:armCalls++; @{Code=403;ErrorCode='AuthorizationFailed'} }
$script:armCalls=0;Reject {Get-SetupResource '/x'} 'Authorization read failure surfaces'
Check ($script:armCalls -eq 1) 'Authorization read failure is not retried'
$detail=Get-SetupErrorDetail "WARNING: noise`nERROR: Bad request Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.payload.sig token=abc123&x=1"
Check ($detail -match '^ERROR: Bad request' -and $detail -notmatch 'eyJhbGci|abc123') 'CLI detail picks the error line and redacts token-like values'
Check ((Get-SetupErrorDetail '') -match 'no error text' -and (Get-SetupErrorDetail ('ERROR: '+('x'*400))).Length -le 303) 'Empty and long CLI details are bounded'

$failWorker = @'
param($Root,$Graph,$Node,$Mode,$Directory,$Approval,$Ack)
$parent=Split-Path $Directory
Add-Content (Join-Path $parent 'calls.log') "$Mode $($Node.id)"
if($Mode -eq 'Preview'){return @{node=$Node.id;state='PreviewReady';previewPath='x';approvalHash='h'}}
$flag=Join-Path $parent "fail-$($Node.id).flag"
if(Test-Path $flag){ $left=[int](Get-Content $flag); if($left -le 1){Remove-Item $flag}else{Set-Content $flag ($left-1)}; return @{node=$Node.id;state='Failed';nextAction='InspectConfirmedFailure'} }
@{node=$Node.id;state='Succeeded'}
'@
Check (($graph.nodes|Where-Object id -eq 'Storage').kind -eq 'Deployment') 'Fixture Storage node is a deployment'
$failDir=Join-Path $OutputDirectory 'plan-run-failed'
$null=New-Item -ItemType Directory $failDir -Force;Set-Content (Join-Path $failDir 'fail-Storage.flag') '2'
$failedRun=Invoke-SetupRun $graph $failDir $graph.planHash $true 1 $failWorker
Check ($failedRun.status -eq 'Stopped' -and $failedRun.nodes.Storage -eq 'Failed' -and $failedRun.reason -match 'retry Failed deployments once') 'Confirmed Failed deployment stops the run with retry guidance'
$failedAgain=Invoke-SetupRun $graph $failDir $graph.planHash $true 1 $failWorker
$failLog=@(Get-Content (Join-Path $failDir 'calls.log'))
Check ($failedAgain.status -eq 'Stopped' -and @($failLog|Where-Object {$_ -ceq 'Apply Storage'}).Count -eq 2) 'Rerun retries a Failed deployment exactly once, then stops again'
$recovered=Invoke-SetupRun $graph $failDir $graph.planHash $true 1 $failWorker
$failLog=@(Get-Content (Join-Path $failDir 'calls.log'))
Check ($recovered.status -eq 'Completed' -and @($failLog|Where-Object {$_ -ceq 'Apply Storage'}).Count -eq 3 -and @($failLog|Where-Object {$_ -ceq 'Apply ResourceGroup'}).Count -eq 1) 'Retry after a fixed cause completes without repeating Succeeded nodes'

$ownDir=Join-Path $OutputDirectory 'owned-endpoint'
$ownedPe='/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg/providers/Microsoft.Network/privateEndpoints/pe-account'
$ownedZone='/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net'
Write-Json (Join-Path $ownDir 'op1.preview.json') @{kind='Deployment';operationId='op1';preview=@(@{resourceId=$ownedPe;changeType='Create'},@{resourceId=$ownedZone;changeType='Create'})}
Write-Json (Join-Path $ownDir 'op1.attempt.json') @{operationId='op1';state='Failed';submissionStartedAt=1}
Write-Json (Join-Path $ownDir 'op2.preview.json') @{kind='Deployment';operationId='op2';preview=@(@{resourceId=($ownedPe+'-other');changeType='Create'})}
Write-Json (Join-Path $ownDir 'op2.attempt.json') @{operationId='op2';state='NotSubmitted'}
$owned=@(Get-PriorFailedCreates $ownDir)
Check ($ownedPe -in $owned -and $ownedZone -in $owned -and ($ownedPe+'-other') -notin $owned) 'Only resources planned by a submitted, confirmed-Failed attempt count as setup-created'
$script:SetupStateDirectory=$ownDir
$failedPeMessage=Get-ExistingEndpointMessage @{properties=@{provisioningState='Failed'}} $ownedPe
Check ($failedPeMessage -match 'earlier failed attempt' -and $failedPeMessage -match 'az network private-endpoint delete --resource-group rg --name pe-account' -and $failedPeMessage -match 'rerun the same Run command') 'Setup-created Failed endpoint gets exact delete-then-rerun guidance'
$okPeMessage=Get-ExistingEndpointMessage @{properties=@{provisioningState='Succeeded'}} $ownedPe
Check ($okPeMessage -match 'state: Succeeded' -and $okPeMessage -match 'inspect it') 'Setup-created non-Failed endpoint is inspected, never overwritten'
$script:SetupStateDirectory=Join-Path $OutputDirectory 'owned-endpoint-missing'
$customerPeMessage=Get-ExistingEndpointMessage @{properties=@{provisioningState='Failed'}} $ownedPe
Check ($customerPeMessage -match 'not created by this setup' -and $customerPeMessage -notmatch 'delete --resource-group') 'Same-name endpoint without setup evidence is never treated as setup-created'
$script:SetupStateDirectory=''

$changedPlan=Copy-Data $graph;$changedPlan.packageHash='0'*64
$changedPlan.packageFiles.Remove('SKILL.md');$changedPlan.packageFiles['scripts/Setup.ps1']='0'*64;$changedPlan.packageFiles['plan.json']='0'*64
$copy=Copy-Data $changedPlan;$copy.Remove('planHash');$changedPlan.planHash=Get-Digest $copy
$packageError='';try{Assert-SetupPlan $changedPlan}catch{$packageError=$_.Exception.Message}
Check ($packageError -match 'added: SKILL\.md' -and $packageError -match 'removed: plan\.json' -and $packageError -match 'changed: scripts/Setup\.ps1' -and $packageError -match 'outside the extracted package folder') 'Package change names the files and where plan/state belong'
$editedPlan=Copy-Data $graph;$editedPlan.nodes[0].budgetSeconds=1
$editError='';try{Assert-SetupPlan $editedPlan}catch{$editError=$_.Exception.Message}
Check ($editError -match 'edited after Plan generated it') 'Hand-edited plan is reported as an edit, not a package change'

$script:reads=0;$script:writes=@();$script:mode='Success';$script:resources=@{};$script:collections=@{}
$ids=Get-SetupIds $config
function Assert-SetupContext {param($Config)}
function Invoke-SetupCli { throw 'OFFLINE: unmocked Azure CLI forbidden' }
function Invoke-DeploymentExport {
    param($Plan)
    @{Code=200;Data=@{parameters=@{location=@{type='String'};config=@{type='Object'};optional=@{type='Bool';defaultValue=$true}}}}
}
function Get-SetupResource {param($Id,[switch]$Optional);$script:reads++;if($script:resources.ContainsKey($Id)){return Copy-Data $script:resources[$Id]};if($Optional){return $null};throw "Missing synthetic resource: $Id"}
function Get-SetupCollection {param($Id);$script:reads++;if(!$script:collections.ContainsKey($Id)){throw "Missing synthetic collection: $Id"};return ,(Copy-Data $script:collections[$Id])}
function Invoke-SetupArm {
    param($Method,$Id,$Body,$ETag,[scriptblock]$OnStart)
    if($Method -eq 'GET'){ $x=Get-SetupResource $Id -Optional;return @{Code=$(if($x){200}else{404});Data=$x} }
    if($script:mode -eq 'BeforeStart'){throw 'Local preparation failed before process launch'}
    if($OnStart){& $OnStart}
    $script:writes+=@{method=$Method;id=$Id;body=(Copy-Data $Body)}
    if($script:mode -eq 'Lost'){return @{Code=408;Data=$null}}
    if($Method -eq 'PATCH'){$script:resources[$Id].properties.networkInjections=Copy-Data $Body.properties.networkInjections}
    else{$r=Copy-Data $Body;$r.id=$Id;if($Id -match '/capabilityHosts/'){$r.properties.provisioningState='Succeeded';$script:collections[($Id -replace '/capabilityHosts/[^/]+$','/capabilityHosts')]=@($r)};$script:resources[$Id]=$r}
    @{Code=200;Data=@{}}
}
function Reset-Fixture {
    $script:resources=@{};$script:collections=@{};$script:writes=@();$script:mode='Success'
    $script:resources[$ids.ResourceGroup]=@{id=$ids.ResourceGroup;location='koreacentral';tags=@{}}
    foreach($id in @($ids.Account,$ids.Project)) {
        $script:resources[$id]=@{id=$id;location='koreacentral';kind='AIServices';identity=@{type='SystemAssigned';principalId='11111111-1111-1111-1111-111111111111'}
            properties=@{provisioningState='Succeeded';internalId="stable-$($id.Split('/')[-1])";publicNetworkAccess='Enabled';networkInjections=@();unrelated='keep'};tags=@{}}
    }
    $script:resources[$ids.Storage]=@{id=$ids.Storage;kind='StorageV2';location='koreacentral';properties=@{provisioningState='Succeeded';primaryEndpoints=@{blob='https://evaluationexample.blob.core.windows.net/'};publicNetworkAccess='Disabled'}}
    $agent=@{id=$ids.AgentSubnet;name='agent';properties=@{addressPrefix='10.241.0.0/24';delegations=@(@{name='agent-delegation';properties=@{serviceName='Microsoft.App/environments'}})}}
    $pe=@{id=$ids.PeSubnet;name='pe';properties=@{addressPrefix='10.241.1.0/24';delegations=@();privateEndpointNetworkPolicies='Disabled'}}
    $script:resources[$ids.AgentSubnet]=$agent;$script:resources[$ids.PeSubnet]=$pe
    $script:resources[$ids.Vnet]=@{id=$ids.Vnet;location='koreacentral';properties=@{subnets=@($agent,$pe);addressSpace=@{addressPrefixes=@('10.241.0.0/16')}}}
    $script:collections["$($ids.Account)/projects"]=@($script:resources[$ids.Project])
    foreach($tail in @("$($ids.Account)/deployments","$($ids.Account)/connections","$($ids.Project)/connections","$($ids.Account)/capabilityHosts","$($ids.Project)/capabilityHosts")){$script:collections[$tail]=@()}
}
Reset-Fixture
$fixture=Read-Json (Join-Path $PSScriptRoot 'fixtures\deployment-network-succeeded.json')
$testTemplate=@{parameters=@{location=@{type='string'};config=@{type='object'};optional=@{type='bool';defaultValue=$true}}}
$requestParams=@{location=@{value='koreacentral'};config=@{value=$config.network}}
Check ((Get-Digest $fixture.properties.parameters) -cne (Get-Digest $requestParams)) 'Recorded Azure type wrappers differ from raw request hash'
Check ((Get-Digest (Get-ParameterValues $testTemplate $fixture.properties.parameters)) -ceq (Get-Digest (Get-ParameterValues $testTemplate $requestParams))) 'Independent actual-shape fixture values/defaults match'
$request=@{asset='network';scope=$ids.ResourceGroup;resourceId=$fixture.id;template=$testTemplate;parameters=$requestParams;templateHash='145803366213390841'
    parametersHash=(Get-Digest (Get-ParameterValues $testTemplate $requestParams));observedIds=@()}
$plan=New-Approval 'Deployment' $config $request @{}
$plan.observed=@{};$plan.timings=@();$plan.preview=@(@{resourceId=$ids.Vnet;changeType='Create'});$plan=Seal-Approval $plan
$attempt=@{receipt=@{submissionStartedAt=([DateTimeOffset]::Parse('2026-10-21T20:39:00Z').ToUnixTimeMilliseconds())}}
$resources[$fixture.id]=Copy-Data $fixture
$outcome=Get-DeploymentOutcome $plan $attempt
Check ($outcome.state -eq 'Succeeded' -and $outcome.azureDurationMs -eq 72235) 'Actual Azure Succeeded automatically recognized with authoritative duration'
$resources[$fixture.id].properties.parameters.config.value.agentSubnetPrefix='10.241.8.0/24'
Check ((Get-DeploymentOutcome $plan $attempt).state -eq 'OutcomeUnknown') 'Wrong actual values rejected'
$resources[$fixture.id]=Copy-Data $fixture
$resources[$fixture.id].properties.timestamp='2026-10-21T20:38:00Z'
Check ((Get-DeploymentOutcome $plan $attempt).state -eq 'Succeeded') 'Ordinary clock skew tolerated with unique content/correlation attribution'
$resources[$fixture.id]=Copy-Data $fixture
$resources[$fixture.id].properties.timestamp='2026-10-21T20:30:00Z'
Check ((Get-DeploymentOutcome $plan $attempt).state -eq 'OutcomeUnknown') 'Old same-name attempt rejected'
$resources[$fixture.id]=Copy-Data $fixture;$attempt.receipt.correlationId='wrong'
Check ((Get-DeploymentOutcome $plan $attempt).state -eq 'OutcomeUnknown') 'Wrong recorded correlation rejected'
$attempt.receipt.Remove('correlationId')
$resources[$fixture.id].properties.parameters.config=@{type='Object'}
Check ((Get-DeploymentOutcome $plan $attempt).state -eq 'OutcomeUnknown') 'Unobservable/redacted values rejected'
Reject {Get-ParameterValues $testTemplate @{location=@{value='koreacentral'}}} 'Missing required parameter rejected'
$wrong=Copy-Data $requestParams;$wrong.optional=@{type='Bool';value='true'}
Check ((Get-Digest (Get-ParameterValues $testTemplate $wrong)) -cne $request.parametersHash) 'No coercion of string true into bool default'

Reset-Fixture
$resources.Remove($ids.Storage)
$script:deploymentCalls=@()
function Invoke-DeploymentCli {
    param($Verb,$Plan,[scriptblock]$OnStart)
    if($Verb -eq 'what-if'){return @{Code=200;Data=@{changes=@(@{resourceId=$ids.Storage;changeType='Create'})}}}
    if($script:mode -eq 'BeforeStart'){throw 'Local request file construction failed'}
    if($OnStart){& $OnStart};$script:deploymentCalls+=$Verb;@{Code=408;Data=$null}
}
$request=@{asset='storage';scope=$ids.ResourceGroup;resourceId="$($ids.ResourceGroup)/providers/Microsoft.Resources/deployments/lost-storage";template=$testTemplate;parameters=$requestParams;templateHash='145803366213390841';parametersHash=$plan.request.parametersHash;observedIds=@($ids.Storage)}
$state=Get-DeploymentState $config $request
$plan=New-Approval 'Deployment' $config $request $state.material;$plan.observed=$state.observations;$plan.timings=@();$plan.preview=@(@{resourceId=$ids.Storage;changeType='Create'});$plan=Seal-Approval $plan
$resources[$ids.Storage]=@{id=$ids.Storage;properties=@{changed='concurrent-create'}}
$dir=Join-Path $OutputDirectory 'prewrite'
Write-Json (Join-Path $dir 'last-verified-deployment.json') @{state='previous-good'}
$old=(Get-FileHash (Join-Path $dir 'last-verified-deployment.json')).Hash
Reject {Submit-Deployment $plan $plan.approvalHash $dir 0} 'Material prewrite drift terminal'
$receipt=Read-Json (Join-Path $dir "$($plan.operationId).attempt.json")
$before=$reads;$result=Reconcile-Deployment $plan $dir
Check ($result.state -eq 'NotSubmitted' -and $reads -eq $before -and $deploymentCalls.Count -eq 0) 'NotSubmitted returns immediately with ZERO deployment polling'
Check ((Get-FileHash (Join-Path $dir 'last-verified-deployment.json')).Hash -eq $old) 'Last verified preserved'
$resources.Remove($ids.Storage)
$fresh=New-Approval 'Deployment' $config $request (Get-DeploymentState $config $request).material;$fresh.observed=@{};$fresh.timings=@();$fresh.preview=$plan.preview;$fresh=Seal-Approval $fresh
$result=Submit-Deployment $fresh $fresh.approvalHash (Join-Path $OutputDirectory 'lost') 0
Check ($result.state -eq 'OutcomeUnknown' -and $deploymentCalls.Count -eq 1) 'Fresh scoped action can attempt and journal lost native write'
$null=Reconcile-Deployment $fresh (Join-Path $OutputDirectory 'lost')
Check ($deploymentCalls.Count -eq 1) 'Unknown lost deployment NEVER replayed'
$script:mode='BeforeStart'
$beforeStart=New-Approval 'Deployment' $config $request (Get-DeploymentState $config $request).material;$beforeStart.observed=@{};$beforeStart.timings=@();$beforeStart.preview=$plan.preview;$beforeStart=Seal-Approval $beforeStart
$dir=Join-Path $OutputDirectory 'no-process'
Reject {Submit-Deployment $beforeStart $beforeStart.approvalHash $dir 0} 'Local preparation failure surfaced'
$receipt=Read-Json (Join-Path $dir "$($beforeStart.operationId).attempt.json")
Check ($receipt.state -eq 'NotSubmitted' -and !$receipt.Contains('submissionStartedAt')) 'No process launch is not possibly submitted'

Reset-Fixture
$nsgId="$($ids.ResourceGroup)/providers/Microsoft.Network/networkSecurityGroups/nrms"
$resources[$nsgId]=@{id=$nsgId;tags=@{policy='one'};properties=@{securityRules=@(@{name='deny';properties=@{access='Deny';priority=100}})}}
$resources[$ids.PeSubnet].properties.networkSecurityGroup=@{id=$nsgId}
$resources[$ids.Vnet].properties.subnets[1].properties.networkSecurityGroup=@{id=$nsgId}
$node=$graph.nodes|Where-Object id -eq 'StorageConnectivity'
$parameters=@{};foreach($key in $node.values.Keys){$parameters[$key]=@{value=$node.values[$key]}}
$peRequest=@{asset='connectivity';scope=$ids.ResourceGroup;parameters=$parameters;observedIds=@()}
$before=Get-DeploymentState $config $peRequest
$resources[$nsgId].tags.policy='two';$resources[$nsgId].properties.securityRules[0].properties.priority=200
$after=Get-DeploymentState $config $peRequest
Check ((Get-Digest $before.material) -ceq (Get-Digest $after.material)) 'Unrelated NRMS NSG rule/tag content does not gate Storage PE'
Check (@(Get-SemanticDiff $before.observations $after.observations).Count -gt 0 -and $writes.Count -eq 0) 'Policy differences visible and never modified/adopted'
$resources[$ids.PeSubnet].properties.addressPrefix='10.241.2.0/24'
Check ((Get-Digest $before.material) -cne (Get-Digest (Get-DeploymentState $config $peRequest).material)) 'Real relevant subnet change gates PE'
Check (!(Get-Command Wait-NetworkQuiet -ErrorAction SilentlyContinue)) 'No network quiet-window wait before connectivity previews'

Reset-Fixture
$storageConnection=@{id="$($ids.Project)/connections/dataset-storage";properties=@{category='AzureStorageAccount';authType='AAD'
    target='https://evaluationexample.blob.core.windows.net/';metadata=@{ResourceId=$ids.Storage}}}
Check ($null -eq (Get-CompatibleConnection $config 'storage')) 'Absent fixed-name connection returns none'
$resources[$storageConnection.id]=Copy-Data $storageConnection
$projected=Copy-Data $storageConnection;$projected.id="$($ids.Account)/connections/dataset-storage"
$collections["$($ids.Account)/connections"]=@($projected);$collections["$($ids.Project)/connections"]=@($storageConnection)
Check ((Get-CompatibleConnection $config 'storage').id -ceq $storageConnection.id) 'Exact GET ignores account-level projection (no ambiguity)'
$resources[$storageConnection.id].properties.authType='AccountKey'
Reject {Get-CompatibleConnection $config 'storage'} 'Incompatible fixed-name connection is never overwritten'
$selection=Copy-Data $config;$selection.connectionSelection=@{storage="$($ids.Project)/connections/missing"}
Reject {Get-CompatibleConnection $selection 'storage'} 'Missing selected connection fails'
$resources["$($ids.Project)/connections/custom"]=Copy-Data $storageConnection;$resources["$($ids.Project)/connections/custom"].id="$($ids.Project)/connections/custom"
$selection.connectionSelection.storage="$($ids.Project)/connections/custom"
Check ((Get-CompatibleConnection $selection 'storage').id -like '*/connections/custom') 'Selected differently named compatible connection reused'

Reset-Fixture
$foundation=Get-FoundryState $config
foreach($key in @('identity','internalId','models','connections','unrelated','publicAccess')){
    $changed=Copy-Data $foundation
    switch($key){
        'identity'{$changed.resources[$ids.Account].identity.principalId='22222222-2222-2222-2222-222222222222'}
        'internalId'{$changed.resources[$ids.Project].properties.internalId='changed'}
        'models'{$changed.collections["$($ids.Account)/deployments"]=@(@{id='model'})}
        'connections'{$changed.collections["$($ids.Project)/connections"]=@(@{id='connection'})}
        'unrelated'{$changed.resources[$ids.Account].properties.unrelated='changed'}
        'publicAccess'{$changed.resources[$ids.Account].properties.publicNetworkAccess='Disabled'}
    };Reject {Assert-FoundryUnchanged $foundation $changed -AllowInjection} "Retrofit preserves $key"
}
$injection=New-FoundryPreview $config 'Injection'
Reject {Submit-Foundry $injection $injection.approvalHash (Join-Path $OutputDirectory 'no-ack')} 'Account-wide acknowledgment mandatory'
$result=Submit-Foundry $injection $injection.approvalHash (Join-Path $OutputDirectory 'injection') -AcknowledgeAccountWideImpact -TimeoutSeconds 0
Check ($result.state -eq 'Succeeded' -and $writes.Count -eq 1 -and $writes[0].method -eq 'PATCH' -and $writes[0].body.properties.Keys.Count -eq 1) 'Only narrow injection PATCH'
Check ($resources[$ids.Account].properties.publicNetworkAccess -eq 'Enabled') 'No implicit public-access lockdown'
Reject {New-FoundryPreview $config 'ProjectHost'} 'No default project-host creation'
$hostPlan=New-FoundryPreview $config 'AccountHost'
$result=Submit-Foundry $hostPlan $hostPlan.approvalHash (Join-Path $OutputDirectory 'account-host') -TimeoutSeconds 0
Check ($result.state -eq 'Succeeded') 'Explicit account host can be ensured'
$again=New-FoundryPreview $config 'AccountHost'
Check ($again.request.method -eq 'None') 'Matching host reuse has no PUT'
$hostConfig=Copy-Data $config;$hostConfig.workload.projectHost='requested'
$projectHost=New-FoundryPreview $hostConfig 'ProjectHost'
$result=Submit-Foundry $projectHost $projectHost.approvalHash (Join-Path $OutputDirectory 'project-host') -TimeoutSeconds 0
Check ($result.state -eq 'Succeeded' -and $result.result.route -eq 'NotVerified') 'Explicit project host is setup only, no route claim'

$clock=Start-Phase 'SyntheticSeparatePhase';$phase=Stop-Phase $clock
Check ($phase.elapsedMs -ge 0 -and $phase.startedUtc -match 'Z|\+00:00$' -and $phase.phase -eq 'SyntheticSeparatePhase') 'UTC and monotonic separate phase timing without wall-time threshold'
$attempt=New-Attempt (Seal-Approval (New-Approval 'Grant' $config @{one=1} @{})) (Join-Path $OutputDirectory 'metrics')
Add-AttemptTiming $attempt $phase
Check ($attempt.receipt.timings.Count -eq 1 -and !$attempt.receipt.Contains('azureDurationMs')) 'Local elapsed never masquerades as Azure duration'

$parsed=0;$builds=@()
foreach($file in Get-ChildItem (Join-Path $skill 'scripts') -Filter '*.ps1'){
    $e=$null;$null=[Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$null,[ref]$e)
    Check (@($e).Count -eq 0) "PS parse $($file.Name)";$parsed++
}
foreach($file in Get-ChildItem (Join-Path $skill 'assets') -Filter '*.json'){Check ($null -ne (Read-Json $file.FullName)) "JSON $($file.Name)"}
foreach($file in Get-ChildItem (Join-Path $skill 'assets\bicep') -Filter '*.bicep'){
    $output=Join-Path $OutputDirectory "$($file.BaseName).arm.json";$diagnostic=Join-Path $OutputDirectory "$($file.BaseName).diagnostics.txt"
    & $tools.bicep build $file.FullName --outfile $output 2> $diagnostic
    Check ($LASTEXITCODE -eq 0) "Build $($file.Name)"
    if($file.BaseName -eq 'storage'){Check ((Read-Json $output).resources[0].kind -ceq 'StorageV2') 'Independent Azure StorageV2 contract'}
    $builds+=@{asset=$file.Name;diagnostics=[string](Get-Content $diagnostic -Raw)}
}
Check ($builds.Count -eq 10) 'Exactly ten assets built'

Reset-Fixture
$resources.Remove($ids.Storage)
function Invoke-LocalBicep {param($File); Read-Json (Join-Path $OutputDirectory (([IO.Path]::GetFileNameWithoutExtension($File))+'.arm.json'))}
$script:mode='Lost'
$storageNode=$graph.nodes|Where-Object id -eq 'Storage'
$nodeResult=Invoke-SetupNode $graph $storageNode 'Preview' (Join-Path $OutputDirectory 'node-storage') @{}
Check ($nodeResult.state -eq 'PreviewReady' -and (Test-Path $nodeResult.previewPath)) 'Real node helper generates parameters and sealed native preview'
$approved=@{planPath=$nodeResult.previewPath;approvalHash=$nodeResult.approvalHash}
$nodeResult=Invoke-SetupNode $graph $storageNode 'Apply' (Join-Path $OutputDirectory 'node-storage') $approved
Check ($nodeResult.state -eq 'OutcomeUnknown' -and $nodeResult.result.timings.phase -contains 'LocalPreparation' -and
    $nodeResult.result.timings.phase -contains 'PreviewWhatIf' -and $nodeResult.result.timings.phase -contains 'SubmissionApply') 'Actual node records separated local/preview/submission timings'
$unknownId=$nodeResult.result.operationId
$freshAfterUnknown=Invoke-SetupNode $graph $storageNode 'Preview' (Join-Path $OutputDirectory 'node-storage') @{}
Check ($freshAfterUnknown.state -eq 'OutcomeUnknown' -and $freshAfterUnknown.nextAction -eq 'ReadOnlyReconcileOriginalAttempt' -and
    $freshAfterUnknown.originalOperationId -ceq $unknownId) 'Same-node unknown blockage retains original outcome and reconciliation guidance'
$unknownReceipt=Read-Json (Join-Path $OutputDirectory "node-storage\$unknownId.attempt.json")
Check ($unknownReceipt.state -eq 'OutcomeUnknown') 'Refused fresh preview preserves the original unknown attempt'
$runningDirectory=Join-Path $OutputDirectory 'node-running'
$runningReceipt=Copy-Data $unknownReceipt;$runningReceipt.state='Running'
Write-Json (Join-Path $runningDirectory "$unknownId.attempt.json") $runningReceipt
$beforeReads=$reads;$beforeWrites=$writes.Count
$runningBlock=Invoke-SetupNode $graph $storageNode 'Preview' $runningDirectory @{}
Check ($runningBlock.state -eq 'Running' -and $runningBlock.originalOperationId -ceq $unknownId -and
    $runningBlock.nextAction -eq 'ReadOnlyReconcileOriginalAttempt' -and
    $runningBlock.originalAttemptPath -eq (Join-Path $runningDirectory "$unknownId.attempt.json") -and
    $reads -eq $beforeReads -and $writes.Count -eq $beforeWrites) 'Running refusal gives original path and zero writes/polling'
$terminalDirectory=Join-Path $OutputDirectory 'node-terminal'
$terminalReceipt=Copy-Data $unknownReceipt;$terminalReceipt.state='NotSubmitted'
Write-Json (Join-Path $terminalDirectory "$unknownId.attempt.json") $terminalReceipt
$terminalPreview=Invoke-SetupNode $graph $storageNode 'Preview' $terminalDirectory @{}
Check ($terminalPreview.state -eq 'PreviewReady') 'Terminal NotSubmitted immediately permits a fresh scoped preview'

Reset-Fixture
$collections["$($ids.Account)/providers/Microsoft.Authorization/roleAssignments"]=@()
$collections["$($ids.Storage)/providers/Microsoft.Authorization/roleAssignments"]=@()
$accountGrant=New-GrantPreview $config 'Account';$storageGrant=New-GrantPreview $config 'Storage'
$writeCount=$writes.Count
Reject {Assert-NodeApproval $graph ($graph.nodes|Where-Object id -eq 'ResourceGroup') $accountGrant} 'RG rejects another operation kind'
$wrongRg=@{kind='ResourceGroup';config=$config;request=@{resourceId=$ids.Account}}
Reject {Assert-NodeApproval $graph ($graph.nodes|Where-Object id -eq 'ResourceGroup') $wrongRg} 'RG rejects wrong target'
Reject {Assert-NodeApproval $graph ($graph.nodes|Where-Object id -eq 'GrantStorage') $accountGrant} 'Storage grant rejects account approval'
Reject {Assert-NodeApproval $graph ($graph.nodes|Where-Object id -eq 'GrantAccount') $storageGrant} 'Account grant rejects storage approval'
Assert-NodeApproval $graph ($graph.nodes|Where-Object id -eq 'GrantStorage') $storageGrant
Check ($writes.Count -eq $writeCount) 'Node/target guards and accepted exact binding make zero writes'
$monitorIds=Get-SetupIds $monitorConfig
$lawId="$($ids.ResourceGroup)/providers/Microsoft.OperationalInsights/workspaces/law-evaluation"
$resources[$monitorIds.Insights]=@{id=$monitorIds.Insights;properties=@{WorkspaceResourceId=$lawId}}
$monitorGrant=@{kind='Grant';config=$monitorConfig;request=@{scope=$monitorIds.Insights;
    resourceId="$($monitorIds.Insights)/providers/Microsoft.Authorization/roleAssignments/one";
    body=@{properties=@{roleDefinitionId="/subscriptions/$($config.subscriptionId)/providers/Microsoft.Authorization/roleDefinitions/73c42c96-874c-492b-b04d-ab87d138a893"}}}}
Reject {Assert-NodeApproval $monitorGraph ($monitorGraph.nodes|Where-Object id -eq 'GrantWorkspace') $monitorGrant} 'Workspace rejects Insights grant approval'
$lawGrant=Copy-Data $monitorGrant;$lawGrant.request.scope=$lawId;$lawGrant.request.resourceId="$lawId/providers/Microsoft.Authorization/roleAssignments/one"
Reject {Assert-NodeApproval $monitorGraph ($monitorGraph.nodes|Where-Object id -eq 'GrantInsights') $lawGrant} 'Insights rejects workspace grant approval'

Reset-Fixture
$resources.Remove($ids.Vnet)
$fixture=Read-Json (Join-Path $PSScriptRoot 'fixtures\deployment-network-succeeded.json')
$nativeRequest=@{asset='network';scope=$ids.ResourceGroup;resourceId=$fixture.id;template=$testTemplate;parameters=$requestParams;
    templateHash='145803366213390841';parametersHash=(Get-Digest (Get-ParameterValues $testTemplate $requestParams));observedIds=@($ids.Vnet)}
function Invoke-DeploymentCli {
    param($Verb,$Plan,[scriptblock]$OnStart)
    if($Verb -ne 'create'){throw 'Unexpected preview in native status fixture'}
    if($OnStart){& $OnStart};$script:deploymentCalls+=$Verb
    $observed=Copy-Data $fixture
    $observed.properties.timestamp=[DateTimeOffset]::UtcNow.ToString('o')
    $observed.properties.provisioningState=$script:serverState
    $script:resources[$Plan.request.resourceId]=$observed
    @{Code=200;Data=@{id=$Plan.request.resourceId}}
}
$native=New-Approval 'Deployment' $config $nativeRequest (Get-DeploymentState $config $nativeRequest).material
$native.observed=@{};$native.timings=@();$native.preview=@(@{resourceId=$ids.Vnet;changeType='Create'});$native=Seal-Approval $native
$script:serverState='Succeeded';$dir=Join-Path $OutputDirectory 'real-shape-succeeded'
$nativeResult=Submit-Deployment $native $native.approvalHash $dir 0
Check ($nativeResult.state -eq 'Succeeded' -and $nativeResult.result.azureDurationMs -eq 72235) 'Submission automatically confirms realistic Azure type/value response'
$before=$reads;$null=Reconcile-Deployment $native $dir
Check ($reads -eq $before) 'Confirmed success no longer polled'
foreach($state in @('Failed','Running')){
    $resources.Remove($fixture.id)
    $next=New-Approval 'Deployment' $config $nativeRequest (Get-DeploymentState $config $nativeRequest).material
    $next.observed=@{};$next.timings=@();$next.preview=$native.preview;$next=Seal-Approval $next
    $script:serverState=$state;$dir=Join-Path $OutputDirectory "server-$state"
    Write-Json (Join-Path $dir 'last-verified-deployment.json') @{state='previous'}
    $last=(Get-FileHash (Join-Path $dir 'last-verified-deployment.json')).Hash
    $r=Submit-Deployment $next $next.approvalHash $dir 0
    Check ($r.state -eq $state) "Authoritative $state has distinct bounded behavior"
    Check ((Get-FileHash (Join-Path $dir 'last-verified-deployment.json')).Hash -eq $last) "$state does not replace last verified result"
}
Reset-Fixture
$script:collections["$($ids.Storage)/providers/Microsoft.Authorization/roleAssignments"]=@()
$grant=New-GrantPreview $config 'Storage';$script:mode='Lost'
$grantResult=Submit-Grant $grant $grant.approvalHash (Join-Path $OutputDirectory 'partial-grant')
Check ($grantResult.state -eq 'OutcomeUnknown' -and $writes.Count -eq 1) 'Individual lost grant is journaled'
$resources[$grant.request.resourceId]=Copy-Data $grant.request.body;$resources[$grant.request.resourceId].id=$grant.request.resourceId
$grantResult=Reconcile-Grant $grant (Join-Path $OutputDirectory 'partial-grant')
Check ($grantResult.state -eq 'Succeeded' -and $writes.Count -eq 1) 'Individual grant reconciles exact observed assignment, no batch replay'
$existingInput=Read-SetupInput (Join-Path $skill 'assets\input.existing.example.json')
$existing=$existingInput.config
$existingGraph=New-SetupPlan $existing $existingInput.options
Check ($existingInput.options.dnsZones['privatelink.blob.core.windows.net'].mode -ceq 'existing' -and $existingInput.options.privateEndpoints['pe-storage'].mode -ceq 'create') 'BYO example DNS zones read from the single input file'
foreach($name in @('Network','Storage','Account','Project')){Check (($existingGraph.nodes|Where-Object id -eq $name).kind -eq 'Reference') "BYO $name is read-only node"}
$savedIds=$ids;$ids=Get-SetupIds $existing;Reset-Fixture
$before=$writes.Count
foreach($name in @('Account','Project','Network','Storage')){$null=Confirm-Reference $existingGraph ($existingGraph.nodes|Where-Object id -eq $name)}
Check ($writes.Count -eq $before) 'Actual BYO reference execution makes zero PUT/PATCH'
$bad=Copy-Data $existing;$bad.foundryAccount.publicNetworkAccess='Disabled'
Reject {Assert-SetupConfig $bad} 'No BYO desired public-access override'
$bad=Copy-Data $existing;$bad.foundryProject.resourceId=$bad.foundryProject.resourceId -replace '/account-example/','/other/'
Reject {Assert-SetupConfig $bad} 'Paired-existing parent enforced'
$ids=$savedIds

foreach($absent in @('scripts\Assess-Readiness.ps1','scripts\Test-Evaluation.ps1','references\runtime-smoke.md')){Check (!(Test-Path (Join-Path $skill $absent))) "Removed customer path $absent"}
$customerText=@(Get-ChildItem (Join-Path $skill 'references') -File;Get-Item (Join-Path $skill 'SKILL.md'))|ForEach-Object{Get-Content $_.FullName -Raw}
Check (($customerText -join "`n") -notmatch 'https?://|339ad820|Vienna|CapabilityHostCache') 'Self-contained guide needs no external references/internal evidence'
$report=@{assertions=$script:checks;powerShellParsed=$parsed;bicepBuilds=$builds;toolchain=$tools.versions;packageHash=(Get-PackageHash);azureResourceCalls=0
    fixture='Sanitized Azure GET response shape, independently fixed type/value wrappers; not a new live receipt.'}
$proofResults=& (Join-Path $PSScriptRoot 'Test-TemplateAttribution.ps1') -OutputDirectory (Join-Path $OutputDirectory 'template-attribution')
$report.templateAttribution=$proofResults
$report.assertions+=$proofResults.assertions
Write-Json (Join-Path $OutputDirectory 'results.json') $report
"PASS: $($report.assertions) assertions; $parsed PS parses; ten Bicep builds; no Azure resource calls."
