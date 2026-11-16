#Requires -Version 7.2
[CmdletBinding()]
param([Parameter(Mandatory)][string]$OutputDirectory)
. (Join-Path $PSScriptRoot '..\scripts\Deployment.ps1')
$script:proofChecks=0
function Assert-Proof([bool]$Value,[string]$Message) {
    if(!$Value){throw "ATTRIBUTION ASSERTION: $Message"};$script:proofChecks++
}
$approvedDoc=Read-Json (Join-Path $PSScriptRoot 'fixtures\approved-bicep-network.json')
$exportDoc=Read-Json (Join-Path $PSScriptRoot 'fixtures\actual-azure-export-network.json')
$metadataFixture=Read-Json (Join-Path $PSScriptRoot 'fixtures\deployment-network-succeeded.json')
$caseConfig=Read-SetupConfig (Join-Path $PSScriptRoot '..\assets\input.no-monitoring.example.json')
$requestValues=@{location=@{value='koreacentral'};config=@{value=$caseConfig.network}}
$request=@{asset='network';scope=($metadataFixture.id -replace '/providers/Microsoft.Resources/deployments/[^/]+$','')
    resourceId=$metadataFixture.id;template=$approvedDoc;bicepGeneratorHash='13644102471240374280'
    parameters=$requestValues;parametersHash=(Get-Digest (Get-ParameterValues $approvedDoc $requestValues))}
$casePlan=Seal-Approval (New-Approval 'Deployment' $caseConfig $request @{})
$script:fixtureExport=$null;$script:fixtureDeployment=$null;$script:exportStatus=200;$script:exportCalls=0;$script:commands=@();$script:metadataReads=0
function Invoke-SetupCli {
    param($Arguments,[scriptblock]$OnStart)
    $script:commands+=,@($Arguments)
    if(($Arguments[0..2] -join ' ') -cne 'deployment group export' -or $OnStart){throw 'OFFLINE: only read-only native export is allowed in this fixture'}
    $script:exportCalls++
    @{Code=$script:exportStatus;Data=$script:fixtureExport}
}
function Get-SetupResource {
    param($Id,[switch]$Optional)
    $script:metadataReads++
    if($Id -ine $metadataFixture.id){throw 'OFFLINE: unexpected resource read'}
    Copy-Data $script:fixtureDeployment
}
function Reset-ProofFixture([string]$Name) {
    $script:fixtureExport=Copy-Data $exportDoc
    $script:fixtureDeployment=Copy-Data $metadataFixture
    $script:fixtureDeployment.properties.templateHash='15670727587737489330'
    $script:exportStatus=200;$script:exportCalls=0;$script:commands=@()
    $attempt=New-Attempt $casePlan (Join-Path $OutputDirectory $Name)
    $attempt.receipt.submissionStartedAt=[DateTimeOffset]::Parse('2026-10-21T20:39:00Z').ToUnixTimeMilliseconds()
    $attempt.receipt.state='OutcomeUnknown'
    Write-Json $attempt.path $attempt.receipt
    return $attempt
}
$approvedHash=Get-TemplateContentHash $approvedDoc
Assert-Proof ($approvedHash -ceq '4bf8e86f579e0516119e723ed0f0dc3606fc1a1732e8a021bfdf807e2425d92e') 'Independent approved fixture matches parent full-content SHA256'
Assert-Proof ((Get-TemplateContentHash $exportDoc) -ceq $approvedHash) 'Real independent Azure export content matches despite compiler/type representation changes'
$attempt=Reset-ProofFixture 'positive'
$outcome=Get-DeploymentOutcome $casePlan $attempt
Assert-Proof ($outcome.state -eq 'Succeeded' -and $outcome.providerTemplateHash -cne $casePlan.request.bicepGeneratorHash) 'Different real provider/generator hashes do not cause false OutcomeUnknown'
Assert-Proof ($outcome.templateContentHash -ceq $approvedHash -and $script:exportCalls -eq 1) 'Native full-content proof obtained once'
Assert-Proof (($script:commands[0] -join ' ') -match 'deployment group export --subscription .* --resource-group .* --name setup-network-fixture') 'Actual native export command uses exact operation scope/name'
$saved=Read-Json $attempt.path
Assert-Proof ($saved.templateContentProof.binding.operationId -ceq $casePlan.operationId -and $saved.templateContentProof.binding.requestHash -ceq (Get-Digest $casePlan.request)) 'Persisted proof bound to original request/attempt'
$cached=@{path=$attempt.path;receipt=$saved}
$null=Get-DeploymentOutcome $casePlan $cached
Assert-Proof ($script:exportCalls -eq 1) 'Successful proof reused across status reads without repeated export'
$script:fixtureDeployment.properties.templateHash='different-provider-revision'
$changed=Get-DeploymentOutcome $casePlan $cached
Assert-Proof ($changed.state -eq 'OutcomeUnknown' -and $changed.attributionCode -eq 'TemplateProofBindingChanged' -and $script:exportCalls -eq 1) 'Subsequent provider inconsistency rejected, not re-exported/adopted'

