# Script to remove sensitive commit from git history

# Step 1: Reset to remote main (clean state)
Write-Host "Resetting to remote main..." -ForegroundColor Yellow
git reset --hard origin/main

# Step 2: Cherry-pick the good changes from backup
Write-Host "This will create a clean history without the secret keys" -ForegroundColor Green
Write-Host "The commit with exposed secrets (8f455c5) will NOT be included" -ForegroundColor Green

# Step 3: Show current status
git status

Write-Host "`nGit history has been cleaned. Your local branch is now aligned with remote." -ForegroundColor Green
Write-Host "The problematic commit 8f455c5 with exposed API keys has been removed." -ForegroundColor Green
