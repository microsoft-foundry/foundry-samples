. (Join-Path $PSScriptRoot 'SetupPlan.ps1')
. (Join-Path $PSScriptRoot 'Deployment.ps1')
. (Join-Path $PSScriptRoot 'Manage-Foundry.ps1')
. (Join-Path $PSScriptRoot 'Set-ProjectAccess.ps1')

function Test-ScopeConflict([string[]]$Left,[string[]]$Right) {
    foreach ($a in $Left) { foreach ($b in $Right) {
        if ($a -ieq $b -or $a.StartsWith("$b/",[StringComparison]::OrdinalIgnoreCase) -or $b.StartsWith("$a/",[StringComparison]::OrdinalIgnoreCase)) { return $true }
    } }
    return $false
}
function Confirm-Reference($Graph,$Node) {
    $ids = Get-SetupIds $Graph.config
    if ($Node.id -in @('Account','Project')) { $null = Get-FoundryState $Graph.config }
    elseif ($Node.id -eq 'Network') {
        $state = Get-NetworkObservation $Graph.config; $state.resources[$ids.Storage] = 'Absent'
        foreach ($id in @($ids.Vnet,$ids.AgentSubnet,$ids.PeSubnet)) { if ($state.resources[$id] -eq 'Absent') { throw 'Supplied network is missing.' } }
        Assert-ObservedDependencies $Graph.config $state
    } elseif ($Node.id -eq 'Storage') {
        $storage = Get-SetupResource $ids.Storage
        if ($storage.kind -cne 'StorageV2' -or $storage.properties.provisioningState -ne 'Succeeded' -or !$storage.properties.primaryEndpoints.blob) { throw 'Supplied Storage is incompatible/not Succeeded.' }
    } elseif ($Node.id -eq 'Monitoring') {
        $component = Get-SetupResource $ids.Insights
        $null = Get-SetupResource (Assert-ResourceId $component.properties.WorkspaceResourceId 'Microsoft.OperationalInsights/workspaces')
    } else { throw 'Unsupported reference node.' }
    @{ state = 'Succeeded'; operation = 'ReferenceOnly'; node = $Node.id; writes = 0 }
}
function Assert-NodeApproval($Graph,$Node,$Plan) {
    $ids = Get-SetupIds $Graph.config
    if ((Get-Digest $Plan.config) -cne (Get-Digest $Graph.config)) { throw 'Node/config binding mismatch.' }
    switch ($Node.kind) {
        'ResourceGroup' {
            if ($Plan.kind -cne 'ResourceGroup' -or $Plan.request.resourceId -ine $ids.ResourceGroup) { throw 'ResourceGroup node requires its exact RG operation/target.' }
        }
        { $_ -in @('Deployment','Connections') } {
            if ($Plan.kind -cne 'Deployment' -or $Plan.request.asset -cne $Node.asset) { throw 'Node/asset binding mismatch.' }
            $scope = if ($Node.asset -eq 'connections' -and $Graph.config.foundryAccount.mode -eq 'existing') {
                $ids.Account -replace '/providers/Microsoft.CognitiveServices/accounts/[^/]+$',''
            } else { $ids.ResourceGroup }
            if ($Plan.request.scope -ine $scope) { throw 'Node/deployment scope mismatch.' }
            $expected = Resolve-NodeValues $Graph $Node
            foreach ($key in $expected.Keys) {
                if (!$Plan.request.parameters.Contains($key) -or (Get-Digest $Plan.request.parameters[$key].value) -cne (Get-Digest $expected[$key])) { throw "Node parameter target/operation mismatch: $key." }
            }
        }
        'Grant' {
            if ($Plan.kind -cne 'Grant') { throw 'Grant node binding mismatch.' }
            $target = $Node.values.target
            $scope = switch ($target) {
                'Account' { $ids.Account }; 'Storage' { $ids.Storage }; 'Insights' { $ids.Insights }
                'Workspace' { if (!$ids.Insights) { throw 'Monitoring absent.' }; (Get-SetupResource $ids.Insights).properties.WorkspaceResourceId }
            }
            $role = switch ($target) { 'Account' { '53ca6127-db72-4b80-b1b0-d745d6d5456d' }; 'Storage' { 'ba92f5b4-2d11-453d-a403-e96b0029c9fe' }; default { '73c42c96-874c-492b-b04d-ab87d138a893' } }
            if (!$scope -or $Plan.request.scope -ine $scope -or
                $Plan.request.resourceId -inotlike "$scope/providers/Microsoft.Authorization/roleAssignments/*" -or
                $Plan.request.body.properties.roleDefinitionId -ine "/subscriptions/$($scope.Split('/')[2])/providers/Microsoft.Authorization/roleDefinitions/$role") { throw 'Grant node/role/target binding mismatch.' }
        }
        'Foundry' {
            $target = if ($Node.values.operation -eq 'Injection') { $ids.Account } elseif ($Node.values.operation -eq 'AccountHost') {
                "$($ids.Account)/capabilityHosts/agents"
            } else { "$($ids.Project)/capabilityHosts/agents" }
            if ($Plan.kind -cne $Node.values.operation -or $Plan.request.resourceId -ine $target) { throw 'Foundry node/operation/target binding mismatch.' }
        }
        default { throw 'Unsupported approval node kind.' }
    }
}
function Assert-NoUnresolvedAttempt([string]$Directory) {
    if (!(Test-Path -LiteralPath $Directory)) { return }
    foreach ($file in Get-ChildItem -LiteralPath $Directory -Filter '*.attempt.json' -File) {
        $receipt = Read-Json $file.FullName
        if ($receipt.state -in @('Running','SubmissionAttempted','OutcomeUnknown')) {
            $error = [InvalidOperationException]::new("Unresolved attempt $($receipt.operationId): reconcile its original plan read-only before a fresh same-node preview. No write or deployment polling occurred.")
            $error.Data['priorState'] = if ($receipt.state -eq 'SubmissionAttempted') { 'OutcomeUnknown' } else { $receipt.state }
            $error.Data['originalOperationId'] = $receipt.operationId
            $error.Data['originalAttemptPath'] = $file.FullName
            $error.Data['originalPreviewPath'] = Join-Path $Directory "$($receipt.operationId).preview.json"
            throw $error
        }
    }
}
function Invoke-SetupNode($Graph,$Node,[string]$Mode,[string]$Directory,$Approval,[bool]$AcknowledgeAccountWideImpact = $false) {
    $clock = Start-Phase 'NodeWall'
    $record = @{ node = $Node.id; mode = $Mode; state = 'NotSubmitted'; timings = @(); nextAction = 'FreshScopedPreview' }
    $plan = $null; $attemptPath = ''
    $script:SetupStateDirectory = $Directory
    try {
        $tools = Get-SetupToolchain
        $record.toolchain = @{ powerShell = $PSVersionTable.PSVersion.ToString(); python = $tools.versions.python
            azureCli = $tools.versions.azureCli; bicep = $tools.bicepVersion }
        Assert-SetupContext $Graph.config
        if ($Node.kind -eq 'Reference') {
            $record.result = Confirm-Reference $Graph $Node; $record.state = 'Succeeded'; $record.nextAction = 'None'
        } elseif ($Mode -eq 'Preview') {
            Assert-NoUnresolvedAttempt $Directory
            $preparation = Start-Phase 'ParameterPreparation'
            $values = Resolve-NodeValues $Graph $Node
            $record.timings += Stop-Phase $preparation
            $plan = switch ($Node.kind) {
                'ResourceGroup' { New-GroupPreview $Graph.config }
                { $_ -in @('Deployment','Connections') } { New-DeploymentPreview $Graph.config $Node.asset $values }
                'Grant' { New-GrantPreview $Graph.config $values.target }
                'Foundry' { New-FoundryPreview $Graph.config $values.operation }
            }
            $path = Join-Path $Directory "$($plan.operationId).preview.json"
            Write-Json $path $plan
            $record.state = 'PreviewReady'; $record.previewPath = [IO.Path]::GetFullPath($path)
            $record.approvalHash = $plan.approvalHash; $record.nextAction = 'ReviewExactScopeThenApply'
        } else {
            if (!$Approval -or !$Approval.Contains('planPath')) { throw 'An exact node planPath is required; no automatic approval or cross-step replay.' }
            $plan = Read-Json $Approval.planPath
            Assert-NodeApproval $Graph $Node $plan
            $attemptPath = Join-Path $Directory "$($plan.operationId).attempt.json"
            $remaining = [Math]::Max(0,$Node.budgetSeconds - [int]((Stop-Phase $clock).elapsedMs / 1000))
            if ($remaining -eq 0) { throw 'Preparation budget exhausted before submission.' }
            $statusBudget = [Math]::Min($remaining,$tools.manifest.budgets.operationSeconds)
            if ($Mode -eq 'Apply') {
                if (!$Approval.Contains('approvalHash')) { throw 'Exact approvalHash is required, never approved:true.' }
                $result = switch ($plan.kind) {
                    'Deployment' { Submit-Deployment $plan $Approval.approvalHash $Directory $statusBudget }
                    'ResourceGroup' { Submit-Group $plan $Approval.approvalHash $Directory }
                    'Grant' { Submit-Grant $plan $Approval.approvalHash $Directory }
                    default { Submit-Foundry $plan $Approval.approvalHash $Directory -AcknowledgeAccountWideImpact:$AcknowledgeAccountWideImpact -TimeoutSeconds $statusBudget }
                }
            } else {
                $result = switch ($plan.kind) {
                    'Deployment' { Reconcile-Deployment $plan $Directory }
                    'ResourceGroup' { Reconcile-Group $plan $Directory }
                    'Grant' { Reconcile-Grant $plan $Directory }
                    default { Reconcile-Foundry $plan $Directory }
                }
            }
            $record.result = $result; $record.state = $result.state
            $record.nextAction = switch ($result.state) {
                'NotSubmitted' { 'FreshScopedPreview' }; 'Succeeded' { 'None' }; 'Failed' { 'InspectConfirmedFailure' }
                'Running' { 'BoundedReadOnlyReconcile' }; default { 'ReadOnlyReconcileNoResubmit' }
            }
        }
    } catch {
        $record.error = $_.Exception.Message
        if ($_.Exception.Data.Contains('priorState')) {
            $record.state = $_.Exception.Data['priorState']
            $record.originalOperationId = $_.Exception.Data['originalOperationId']
            $record.originalAttemptPath = $_.Exception.Data['originalAttemptPath']
            $record.originalPreviewPath = $_.Exception.Data['originalPreviewPath']
            $record.nextAction = 'ReadOnlyReconcileOriginalAttempt'
        } elseif ($attemptPath -and (Test-Path -LiteralPath $attemptPath)) {
            $attempt = Read-Json $attemptPath; $record.state = $attempt.state; $record.result = $attempt
            $record.nextAction = if ($attempt.state -eq 'NotSubmitted') { 'FreshScopedPreview' } else { 'InspectReceiptNoResubmit' }
        }
    }
    $record.timings += Stop-Phase $clock
    Write-Json (Join-Path $Directory 'latest.json') $record
    return $record
}
function Invoke-SetupSelection {
    param($Graph,[string[]]$Selected,[ValidateSet('Preview','Apply','Reconcile')][string]$Mode,[string]$Directory,
        $Approvals = @{},[ValidateRange(1,3)][int]$Concurrency = 3,[bool]$AcknowledgeAccountWideImpact = $false,
        [string]$WorkerScript = '')
    Assert-SetupPlan $Graph
    $selectedIds = @($Selected | ForEach-Object { $_ -split ',' } | Sort-Object -Unique)
    if (!$selectedIds.Count) { throw 'Select explicit nodes/waves; there is no implicit run-all.' }
    $nodes = @{}
    foreach ($id in $selectedIds) {
        $matches = @($Graph.nodes | Where-Object id -CEQ $id)
        if ($matches.Count -ne 1) { throw "Unknown/duplicate selected node: $id." }
        $nodes[$id] = $matches[0]
    }
    if (!$WorkerScript) {
        $WorkerScript = 'param($Root,$Graph,$Node,$Mode,$Directory,$Approval,$Ack); . (Join-Path $Root ''SetupEngine.ps1''); Invoke-SetupNode $Graph $Node $Mode $Directory $Approval $Ack'
    }
    $pool = [RunspaceFactory]::CreateRunspacePool(1,$Concurrency)
    $pool.Open()
    $active = @{}; $results = @{}; $pending = [Collections.Generic.List[string]]::new()
    foreach ($id in $selectedIds) { $pending.Add($id) }
    $wall = Start-Phase 'SelectionWall'
    try {
        while ($pending.Count -or $active.Count) {
            $completedAny = $false
            foreach ($id in @($pending.ToArray())) {
                $dependencies = @($nodes[$id].dependsOn | Where-Object { $nodes.ContainsKey($_) })
                if (@($dependencies | Where-Object { $results.ContainsKey($_) -and $results[$_].state -notin @('Succeeded','PreviewReady') }).Count) {
                    $results[$id] = @{ node = $id; state = 'Blocked'; nextAction = 'ResolveMaterialPrerequisite'; writes = 0 }
                    $null = $pending.Remove($id); continue
                }
                if (@($dependencies | Where-Object { !$results.ContainsKey($_) }).Count) { continue }
                if ($active.Count -ge $Concurrency) { break }
                $conflict = $false
                if ($Mode -eq 'Apply') {
                    foreach ($other in $active.Keys) { if (Test-ScopeConflict $nodes[$id].writeScopes $nodes[$other].writeScopes) { $conflict = $true; break } }
                }
                if ($conflict) { continue }
                $ps = [PowerShell]::Create(); $ps.RunspacePool = $pool
                $approval = if ($Approvals.Contains($id)) { $Approvals[$id] } else { @{} }
                $null = $ps.AddScript($WorkerScript).AddArgument($PSScriptRoot).AddArgument((Copy-Data $Graph)).AddArgument((Copy-Data $nodes[$id])).
                    AddArgument($Mode).AddArgument((Join-Path $Directory $id)).AddArgument((Copy-Data $approval)).AddArgument($AcknowledgeAccountWideImpact)
                $active[$id] = @{ ps = $ps; handle = $ps.BeginInvoke(); timer = [Diagnostics.Stopwatch]::StartNew(); stop = $null }
                $null = $pending.Remove($id)
            }
            foreach ($id in @($active.Keys)) {
                $job = $active[$id]
                if (!$job.handle.IsCompleted -and $job.timer.Elapsed.TotalSeconds -gt $nodes[$id].budgetSeconds -and !$job.stop) {
                    $job.stop = $job.ps.BeginStop($null,$null)
                }
                if (!$job.handle.IsCompleted) { continue }
                $completedAny = $true
                try {
                    $output = @($job.ps.EndInvoke($job.handle))
                    if ($job.ps.HadErrors -or $output.Count -ne 1) { throw 'Worker did not return one safe node result; inspect its per-operation receipts.' }
                    $results[$id] = $output[0]
                } catch {
                    $attempted = @(Get-ChildItem (Join-Path $Directory $id) -Filter '*.attempt.json' -ErrorAction SilentlyContinue |
                        ForEach-Object { Read-Json $_.FullName } | Where-Object { $_.Contains('submissionStartedAt') })
                    $results[$id] = @{ node = $id; state = $(if ($attempted.Count) { 'OutcomeUnknown' } else { 'NotSubmitted' })
                        error = $_.Exception.Message; nextAction = $(if ($attempted.Count) { 'InspectReceiptsNoResubmit' } else { 'FreshScopedPreview' }) }
                } finally { $job.ps.Dispose(); $active.Remove($id) }
            }
            if ($pending.Count -and !$active.Count -and !$completedAny) { throw 'Selected dependency graph cannot progress; no retries were submitted.' }
            if ($active.Count) { Start-Sleep -Milliseconds 25 }
        }
    } finally {
        foreach ($job in $active.Values) { $job.ps.Stop(); $job.ps.Dispose() }
        $pool.Close(); $pool.Dispose()
    }
    $result = @{ planHash = $Graph.planHash; mode = $Mode; concurrency = $Concurrency; timing = (Stop-Phase $wall)
        nodes = $results; meaning = 'Per-node clocks may overlap; SelectionWall is wall time, not the sum of Azure deployment durations.' }
    Write-Json (Join-Path $Directory "$Mode-results.json") $result
    return $result
}

