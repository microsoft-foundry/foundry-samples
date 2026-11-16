# Access (RBAC) checks: configured role assignments for the identities evaluations use, plus which reads this run was denied.
# Role assignments are read with $filter=atScope(), so each read already includes assignments inherited from the
# resource group, subscription and management groups. Group membership is not resolved.

$script:AccessRoles = @{
    BlobFull     = @{ 'ba92f5b4-2d11-453d-a403-e96b0029c9fe' = 'Storage Blob Data Contributor'; 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b' = 'Storage Blob Data Owner' }
    BlobRead     = @{ '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1' = 'Storage Blob Data Reader' }
    TraceRead    = @{
        '73c42c96-874c-492b-b04d-ab87d138a893' = 'Log Analytics Reader'; '92aaf0da-9dab-42b6-94a3-d43ce8d16293' = 'Log Analytics Contributor'
        '43d0d8ad-25c7-4714-9337-8ba259a9fe05' = 'Monitoring Reader'; '749f88d5-cbae-40b8-bcfc-e573ddc772fa' = 'Monitoring Contributor'
        'acdd72a7-3385-48ef-bd42-f606fba81ae7' = 'Reader'; 'b24988ac-6180-42a0-ab88-20f7382dd24c' = 'Contributor'; '8e3cbf11-a1a9-4ecd-8cb0-5bba6d0a3cb0' = 'Owner'
    }
    FoundryData  = @{
        '53ca6127-db72-4b80-b1b0-d745d6d5456d' = 'Azure AI User'; '64702f94-c441-49e6-a78b-ef80e0188fee' = 'Azure AI Developer'
        'eadc314b-1a2d-4efa-be10-5d325db5065e' = 'Azure AI Project Manager'; 'a97b65f3-24c7-4388-baec-2e87135dc908' = 'Cognitive Services User'
    }
    ModelInvoke  = @{
        '53ca6127-db72-4b80-b1b0-d745d6d5456d' = 'Azure AI User'; '64702f94-c441-49e6-a78b-ef80e0188fee' = 'Azure AI Developer'
        'eadc314b-1a2d-4efa-be10-5d325db5065e' = 'Azure AI Project Manager'; 'a97b65f3-24c7-4388-baec-2e87135dc908' = 'Cognitive Services User'
        '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' = 'Cognitive Services OpenAI User'; 'a001fd3d-188f-4b5d-821b-7da978bf7442' = 'Cognitive Services OpenAI Contributor'
    }
}
$script:AccessEntraAuthTypes = @('AAD', 'ManagedIdentity', 'UserEntraToken', 'ServicePrincipal')

function Get-AccessRaPath { param([string]$Scope) "$Scope/providers/Microsoft.Authorization/roleAssignments" }

# Assignments at (or inherited by) $Scope that give one of $Roles: Direct (to the principal, no condition),
# Conditional (to the principal, with an ABAC condition) and Group (to any group; membership can't be read).
function Get-AccessGrant {
    param($Evidence, [string]$Scope, [string]$Principal, [hashtable]$Roles)
    $read = Get-Ev $Evidence (Get-AccessRaPath $Scope)
    $items = @($(if ($read.Ok) { @($read.Data | Where-Object { $_ -and $_.properties }) }))
    $withRole = @($items | Where-Object { $Roles.ContainsKey((Get-ArmName $_.properties.roleDefinitionId).ToLowerInvariant()) })
    $mine = @($withRole | Where-Object { $_.properties.principalId -eq $Principal })
    @{
        Read        = $read
        Direct      = @($mine | Where-Object { !$_.properties.conditionPresent })
        Conditional = @($mine | Where-Object { $_.properties.conditionPresent })
        Group       = @($withRole | Where-Object { $_.properties.principalType -eq 'Group' })
    }
}

function Get-AccessRoleNames {
    param($Assignments, [hashtable]$Roles)
    @($Assignments | ForEach-Object { $Roles[(Get-ArmName $_.properties.roleDefinitionId).ToLowerInvariant()] } | Where-Object { $_ } | Sort-Object -Unique)
}

# Shared decision for "does $Who have one of $Roles on $Scope".
function New-AccessRoleResult {
    param($Evidence, [string]$Id, [string]$Title, [string]$Path, [string]$Scope, [string]$Principal, [string]$Who,
        [hashtable]$Roles, [hashtable]$Partial = @{}, [string]$RoleHint, [string]$Likely, [string]$Severity = 'High')
    $label = Get-ArmName $Scope
    $grant = Get-AccessGrant $Evidence $Scope $Principal $Roles
    $read = $grant.Read
    $gap = New-ReadGap $read -Id $Id -Area Access -Title $Title -Layer Access -Path $Path -Resource $Scope -What "the role assignments on '$label'"
    if ($gap) { return $gap }
    $ref = @(Get-EvRef $read)
    $details = @{ principalId = $Principal; scope = $Scope }
    if ($read.NotFound) {
        return New-DiagResult -Id $Id -Area Access -Title $Title -Status CouldNotCheck -Gap KnownLimit -Path $Path -Layer Access -Resource $Scope `
            -Seen "Role assignments on '$label' could not be listed (the resource was not found)." -Needs "Fix the missing resource '$label' first." -Evidence $ref
    }
    if ($grant.Direct.Count) {
        $details.roles = Get-AccessRoleNames $grant.Direct $Roles
        return New-DiagResult -Id $Id -Area Access -Title $Title -Status OK -Path $Path -Layer Access -Resource $Scope `
            -Seen "$Who has $($details.roles -join ', ') on '$label'." -Evidence $ref -Details $details
    }
    if ($grant.Conditional.Count) {
        $details.roles = Get-AccessRoleNames $grant.Conditional $Roles
        return New-DiagResult -Id $Id -Area Access -Title $Title -Status Problem -Severity Medium -Path $Path -Layer Access -Resource $Scope `
            -Seen "$Who has $($details.roles -join ', ') on '$label' only with a condition, which may limit what it can access." -Owner AzureAdmin `
            -Action "Check that the condition on the $($details.roles -join ', ') assignment allows the data evaluations use, or add $RoleHint on '$label' without a condition." `
            -Evidence $ref -Details $details
    }
    $readOnly = @($(if ($Partial.Count) { (Get-AccessGrant $Evidence $Scope $Principal $Partial).Direct }))
    if ($readOnly.Count) {
        $details.roles = Get-AccessRoleNames $readOnly $Partial
        return New-DiagResult -Id $Id -Area Access -Title $Title -Status Problem -Severity Medium -Path $Path -Layer Access -Resource $Scope `
            -Seen "$Who has only $($details.roles -join ', ') on '$label', which can read but not write." -Owner AzureAdmin `
            -Action "Assign $RoleHint to $Who on '$label'." -Evidence $ref -Details $details
    }
    if ($grant.Group.Count) {
        $details.groupRoles = Get-AccessRoleNames $grant.Group $Roles
        return New-DiagResult -Id $Id -Area Access -Title $Title -Status CouldNotCheck -Gap KnownLimit -Path $Path -Layer Access -Resource $Scope `
            -Seen "$Who has no direct role on '$label'; a group has $($details.groupRoles -join ', ')." `
            -Needs "Confirm that $Who is a member of that group, or assign $RoleHint to it directly." -Evidence $ref -Details $details
    }
    New-DiagResult -Id $Id -Area Access -Title $Title -Status Problem -Severity $Severity -Path $Path -Layer Access -Resource $Scope `
        -Seen "$Who has no role on '$label' that grants this access." -Owner AzureAdmin -Likely $Likely `
        -Action "Assign $RoleHint to $Who on '$label'." -Evidence $ref -Details $details
}

function Test-DiagAccess {
    param($Evidence)
    $d = $Evidence.discovery
    $out = [Collections.Generic.List[object]]::new()
    $project = Get-Ev $Evidence $d.project
    $principal = $(if ($project.Ok) { $project.Data.identity.principalId })
    $mi = "The project managed identity"
    $projectName = Get-ArmName $d.project

    # access.projectStorage — project MI can read and write blobs.
    $storage = @($d.connections | Where-Object { $_ -and $_.path -eq 'Storage' })[0].resource
    if ($principal -and (Test-DiagPathUsed $Evidence 'Storage') -and $storage -match '(?i)/providers/Microsoft\.Storage/storageAccounts/[^/]+$') {
        $out.Add((New-AccessRoleResult $Evidence -Id access.projectStorage -Title 'Project identity storage data role' -Path Storage -Scope $storage `
            -Principal $principal -Who $mi -Roles $script:AccessRoles.BlobFull -Partial $script:AccessRoles.BlobRead -RoleHint 'Storage Blob Data Contributor' `
            -Likely 'Consistent with evaluations failing to read or write evaluation data (403 from storage).'))
    }

    # access.traceReader — project MI can query traces (on the component with resource permissions, or on the workspace).
    $ai = @($d.connections | Where-Object { $_ -and $_.path -eq 'MonitorQuery' })[0].resource
    if ($principal -and (Test-DiagPathUsed $Evidence 'MonitorQuery') -and $ai -match '(?i)/providers/Microsoft\.Insights/components/[^/]+$') {
        $out.Add((Get-AccessTraceResult $Evidence $ai $principal $mi))
    }

    # access.projectAssets — project MI data role on the project (datasets, evaluation results). Needs the project-scope read.
    $projectRa = Get-Ev $Evidence (Get-AccessRaPath $d.project)
    if ($principal -and $projectRa.Read) {
        $out.Add((New-AccessRoleResult $Evidence -Id access.projectAssets -Title 'Project identity project data role' -Path Foundry -Scope $d.project `
            -Principal $principal -Who $mi -Roles $script:AccessRoles.FoundryData -RoleHint 'Azure AI User' `
            -Likely 'Consistent with evaluations failing to read datasets or save results in the project.'))
    }

    # access.evaluationCaller — the identity that starts evaluations has a data role on the project (only when supplied).
    $caller = $d.evaluationCaller
    if ($caller) {
        $title = 'Evaluation caller project data role'
        $who = 'The evaluation caller'
        if ($projectRa.Read) {
            $out.Add((New-AccessRoleResult $Evidence -Id access.evaluationCaller -Title $title -Path Foundry -Scope $d.project `
                -Principal $caller -Who $who -Roles $script:AccessRoles.FoundryData -RoleHint 'Azure AI User' `
                -Likely 'Consistent with starting an evaluation failing with 403.'))
        }
        else {
            $result = New-AccessRoleResult $Evidence -Id access.evaluationCaller -Title $title -Path Foundry -Scope $d.account `
                -Principal $caller -Who $who -Roles $script:AccessRoles.FoundryData -RoleHint 'Azure AI User' `
                -Likely 'Consistent with starting an evaluation failing with 403.'
            if ($result.status -eq 'Problem' -and $result.severity -eq 'High') {
                # Only the account was read; the role may still be assigned on the project itself.
                $result = New-DiagResult -Id access.evaluationCaller -Area Access -Title $title -Status CouldNotCheck -Gap KnownLimit -Path Foundry -Layer Access -Resource $d.account `
                    -Seen "$who has no data role on account '$(Get-ArmName $d.account)'; role assignments on project '$projectName' were not read." `
                    -Needs "Check that $who has Azure AI User on project '$projectName'." -Evidence $result.evidence -Details $result.details
            }
            $out.Add($result)
        }
    }

    # access.modelIdentity — project MI can call the model account (Entra ID connections only).
    $model = @($d.connections | Where-Object { $_ -and $_.path -eq 'Models' })[0]
    if ($principal -and (Test-DiagPathUsed $Evidence 'Models') -and $model.resource -match '(?i)/providers/Microsoft\.CognitiveServices/accounts/[^/]+$') {
        $connRead = Get-Ev $Evidence "$($d.project)/connections"
        $auth = $(if ($connRead.Ok) { @($connRead.Data | Where-Object { $_ -and $_.name -eq $model.name })[0].properties.authType })
        $title = 'Project identity model role'
        if ($auth -and $auth -notin $script:AccessEntraAuthTypes) {
            $out.Add((New-DiagResult -Id access.modelIdentity -Area Access -Title $title -Status OK -Path Models -Layer Access -Resource $model.resource `
                -Seen "Connection '$($model.name)' uses $auth, so no role on '$(Get-ArmName $model.resource)' is needed." -Details @{ authType = $auth }))
        }
        else {
            $out.Add((New-AccessRoleResult $Evidence -Id access.modelIdentity -Title $title -Path Models -Scope $model.resource `
                -Principal $principal -Who $mi -Roles $script:AccessRoles.ModelInvoke -RoleHint 'Azure AI User' `
                -Likely 'Consistent with model calls from evaluations failing with 401 or 403.'))
        }
    }

    # access.runnerReads — which reads this run was denied, and what access would fix them.
    $out.Add((Get-AccessRunnerReadsResult $Evidence))

    , $out.ToArray()
}

