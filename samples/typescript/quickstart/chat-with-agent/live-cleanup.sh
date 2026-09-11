#!/usr/bin/env bash
# Auto-detected by validate-sample.sh and run after the main live_service_validation
# command, regardless of that command's outcome. Deletes only the agent this sample
# created — never touches other project resources (e.g. the model deployment).
set -e
npm run live-cleanup:delete-agent