foreach($mutation in @('resource','output','default','metadata')){
    $attempt=Reset-ProofFixture "changed-$mutation"
    switch($mutation){
        'resource'{$script:fixtureExport.resources[0].properties.subnets[0].properties.addressPrefix='changed-resource-value'}
        'output'{$script:fixtureExport.outputs.agentSubnetResourceId.value='changed-output-value'}
        'default'{$script:fixtureExport.parameters.location.defaultValue='changed-default-value'}
        'metadata'{$script:fixtureExport.metadata=@{custom='SECRET-SENTINEL-DO-NOT-LOG'}}
    }
    $outcome=Get-DeploymentOutcome $casePlan $attempt
    Assert-Proof ($outcome.state -eq 'OutcomeUnknown' -and $outcome.attributionCode -eq 'TemplateContentMismatch' -and
        $outcome.approvedContentHash -cne $outcome.exportedContentHash) "Full template rejects changed $mutation with precise hashes"
    Assert-Proof (($outcome|ConvertTo-Json -Depth 100) -notmatch 'SECRET-SENTINEL|changed-resource-value|changed-output-value|changed-default-value') "No raw $mutation payload in diagnostics"
}
$attempt=Reset-ProofFixture 'wrong-actual-parameters'
$script:fixtureDeployment.properties.parameters.config.value.agentSubnetPrefix='10.241.8.0/24'
$outcome=Get-DeploymentOutcome $casePlan $attempt
Assert-Proof ($outcome.state -eq 'OutcomeUnknown' -and $outcome.reason -like 'Actual parameter values differ*' -and $script:exportCalls -eq 0) 'Changed actual values still reject before export'
$attempt=Reset-ProofFixture 'wrong-correlation';$attempt.receipt.correlationId='another-correlation'
$outcome=Get-DeploymentOutcome $casePlan $attempt
Assert-Proof ($outcome.state -eq 'OutcomeUnknown' -and $outcome.reason -like 'Correlation differs*' -and $script:exportCalls -eq 0) 'Wrong original correlation still rejects before export'
$attempt=Reset-ProofFixture 'old-operation';$script:fixtureDeployment.properties.timestamp='2026-10-21T20:20:00Z'
$outcome=Get-DeploymentOutcome $casePlan $attempt
Assert-Proof ($outcome.state -eq 'OutcomeUnknown' -and $outcome.reason -like 'Old same-name*' -and $script:exportCalls -eq 0) 'Old same-name attempt not accepted from matching template alone'
$attempt=Reset-ProofFixture 'forbidden-export';$script:exportStatus=403
$outcome=Get-DeploymentOutcome $casePlan $attempt
Assert-Proof ($outcome.state -eq 'OutcomeUnknown' -and $outcome.attributionCode -eq 'DeploymentExportUnavailable' -and $outcome.status -eq 403) 'Unavailable/unauthorized export cannot become success or permission escalation'
$attempt=Reset-ProofFixture 'malformed-export';$script:fixtureExport='SECRET-SENTINEL'
$outcome=Get-DeploymentOutcome $casePlan $attempt
Assert-Proof ($outcome.state -eq 'OutcomeUnknown' -and $outcome.attributionCode -eq 'DeploymentExportInvalidTemplate' -and
    ($outcome|ConvertTo-Json) -notmatch 'SECRET-SENTINEL') 'Malformed export remains unknown with sanitized cause'