function Get-AccessTraceResult {
    param($Evidence, [string]$AiId, [string]$Principal, [string]$Who)
    $title = 'Project identity trace read role'
    $P = 'MonitorQuery'
    $aiName = Get-ArmName $AiId
    $aiRead = Get-Ev $Evidence $AiId
    $lawId = $(if ($aiRead.Ok) { $aiRead.Data.properties.WorkspaceResourceId })
    if (!$lawId) { $lawId = @($Evidence.discovery.dependencies | Where-Object { $_ -and $_.kind -eq 'Workspace' })[0].resource }
    $law = Get-Ev $Evidence $lawId
    $roles = $script:AccessRoles.TraceRead
    $onAi = Get-AccessGrant $Evidence $AiId $Principal $roles
    $onLaw = $(if ($lawId) { Get-AccessGrant $Evidence $lawId $Principal $roles })
    $refs = @(@($onAi.Read, $onLaw.Read) | Where-Object { $_ -and $_.Read } | ForEach-Object { Get-EvRef $_ })
    $resourceMode = $(if ($law.Ok) { $law.Data.properties.features.enableLogAccessUsingOnlyResourcePermissions })
    $details = @{ principalId = $Principal; appInsights = $AiId; workspace = $lawId; resourcePermissions = $resourceMode }
    $lawGrant = @($onLaw.Direct) + @($onLaw.Conditional)
    $aiGrant = @($onAi.Direct) + @($onAi.Conditional)

    if ($lawGrant.Count) {
        $details.roles = Get-AccessRoleNames $lawGrant $roles
        return New-DiagResult -Id access.traceReader -Area Access -Title $title -Status OK -Path $P -Layer Access -Resource $lawId `
            -Seen "$Who has $($details.roles -join ', ') on workspace '$(Get-ArmName $lawId)'." -Evidence $refs -Details $details
    }
    if ($aiGrant.Count) {
        $details.roles = Get-AccessRoleNames $aiGrant $roles
        if ($resourceMode -eq $true -or !$lawId) {
            return New-DiagResult -Id access.traceReader -Area Access -Title $title -Status OK -Path $P -Layer Access -Resource $AiId `
                -Seen "$Who has $($details.roles -join ', ') on Application Insights '$aiName'." -Evidence $refs -Details $details
        }
        if ($resourceMode -eq $false) {
            return New-DiagResult -Id access.traceReader -Area Access -Title $title -Status Problem -Severity High -Path $P -Layer Access -Resource $AiId `
                -Seen "$Who has $($details.roles -join ', ') only on Application Insights '$aiName', but workspace '$(Get-ArmName $lawId)' requires workspace permissions." `
                -Likely 'Consistent with evaluation trace queries being rejected (403).' -Owner AzureAdmin `
                -Action "Assign Log Analytics Reader to $Who on workspace '$(Get-ArmName $lawId)', or set the workspace access control mode to use resource or workspace permissions." `
                -Evidence ($refs + @($(if ($law.Read) { Get-EvRef $law }))) -Details $details
        }
        if ($law.NotFound) {
            return New-DiagResult -Id access.traceReader -Area Access -Title $title -Status CouldNotCheck -Gap KnownLimit -Path $P -Layer Access -Resource $AiId `
                -Seen "$Who has $($details.roles -join ', ') on Application Insights '$aiName', but workspace '$(Get-ArmName $lawId)' was not found." `
                -Needs "Fix the missing workspace '$(Get-ArmName $lawId)' first." -Evidence $refs -Details $details
        }
        return New-DiagResult -Id access.traceReader -Area Access -Title $title -Status CouldNotCheck -Gap Blocking -Path $P -Layer Access -Resource $AiId `
            -Seen "$Who has $($details.roles -join ', ') on Application Insights '$aiName', but the workspace access control mode could not be read." `
            -Needs "Read access (Reader) on workspace '$(Get-ArmName $lawId)'." -Evidence $refs -Details $details
    }
    foreach ($pair in @(@{ Read = $onAi.Read; Scope = $AiId }, @{ Read = $onLaw.Read; Scope = $lawId })) {
        if (!$pair.Scope -or !$pair.Read) { continue }
        $gap = New-ReadGap $pair.Read -Id access.traceReader -Area Access -Title $title -Layer Access -Path $P -Resource $AiId -What "the role assignments on '$(Get-ArmName $pair.Scope)'"
        if ($gap) { return $gap }
    }
    $groups = @($onAi.Group) + @($onLaw.Group)
    if ($groups.Count) {
        $details.groupRoles = Get-AccessRoleNames $groups $roles
        return New-DiagResult -Id access.traceReader -Area Access -Title $title -Status CouldNotCheck -Gap KnownLimit -Path $P -Layer Access -Resource $AiId `
            -Seen "$Who has no direct trace read role; a group has $($details.groupRoles -join ', ')." `
            -Needs "Confirm that $Who is a member of that group, or assign Log Analytics Reader to it directly." -Evidence $refs -Details $details
    }
    New-DiagResult -Id access.traceReader -Area Access -Title $title -Status Problem -Severity High -Path $P -Layer Access -Resource $AiId `
        -Seen "$Who has no role that can read traces on Application Insights '$aiName' or its workspace." -Owner AzureAdmin `
        -Likely 'Consistent with evaluation trace queries being rejected (403).' `
        -Action "Assign Log Analytics Reader to $Who on Application Insights '$aiName' (or on its workspace)." -Evidence $refs -Details $details
}

function Get-AccessRunnerPaths {
    # Only the machine's own VM and NIC: its subnet, NSG and route table may be shared with the agent.
    param($Evidence)
    $runner = $Evidence.discovery.runner
    $vmId = $(if ($runner.vm) { $runner.vm } else { $Evidence.run.runner.azureVmResourceId })
    @(@($vmId, $runner.nic) | Where-Object { $_ })
}

function Get-AccessRunnerReadsResult {
    param($Evidence)
    $title = 'Diagnostic read access'
    # Reads about this machine are runner.location's concern; a managed machine's VM is often unreadable by design.
    $runnerPaths = Get-AccessRunnerPaths $Evidence
    $denied = @($Evidence.requests | Where-Object {
            $req = $_
            $req -and $req.errorKind -in @('Forbidden', 'Unauthorized') -and !@($runnerPaths | Where-Object { Test-SameArmId $_ $req.path }).Count
        })
    if (!$denied.Count) {
        return New-DiagResult -Id access.runnerReads -Area Access -Title $title -Status OK -Layer Access `
            -Seen "All $(@($Evidence.requests).Count) Azure reads were allowed."
    }
    $forbidden = @($denied | Where-Object { $_.errorKind -eq 'Forbidden' })
    $scopes = @($forbidden | ForEach-Object { Get-ArmScopeName $_.path } | Sort-Object -Unique)
    $names = @($denied | ForEach-Object {
            $name = Get-ArmName $_.path
            if ($_.path -match '(?i)/providers/Microsoft\.Authorization/roleAssignments$') { "role assignments on '$(Get-ArmName (Get-ArmParent $_.path 2))'" } else { "'$name'" }
        } | Sort-Object -Unique)
    $needs = @()
    if ($scopes.Count) { $needs += "Reader on $($scopes -join ', ')." }
    if (@($denied | Where-Object { $_.errorKind -eq 'Unauthorized' }).Count) { $needs += 'A valid sign-in for every subscription involved.' }
    New-DiagResult -Id access.runnerReads -Area Access -Title $title -Status CouldNotCheck -Gap Blocking -Layer Access `
        -Seen "This run couldn't read $($denied.Count) item(s): $($names -join ', ')." -Needs ($needs -join ' ') `
        -Evidence @($denied | ForEach-Object { "request:$($_.key)" }) -Details @{ denied = @($denied | ForEach-Object { @{ path = $_.path; errorKind = $_.errorKind } }); scopes = $scopes }
}
