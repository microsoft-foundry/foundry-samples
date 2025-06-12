@echo off
REM Automated testing script for Azure AI Foundry Java Samples
REM Usage: testing.bat [SampleName]

setlocal enabledelayedexpansion

REM Function to display colored output (Windows console colors)
:print_color
set "color=%~1"
set "message=%~2"
echo [%color%m%message%[0m
exit /b


REM Check for Java and Maven
where java >nul 2>&1
if %ERRORLEVEL% neq 0 (
    call :print_color 31 "Error: Java is not installed or not in PATH"
    exit /b 1
)

where mvn >nul 2>&1
if %ERRORLEVEL% neq 0 (
    call :print_color 31 "Error: Maven is not installed or not in PATH"
    exit /b 1
)

REM Check if user is logged in with Azure CLI
call :print_color 36 "Checking Azure CLI login status..."
az account show >nul 2>&1
if %ERRORLEVEL% neq 0 (
    call :print_color 31 "Error: You are not logged in with the Azure CLI. Please run 'az login' first."
    exit /b 1
) else (
    call :print_color 32 "Azure CLI login validated."
)

REM Check for required environment variables
call :print_color 36 "Validating environment variables..."
set "missing_vars="

REM Check for PROJECT_ENDPOINT (primary) or AZURE_ENDPOINT (fallback)
if "%PROJECT_ENDPOINT%"=="" (
    if "%AZURE_ENDPOINT%"=="" (
        set "missing_vars=!missing_vars! PROJECT_ENDPOINT or AZURE_ENDPOINT"
    ) else (
        call :print_color 36 "Using AZURE_ENDPOINT as fallback for PROJECT_ENDPOINT"
    )
) 

REM Build the project first
call :print_color 36 "=============================================================="
call :print_color 36 "   BUILDING PROJECT"
call :print_color 36 "=============================================================="

call mvn clean compile
if %ERRORLEVEL% neq 0 (
    call :print_color 31 "Error: Failed to build the project"
    exit /b 1
)

REM If a specific test is specified, run only that test
if not "%~1"=="" (
    call :run_test %1
    if !ERRORLEVEL! equ 0 (
        call :print_color 32 "Single test completed successfully."
    ) else (
        call :print_color 31 "Single test failed."
        exit /b 1
    )
    exit /b 0
)

REM Run all tests in sequence
set samples=CreateProject ChatCompletionSample ChatCompletionStreamingSample AgentSample FileSearchAgentSample EvaluateAgentSample

REM Arrays to track results
set passed_tests=
set failed_tests=
set success=true

REM Run each test
for %%s in (%samples%) do (
    call :run_test %%s
    if !ERRORLEVEL! equ 0 (
        set passed_tests=!passed_tests! %%s
    ) else (
        set failed_tests=!failed_tests! %%s
        set success=false
    )
    
    REM Short pause between tests
    timeout /t 2 /nobreak >nul
)

REM Print summary
call :print_color 36 "=============================================================="
call :print_color 36 "   TEST SUMMARY"
call :print_color 36 "=============================================================="

call :print_color 32 "PASSED TESTS:"
for %%t in (%passed_tests%) do (
    call :print_color 32 "  ✓ %%t"
)

if not "%failed_tests%"=="" (
    call :print_color 31 "FAILED TESTS:"
    for %%t in (%failed_tests%) do (
        call :print_color 31 "  ✗ %%t"
    )
    call :print_color 31 "Some tests failed. Please check the logs above for details."
    exit /b 1
) else (
    call :print_color 32 "All tests passed successfully!"
)

exit /b 0

:run_test
set sample=%~1
call :print_color 36 "=============================================================="
call :print_color 36 "   RUNNING TEST: %sample%"
call :print_color 36 "=============================================================="

REM Run the test
call mvn exec:java -Dexec.mainClass="com.azure.ai.foundry.samples.%sample%"
if %ERRORLEVEL% equ 0 (
    call :print_color 32 "✓ TEST PASSED: %sample%"
    exit /b 0
) else (
    call :print_color 31 "✗ TEST FAILED: %sample%"
    exit /b 1
)
REM End of script
:end