$attempt=Reset-ProofFixture 'reconcile-export-failure';$script:exportStatus=403
$result=Reconcile-Deployment $casePlan (Split-Path $attempt.path)
Assert-Proof ($result.state -eq 'OutcomeUnknown' -and $result.attribution.attributionCode -eq 'DeploymentExportUnavailable' -and
    $result.reason -like '*status 403*') 'Reconciliation receipt retains specific export failure instead of generic unknown'
$attempt=Reset-ProofFixture 'reconcile-content-mismatch';$script:fixtureExport.resources[0].location='SECRET-SENTINEL'
$result=Reconcile-Deployment $casePlan (Split-Path $attempt.path)
Assert-Proof ($result.attribution.attributionCode -eq 'TemplateContentMismatch' -and $result.attribution.Contains('exportedContentHash') -and
    ($result|ConvertTo-Json -Depth 100) -notmatch 'SECRET-SENTINEL') 'Mismatch receipt retains precise hashes without raw template'
$attempt=Reset-ProofFixture 'reconcile-success'
$result=Reconcile-Deployment $casePlan (Split-Path $attempt.path)
Assert-Proof ($result.state -eq 'Succeeded' -and $result.result.templateContentHash -ceq $approvedHash) 'Original unknown attempt automatically reconciles from independent exact content proof'

$nested=Read-Json (Join-Path $PSScriptRoot 'fixtures\nested-template-content.json')
$nestedHash=Get-TemplateContentHash $nested.approved
Assert-Proof ($nestedHash -ceq (Get-TemplateContentHash $nested.exported)) 'Nested ARM document compiler/type changes narrowly normalized'
foreach($mutation in @('resource-metadata','resource-type-value','array-order','child-output','custom-document-metadata')){
    $changed=Copy-Data $nested.exported
    switch($mutation){
        'resource-metadata'{$changed.resources[0].properties.template.resources[0].properties.metadata._generator.templateHash='different-custom-generator'}
        'resource-type-value'{$changed.resources[0].properties.template.resources[0].properties.type='string'}
        'array-order'{$changed.resources[0].properties.template.resources[0].properties.values=@('b','a')}
        'child-output'{$changed.resources[0].properties.template.outputs.result.value='different'}
        'custom-document-metadata'{$changed.metadata.custom='different'}
    }
    Assert-Proof ((Get-TemplateContentHash $changed) -cne $nestedHash) "Nested proof preserves $mutation"
}
$caseDistinct=Copy-Data $nested.exported
$caseDistinct.metadata=[hashtable]::new([StringComparer]::Ordinal);$caseDistinct.metadata['ResourceId']='one';$caseDistinct.metadata['resourceId']='two'
$caseDistinct2=Copy-Data $caseDistinct;$caseDistinct2.metadata['ResourceId']='changed'
Assert-Proof ((Get-TemplateContentHash $caseDistinct) -cne (Get-TemplateContentHash $caseDistinct2)) 'Full proof preserves case-distinct custom metadata keys'
$result=@{assertions=$script:proofChecks;recordedContentHash=$approvedHash;fixtures=@('approved-bicep-network.json','actual-azure-export-network.json','nested-template-content.json');azureCalls=0}
Write-Json (Join-Path $OutputDirectory 'results.json') $result
return $result
