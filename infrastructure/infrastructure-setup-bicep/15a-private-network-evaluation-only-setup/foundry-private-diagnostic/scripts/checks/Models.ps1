# Model checks: the model connection, its target account and deployments. Only when the Models path is used.

$script:ModelEntraAuthTypes = @('AAD', 'ManagedIdentity', 'UserEntraToken', 'ServicePrincipal')

function Test-DiagModels {
    param($Evidence)
    if (!(Test-DiagPathUsed $Evidence 'Models')) { return , @() }
    $out = [Collections.Generic.List[object]]::new()
    $P = 'Models'
    $conn = @($Evidence.discovery.connections | Where-Object { $_ -and $_.path -eq $P })[0]
    $id = $conn.resource

    # model.connection — a model connection with a target resource.
    $title = 'Model connection'
    if (!$conn -or !$id) {
        $out.Add((New-DiagResult -Id model.connection -Area Models -Title $title -Status Problem -Severity High -Path $P -Layer Config -Resource $Evidence.discovery.project `
            -Seen $(if ($conn) { "Model connection '$($conn.name)' has no target resource ID." } else { 'The project uses models but has no model connection.' }) -Owner Customer `
            -Action 'Add (or fix) the project model connection so it references the Azure OpenAI or AI Services account by its resource ID.' -Details @{ connection = $conn.name }))
        return , $out.ToArray()
    }
    $name = Get-ArmName $id
    $out.Add((New-DiagResult -Id model.connection -Area Models -Title $title -Status OK -Path $P -Layer Config -Resource $id `
        -Seen "Model connection '$($conn.name)' points at '$name'." -Details @{ connection = $conn.name; category = $conn.category }))

    # model.target — the target exists and is a Cognitive Services account.
    $title = 'Model target account'
    $target = Get-Ev $Evidence $id
    if ($id -notmatch '(?i)/providers/Microsoft\.CognitiveServices/accounts/[^/]+$') {
        $out.Add((New-DiagResult -Id model.target -Area Models -Title $title -Status Problem -Severity High -Path $P -Layer Config -Resource $id `
            -Seen "Model connection '$($conn.name)' points at '$name', which is not an Azure OpenAI or AI Services account." -Owner Customer `
            -Action "Point connection '$($conn.name)' at the resource ID of an Azure OpenAI or AI Services account." -Details @{ resource = $id }))
        return , $out.ToArray()
    }
    $gap = New-ReadGap $target -Id model.target -Area Models -Title $title -Layer Config -Path $P -Resource $id -What "model account '$name'"
    if ($gap) { $out.Add($gap) }
    elseif ($target.NotFound) {
        $out.Add((New-DiagResult -Id model.target -Area Models -Title $title -Status Problem -Severity High -Path $P -Layer Config -Resource $id `
            -Seen "Model account '$name' was not found." -Owner Customer `
            -Action "Recreate model account '$name' or point connection '$($conn.name)' at an existing account." -Evidence @(Get-EvRef $target)))
        return , $out.ToArray()
    }
    elseif ($target.Data.properties.provisioningState -and $target.Data.properties.provisioningState -ne 'Succeeded') {
        $state = $target.Data.properties.provisioningState
        $out.Add((New-DiagResult -Id model.target -Area Models -Title $title -Status Problem -Severity High -Path $P -Layer Config -Resource $id `
            -Seen "Model account '$name' is in state '$state'." -Owner ResourceOwner `
            -Action "Wait for model account '$name' to finish provisioning, or check its deployment error." -Evidence @(Get-EvRef $target) -Details @{ provisioningState = $state }))
    }
    else {
        $out.Add((New-DiagResult -Id model.target -Area Models -Title $title -Status OK -Path $P -Layer Config -Resource $id `
            -Seen "Model account '$name' exists." -Evidence @(Get-EvRef $target)))
    }

    # model.deployment — at least one provisioned deployment.
    $title = 'Model deployments'
    $deployments = Get-Ev $Evidence "$id/deployments"
    $gap = New-ReadGap $deployments -Id model.deployment -Area Models -Title $title -Layer Config -Path $P -Resource $id -What "the deployments of model account '$name'"
    if ($gap) { $out.Add($gap) }
    else {
        $all = @($(if ($deployments.Ok) { @($deployments.Data | Where-Object { $_ }) }))
        $ready = @($all | Where-Object { $_.properties.provisioningState -eq 'Succeeded' })
        $summary = @($all | ForEach-Object { @{ name = $_.name; state = $_.properties.provisioningState; model = $_.properties.model.name } })
        if (!$ready.Count) {
            $out.Add((New-DiagResult -Id model.deployment -Area Models -Title $title -Status Problem -Severity High -Path $P -Layer Config -Resource $id `
                -Seen $(if ($all.Count) { "Model account '$name' has no successfully provisioned deployment." } else { "Model account '$name' has no model deployments." }) -Owner ResourceOwner `
                -Action "Deploy the model the evaluation uses on account '$name'." -Evidence @(Get-EvRef $deployments) -Details @{ deployments = $summary }))
        }
        else {
            $out.Add((New-DiagResult -Id model.deployment -Area Models -Title $title -Status OK -Path $P -Layer Config -Resource $id `
                -Seen "Deployments ready: $(($ready | ForEach-Object { $_.name }) -join ', ')." -Evidence @(Get-EvRef $deployments) -Details @{ deployments = $summary }))
        }
    }

    # model.authentication — Microsoft Entra ID vs key.
    $title = 'Model connection authentication'
    $connRead = Get-Ev $Evidence "$($Evidence.discovery.project)/connections"
    $gap = New-ReadGap $connRead -Id model.authentication -Area Models -Title $title -Layer Access -Path $P -Resource $id -What 'the project connections'
    if ($gap) { $out.Add($gap) }
    elseif ($connRead.Ok) {
        $auth = @($connRead.Data | Where-Object { $_ -and $_.name -eq $conn.name })[0].properties.authType
        $localOff = $target.Ok -and $target.Data.properties.disableLocalAuth -eq $true
        if (!$auth) {
            $out.Add((New-DiagResult -Id model.authentication -Area Models -Title $title -Status CouldNotCheck -Gap KnownLimit -Path $P -Layer Access -Resource $id `
                -Seen "Connection '$($conn.name)' has no authentication type in its metadata." -Needs "Check the authentication type of connection '$($conn.name)' in the Foundry portal." `
                -Evidence @(Get-EvRef $connRead)))
        }
        elseif ($auth -in $script:ModelEntraAuthTypes) {
            $out.Add((New-DiagResult -Id model.authentication -Area Models -Title $title -Status OK -Path $P -Layer Access -Resource $id `
                -Seen "Connection '$($conn.name)' uses Microsoft Entra ID ($auth)." -Evidence @(Get-EvRef $connRead) -Details @{ authType = $auth }))
        }
        elseif ($localOff) {
            $out.Add((New-DiagResult -Id model.authentication -Area Models -Title $title -Status Problem -Severity High -Path $P -Layer Access -Resource $id `
                -Seen "Connection '$($conn.name)' uses $auth, but model account '$name' has key authentication disabled." -Owner Customer `
                -Action "Change connection '$($conn.name)' to Microsoft Entra ID authentication and give the project managed identity Azure AI User on '$name'." `
                -Evidence @((Get-EvRef $connRead), (Get-EvRef $target)) -Details @{ authType = $auth; disableLocalAuth = $true }))
        }
        else {
            $out.Add((New-DiagResult -Id model.authentication -Area Models -Title $title -Status Problem -Severity Low -Path $P -Layer Access -Resource $id `
                -Seen "Connection '$($conn.name)' uses $auth instead of Microsoft Entra ID." -Owner Customer `
                -Action "Change connection '$($conn.name)' to Microsoft Entra ID authentication." -Evidence @(Get-EvRef $connRead) -Details @{ authType = $auth }))
        }
    }

    , $out.ToArray()
}