function Get-PlanSummary($Graph) {
    $nodes = foreach ($node in $Graph.nodes) {
        $action = if ($node.kind -eq 'Reference') { 'ReuseSupplied' } elseif ($node.id -eq 'Injection') { 'AccountWideNetworkInjection' } else { 'CreateOrVerify' }
        @{ node = $node.id; action = $action; dependsOn = @($node.dependsOn); writeScopes = @($node.writeScopes) }
    }
    @{ planHash = $Graph.planHash; nodeCount = @($Graph.nodes).Count; nodes = @($nodes)
        approve = "Setup.ps1 -Action Run -GraphPath <plan.json> -StateDirectory <dir> -ApprovePlan $($Graph.planHash) [-AcknowledgeAccountWideImpact]" }
}
function Invoke-SetupRun {
    param($Graph,[string]$Directory,[string]$ApprovePlan,[bool]$AcknowledgeAccountWideImpact = $false,
        [ValidateRange(1,3)][int]$Concurrency = 3,[string]$WorkerScript = '')
    Assert-SetupPlan $Graph
    if ($ApprovePlan -cne $Graph.planHash) { throw 'ApprovePlan must equal the reviewed plan planHash.' }
    $null = New-Item -ItemType Directory -Path $Directory -Force
    $runPath = Join-Path $Directory 'run.json'
    $run = if (Test-Path -LiteralPath $runPath) { Read-Json $runPath } else { @{ planHash = $Graph.planHash; nodes = @{}; history = @() } }
    if ($run.planHash -cne $Graph.planHash) { throw 'This state directory belongs to a different plan; use a new directory.' }
    $unresolved = @('Running','SubmissionAttempted','OutcomeUnknown')
    $status = 'InProgress'; $reason = ''; $freshRetried = @{}
    function Save-Run { $run.status = $status; $run.reason = $reason; $run.updatedAt = [DateTimeOffset]::UtcNow.ToString('o'); Write-Json $runPath $run }
    function Set-NodeResult([string]$Id,$Result,[string]$Step) {
        $entry = if ($run.nodes.Contains($Id)) { $run.nodes[$Id] } else { @{} }
        $entry.state = $Result['state']; $entry.nextAction = $Result['nextAction']; $entry.step = $Step
        foreach ($key in @('previewPath','approvalHash','error','originalPreviewPath')) { if ($Result.Contains($key)) { $entry[$key] = $Result[$key] } }
        $run.nodes[$Id] = $entry
        $run.history += @{ node = $Id; step = $Step; state = $Result['state']; at = [DateTimeOffset]::UtcNow.ToString('o') }
    }
    try {
        # Resume: one read-only reconcile of any attempt whose outcome was not confirmed.
        $pendingReconcile = @{}
        foreach ($id in @($run.nodes.Keys)) {
            $entry = $run.nodes[$id]
            if ($entry.state -in $unresolved) {
                $path = if ($entry.Contains('originalPreviewPath')) { $entry['originalPreviewPath'] } else { $entry['previewPath'] }
                if ($path) { $pendingReconcile[$id] = @{ planPath = $path } }
            }
        }
        if ($pendingReconcile.Count) {
            $reconciled = Invoke-SetupSelection $Graph @($pendingReconcile.Keys) 'Reconcile' $Directory $pendingReconcile $Concurrency $AcknowledgeAccountWideImpact $WorkerScript
            foreach ($id in $reconciled.nodes.Keys) { Set-NodeResult $id $reconciled.nodes[$id] 'Reconcile' }
        }
        # Resume: a deployment that Azure confirmed as Failed gets one fresh, fully guarded preview per rerun.
        foreach ($node in @($Graph.nodes | Where-Object { $_.kind -in @('Deployment','Connections') })) {
            if ($run.nodes.Contains($node.id) -and $run.nodes[$node.id].state -eq 'Failed') {
                Set-NodeResult $node.id @{ state = 'NotSubmitted'; nextAction = 'FreshScopedPreview' } 'RetryAfterConfirmedFailure'
            }
        }
        while ($true) {
            $states = @{}; foreach ($id in $run.nodes.Keys) { $states[$id] = $run.nodes[$id].state }
            $stuck = @($Graph.nodes | Where-Object { $states[$_.id] -and $states[$_.id] -notin @('Succeeded','NotSubmitted','PreviewReady') })
            if ($stuck.Count) {
                $status = 'Stopped'; $reason = "Node(s) need attention: $((@($stuck.id) | Sort-Object) -join ', '). Rerun the same command to reconcile unconfirmed outcomes and retry Failed deployments once after you address the cause in each node's error."
                break
            }
            $remaining = @($Graph.nodes | Where-Object { $states[$_.id] -ne 'Succeeded' })
            if (!$remaining.Count) { $status = 'Completed'; break }
            $ready = @($remaining | Where-Object { !@($_.dependsOn | Where-Object { $states[$_] -ne 'Succeeded' }).Count })
            if (!$AcknowledgeAccountWideImpact) {
                $held = @($ready | Where-Object { $_.kind -eq 'Foundry' -and $_.values.operation -eq 'Injection' })
                $ready = @($ready | Where-Object { !($_.kind -eq 'Foundry' -and $_.values.operation -eq 'Injection') })
                if ($held.Count -and !$ready.Count) {
                    $status = 'AwaitingAccountWideConfirmation'
                    $reason = 'Network injection changes the whole Foundry account. Review Injection, then rerun with -AcknowledgeAccountWideImpact.'
                    break
                }
            }
            if (!$ready.Count) { throw 'Plan cannot progress; no further writes were submitted.' }
            $wave = @($ready.id)
            $previews = Invoke-SetupSelection $Graph $wave 'Preview' $Directory @{} $Concurrency $AcknowledgeAccountWideImpact $WorkerScript
            $approvals = @{}; $blocked = $false; $reconcile = @{}
            foreach ($id in $wave) {
                $result = $previews.nodes[$id]
                Set-NodeResult $id $result 'Preview'
                if ($result.state -eq 'PreviewReady') { $approvals[$id] = @{ planPath = $result.previewPath; approvalHash = $result.approvalHash } }
                elseif ($result.state -in $unresolved -and $result.Contains('originalPreviewPath')) { $reconcile[$id] = @{ planPath = $result.originalPreviewPath } }
                elseif ($result.state -ne 'Succeeded') { $blocked = $true }
            }
            if ($reconcile.Count) {
                $reconciled = Invoke-SetupSelection $Graph @($reconcile.Keys) 'Reconcile' $Directory $reconcile $Concurrency $AcknowledgeAccountWideImpact $WorkerScript
                foreach ($id in $reconciled.nodes.Keys) { Set-NodeResult $id $reconciled.nodes[$id] 'Reconcile' }
            }
            if ($blocked) {
                $status = 'Stopped'; $reason = 'A preview was rejected by a safety check; nothing was applied for that node. See its error.'
                foreach ($id in $approvals.Keys) { $run.nodes[$id].state = 'NotSubmitted' }
                break
            }
            if ($approvals.Count) {
                $applied = Invoke-SetupSelection $Graph @($approvals.Keys) 'Apply' $Directory $approvals $Concurrency $AcknowledgeAccountWideImpact $WorkerScript
                foreach ($id in $applied.nodes.Keys) { Set-NodeResult $id $applied.nodes[$id] 'Apply' }
                $notDone = @($applied.nodes.Keys | Where-Object { $applied.nodes[$_].state -ne 'Succeeded' } | Sort-Object)
                # A sibling in the same wave can change state another node's preview was bound to.
                # Such a refusal wrote nothing, so allow exactly one fresh preview per node per run.
                $refreshable = @($notDone | Where-Object { $applied.nodes[$_].state -eq 'NotSubmitted' -and
                    $applied.nodes[$_]['nextAction'] -eq 'FreshScopedPreview' -and !$freshRetried.Contains($_) })
                if ($notDone.Count -and $refreshable.Count -eq $notDone.Count) {
                    foreach ($id in $refreshable) { $freshRetried[$id] = $true }
                    Save-Run; continue
                }
                if ($notDone.Count) {
                    $status = 'Stopped'; $reason = "Apply did not complete for: $($notDone -join ', '). Rerun the same command to resume; it never resubmits an unconfirmed attempt, and it will retry Failed deployments once after you address the cause in each node's error."
                    break
                }
            }
            Save-Run
        }
    } catch {
        $status = 'Stopped'; $reason = $_.Exception.Message
    }
    Save-Run
    $summary = [ordered]@{}; foreach ($id in ($run.nodes.Keys | Sort-Object)) { $summary[$id] = $run.nodes[$id].state }
    @{ planHash = $Graph.planHash; status = $status; reason = $reason; runPath = [IO.Path]::GetFullPath($runPath); nodes = $summary }
}
