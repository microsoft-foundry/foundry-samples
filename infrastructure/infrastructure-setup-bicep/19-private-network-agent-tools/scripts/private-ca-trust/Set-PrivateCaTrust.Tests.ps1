#Requires -Modules @{ ModuleName = "Pester"; ModuleVersion = "5.0.0" }

Describe "Public-preview private CA registration" {
    BeforeAll {
        $trustScript = Join-Path $PSScriptRoot "Set-PrivateCaTrust.ps1"
    }

    BeforeEach {
        $script:parameters = @{
            SubscriptionId = "test-subscription"
            ResourceGroup = "test-group"
            AccountName = "test-account"
            KeyVaultResourceId = "/subscriptions/test-subscription/resourceGroups/test-group/providers/Microsoft.KeyVault/vaults/test-vault"
            CertificateReference = @("root-ca=newversion")
            OutputPath = Join-Path $TestDrive "$([guid]::NewGuid()).json"
            Confirm = $false
        }
        $script:sources = @()
        $script:patchBody = $null
        $script:statuses = [Collections.Generic.Queue[string]]::new()
        $script:statuses.Enqueue("Succeeded")
        $script:operationUrl = "https://management.azure.com/operations/test?api-version=2026-07-15-preview"
        $script:retryAfter = "0"
        $script:changeOnRecheck = $false
        $script:dropPreserved = $false
        $script:accountReads = 0

        Mock az {
            $global:LASTEXITCODE = 0
            return "test-token"
        }
        Mock Start-Sleep {}
        Mock Invoke-WebRequest {
            param($Method, $Uri, $Body)

            if ($Method -eq "PATCH") {
                $script:patchBody = [Text.Encoding]::UTF8.GetString($Body) | ConvertFrom-Json
                $script:sources = @($script:patchBody.properties.trustedCertificateSources)
                return [pscustomobject]@{
                    Headers = @{
                        "Azure-AsyncOperation" = $script:operationUrl
                        "Retry-After" = $script:retryAfter
                    }
                    Content = "{}"
                }
            }
            if ([string]$Uri -like "*operations/test*") {
                return [pscustomobject]@{
                    Headers = @{ "Retry-After" = $script:retryAfter }
                    Content = (@{ status = $script:statuses.Dequeue() } | ConvertTo-Json)
                }
            }
            $script:accountReads++
            $returnedSources = $script:sources
            if ($script:changeOnRecheck -and $script:accountReads -eq 2) {
                $returnedSources = @(@{
                    type = "AzureKeyVault"
                    resourceId = $script:parameters.KeyVaultResourceId
                    certificateBundleReferences = @(@{ secretName = "other"; secretVersion = "v1" })
                })
            }
            if ($script:dropPreserved -and $null -ne $script:patchBody) {
                $returnedSources = @(@{
                    type = "AzureKeyVault"
                    resourceId = $script:parameters.KeyVaultResourceId
                    certificateBundleReferences = @(@{ secretName = "root-ca"; secretVersion = "newversion" })
                })
            }
            return [pscustomobject]@{
                Headers = @{}
                Content = (@{ properties = @{ trustedCertificateSources = @($returnedSources) } } |
                    ConvertTo-Json -Depth 30)
            }
        }
    }

    It "registers the nested schema and waits through Updating before read-back" {
        $script:statuses.Clear()
        foreach ($status in @("Accepted", "NotStarted", "Running", "InProgress", "Updating", "Succeeded")) {
            $script:statuses.Enqueue($status)
        }
        $result = . $trustScript @script:parameters | ConvertFrom-Json
        $result.trustedCertificateSources[0].type | Should -Be "AzureKeyVault"
        $result.trustedCertificateSources[0].certificateBundleReferences[0].secretVersion | Should -Be "newversion"
        $script:patchBody.properties.PSObject.Properties.Name | Should -Be "trustedCertificateSources"
        $script:accountReads | Should -Be 3
        $script:statuses.Count | Should -Be 0
        Get-Content "$($script:parameters.OutputPath).operation.txt" | Should -Be $script:operationUrl
        $result.nextStep | Should -Match "automatically"
    }

    It "rotates only the requested pin and preserves unrelated references" {
        $script:sources = @(@{
            type = "AzureKeyVault"
            resourceId = $script:parameters.KeyVaultResourceId.ToUpperInvariant()
            certificateBundleReferences = @(
                @{ secretName = "root-ca"; secretVersion = "oldversion" },
                @{ secretName = "intermediate-ca"; secretVersion = "keepversion" }
            )
        })
        $result = . $trustScript @script:parameters | ConvertFrom-Json
        $references = $result.trustedCertificateSources[0].certificateBundleReferences
        $references.Count | Should -Be 2
        ($references | Where-Object secretName -eq "intermediate-ca").secretVersion | Should -Be "keepversion"
        ($references | Where-Object secretName -eq "root-ca").secretVersion | Should -Be "newversion"
    }

    It "refuses another vault without patching" {
        $script:sources = @(@{
            type = "AzureKeyVault"
            resourceId = "$($script:parameters.KeyVaultResourceId)-other"
            certificateBundleReferences = @()
        })
        { . $trustScript @script:parameters } | Should -Throw "*another vault*"
        Assert-MockCalled Invoke-WebRequest -Times 0 -Exactly -ParameterFilter { $Method -eq "PATCH" }
    }

    It "rejects more than 25 references after merging" {
        $script:sources = @(@{
            type = "AzureKeyVault"
            resourceId = $script:parameters.KeyVaultResourceId
            certificateBundleReferences = @(1..25 | ForEach-Object {
                @{ secretName = "ca-$_"; secretVersion = "v1" }
            })
        })
        { . $trustScript @script:parameters } | Should -Throw "*limit of 25*"
        Assert-MockCalled Invoke-WebRequest -Times 0 -Exactly -ParameterFilter { $Method -eq "PATCH" }
    }

    It "detects an intervening change before patching" {
        $script:changeOnRecheck = $true
        { . $trustScript @script:parameters } | Should -Throw "*changed since the initial read*"
        Assert-MockCalled Invoke-WebRequest -Times 0 -Exactly -ParameterFilter { $Method -eq "PATCH" }
    }

    It "rejects null sources rather than silently dropping them" {
        $script:sources = @($null)
        { . $trustScript @script:parameters } | Should -Throw "*null trust source*"
        Assert-MockCalled Invoke-WebRequest -Times 0 -Exactly -ParameterFilter { $Method -eq "PATCH" }
    }

    It "rejects malformed existing bundle references" {
        $script:sources = @(@{
            type = "AzureKeyVault"
            resourceId = $script:parameters.KeyVaultResourceId
            certificateBundleReferences = @(@{ secretName = "other" })
        })
        { . $trustScript @script:parameters } | Should -Throw "*Unexpected certificate bundle reference*"
        Assert-MockCalled Invoke-WebRequest -Times 0 -Exactly -ParameterFilter { $Method -eq "PATCH" }
    }

    It "does not patch or write a report under WhatIf" {
        . $trustScript @script:parameters -WhatIf
        Assert-MockCalled Invoke-WebRequest -Times 0 -Exactly -ParameterFilter { $Method -eq "PATCH" }
        Test-Path $script:parameters.OutputPath | Should -BeFalse
    }

    It "reports failed and canceled operations without a success report" {
        foreach ($status in @("Failed", "Canceled", "Cancelled")) {
            $script:statuses.Clear()
            $script:statuses.Enqueue($status)
            { . $trustScript @script:parameters } | Should -Throw "*did not succeed*"
            Test-Path $script:parameters.OutputPath | Should -BeFalse
        }
    }

    It "rejects unknown and missing operation statuses" {
        foreach ($status in @("Unexpected", "")) {
            $script:statuses.Clear()
            $script:statuses.Enqueue($status)
            { . $trustScript @script:parameters } | Should -Throw "*Unexpected LRO response*"
            Test-Path $script:parameters.OutputPath | Should -BeFalse
        }
    }

    It "retains the operation URL when monitoring times out" {
        $script:parameters.TimeoutSeconds = 1
        { . $trustScript @script:parameters } | Should -Throw "*Monitoring timed out*"
        Test-Path "$($script:parameters.OutputPath).operation.txt" | Should -BeTrue
        Test-Path $script:parameters.OutputPath | Should -BeFalse
    }

    It "rejects an operation URL on another origin before sending credentials" {
        $script:operationUrl = "https://example.invalid/operations/test"
        { . $trustScript @script:parameters } | Should -Throw "*Unexpected ARM operation URL*"
        Assert-MockCalled Invoke-WebRequest -Times 0 -Exactly -ParameterFilter {
            [string]$Uri -like "*example.invalid*"
        }
    }

    It "requires an async-operation header" {
        $script:operationUrl = ""
        { . $trustScript @script:parameters } | Should -Throw "*No Azure-AsyncOperation*"
        Test-Path $script:parameters.OutputPath | Should -BeFalse
    }

    It "honors Retry-After" {
        $script:retryAfter = "7"
        . $trustScript @script:parameters | Out-Null
        Assert-MockCalled Start-Sleep -Times 1 -Exactly -ParameterFilter { $Seconds -eq 7 }
    }

    It "rejects invalid Retry-After without losing the operation URL" {
        $script:retryAfter = "invalid"
        { . $trustScript @script:parameters } | Should -Throw "*Invalid Retry-After*"
        Test-Path "$($script:parameters.OutputPath).operation.txt" | Should -BeTrue
    }

    It "detects lost preserved references during read-back" {
        $script:sources = @(@{
            type = "AzureKeyVault"
            resourceId = $script:parameters.KeyVaultResourceId
            certificateBundleReferences = @(@{ secretName = "other"; secretVersion = "v1" })
        })
        $script:dropPreserved = $true
        { . $trustScript @script:parameters } | Should -Throw "*didn't persist*"
        Test-Path $script:parameters.OutputPath | Should -BeFalse
    }
}
