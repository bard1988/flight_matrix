<#
.SYNOPSIS
    Diagnoses a git push failing with:
        remote: Permission to <owner>/<repo>.git denied to <someuser>.
        fatal: ... The requested URL returned error: 403

.DESCRIPTION
    HTTP 403 on push means authentication SUCCEEDED but authorization FAILED:
    git sent a valid credential, and the account it belongs to has no write
    access to the target repo. This script figures out which account git is
    actually sending, and why it lacks write access.

    Read-only by default. It never prints your token.

.PARAMETER RepoPath
    Path to the local repo. Defaults to the current directory.

.PARAMETER RemoteName
    Remote to inspect. Defaults to "origin".

.PARAMETER NoApi
    Skip the GitHub API checks (which send your existing credential to
    api.github.com over HTTPS, exactly as git already does on push).

.PARAMETER ClearCredential
    THE ONLY WRITE ACTION. Deletes the cached github.com credential from
    Windows Credential Manager and from git's credential helper, so the next
    push prompts you to sign in again. Nothing is deleted unless you pass this.

.NOTES
    On a managed/corporate Windows box, Group Policy commonly forces the
    PowerShell execution policy to AllSigned. Group Policy OVERRIDES
    -ExecutionPolicy Bypass, so "powershell -File thisscript.ps1" fails with
    "is not digitally signed" no matter what flags you pass.

    Use the gh-push-403-diagnose.cmd wrapper instead. It feeds this script to
    PowerShell over stdin, which AllSigned does not apply to, and passes
    options through the GHDIAG_* environment variables read below.

.EXAMPLE
    gh-push-403-diagnose.cmd

.EXAMPLE
    gh-push-403-diagnose.cmd -RepoPath C:\code\flight_matrix

.EXAMPLE
    gh-push-403-diagnose.cmd -ClearCredential
#>

[CmdletBinding()]
param(
    [string]$RepoPath    = $(if ($env:GHDIAG_REPOPATH)   { $env:GHDIAG_REPOPATH }   else { "." }),
    [string]$RemoteName  = $(if ($env:GHDIAG_REMOTE)     { $env:GHDIAG_REMOTE }     else { "origin" }),
    [switch]$NoApi       = $(if ($env:GHDIAG_NOAPI -eq "1") { $true } else { $false }),
    [switch]$ClearCredential = $(if ($env:GHDIAG_CLEAR -eq "1") { $true } else { $false })
)

$ErrorActionPreference = "Continue"

# ---------------------------------------------------------------- helpers ---

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkGray
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor DarkGray
}

function Write-Finding {
    param([string]$Text, [string]$Level = "info")
    switch ($Level) {
        "good" { Write-Host "  [OK]    $Text" -ForegroundColor Green }
        "bad"  { Write-Host "  [ISSUE] $Text" -ForegroundColor Red }
        "warn" { Write-Host "  [WARN]  $Text" -ForegroundColor Yellow }
        default { Write-Host "  [INFO]  $Text" -ForegroundColor Gray }
    }
}

function Mask-Secret {
    param([string]$Secret)
    if ([string]::IsNullOrEmpty($Secret)) { return "<empty>" }
    $prefix = if ($Secret.Length -ge 4) { $Secret.Substring(0, 4) } else { "?" }
    return "$prefix... (length $($Secret.Length))"
}

# Collect findings so we can print a verdict at the end.
$script:Verdict = @()
function Add-Verdict { param([string]$Text) $script:Verdict += $Text }

# ---------------------------------------------------------------- preflight -

Write-Host ""
Write-Host "GitHub push 403 diagnostic" -ForegroundColor White
Write-Host "Run date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor DarkGray
Write-Host "Machine:  $env:COMPUTERNAME    User: $env:USERNAME" -ForegroundColor DarkGray

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Finding "git is not on PATH. Open 'Git Bash' or install Git for Windows." "bad"
    return
}

if (-not (Test-Path $RepoPath)) {
    Write-Finding "RepoPath '$RepoPath' does not exist." "bad"
    return
}
Set-Location $RepoPath

$insideRepo = (git rev-parse --is-inside-work-tree 2>$null)
if ($insideRepo -ne "true") {
    Write-Finding "'$((Get-Location).Path)' is not a git repository. Pass -RepoPath <folder>." "bad"
    return
}

# ------------------------------------------------------------- 1. remote ----

Write-Section "1. Remote URL"

$remoteUrl = (git remote get-url $RemoteName 2>$null)
if (-not $remoteUrl) {
    Write-Finding "No remote named '$RemoteName'. Remotes found:" "bad"
    git remote -v
    return
}

Write-Host "  $RemoteName -> $remoteUrl"

$owner = $null; $repo = $null; $hostName = $null; $urlHasCreds = $false

if ($remoteUrl -match '^https?://(?:(?<creds>[^@/]+)@)?(?<host>[^/]+)/(?<owner>[^/]+)/(?<repo>[^/]+?)(?:\.git)?/?$') {
    $hostName = $Matches['host']
    $owner    = $Matches['owner']
    $repo     = $Matches['repo']
    if ($Matches['creds']) { $urlHasCreds = $true }
    $scheme = "https"
}
elseif ($remoteUrl -match '^(?:ssh://)?git@(?<host>[^:/]+)[:/](?<owner>[^/]+)/(?<repo>[^/]+?)(?:\.git)?/?$') {
    $hostName = $Matches['host']
    $owner    = $Matches['owner']
    $repo     = $Matches['repo']
    $scheme = "ssh"
}
else {
    Write-Finding "Could not parse the remote URL. Continuing with limited checks." "warn"
    $scheme = "unknown"
}

if ($hostName) { Write-Finding "host=$hostName  owner=$owner  repo=$repo  transport=$scheme" }

if ($urlHasCreds) {
    Write-Finding "The remote URL has a username embedded in it. That username overrides anything in Credential Manager and is a very common cause of this error." "bad"
    Add-Verdict "Remote URL contains an embedded username. Reset it with: git remote set-url $RemoteName https://$hostName/$owner/$repo.git"
}

if ($scheme -eq "ssh") {
    Write-Finding "This remote uses SSH, but the error you reported is an HTTPS 403. Either the failing machine uses a different URL, or you have since changed it." "warn"
}

# --------------------------------------------------- 2. git identity config -

Write-Section "2. Git config touching credentials and identity"

$cfg = git config --list --show-origin 2>$null |
       Select-String -Pattern "credential|user\.name|user\.email|url\."
if ($cfg) { $cfg | ForEach-Object { Write-Host "  $_" } }
else      { Write-Finding "No credential/user config found in any scope." }

$helper = (git config --get credential.helper 2>$null)
if ($helper) { Write-Finding "Active credential.helper = $helper" }
else         { Write-Finding "No credential.helper set. Git will prompt every time." "warn" }

Write-Host ""
Write-Host "  NOTE: user.name / user.email only label your commits. They have" -ForegroundColor DarkGray
Write-Host "        NO effect on which account is authorized to push." -ForegroundColor DarkGray

# ------------------------------------------- 3. Windows Credential Manager --

Write-Section "3. Windows Credential Manager entries for this host"

$targetHost = if ($hostName) { $hostName } else { "github.com" }
$cmdkeyOut  = cmdkey /list 2>$null | Out-String
$cmdkeyLines = $cmdkeyOut -split "`r?`n"

# Walk the listing so each Target: line can be paired with its User: line.
$hostEntries = @()
for ($i = 0; $i -lt $cmdkeyLines.Count; $i++) {
    if ($cmdkeyLines[$i] -match 'Target:' -and $cmdkeyLines[$i] -match [regex]::Escape($targetHost)) {
        $entryTarget = ($cmdkeyLines[$i] -replace '^\s*Target:\s*', '').Trim()
        $entryUser   = ""
        for ($j = $i + 1; $j -lt [Math]::Min($i + 4, $cmdkeyLines.Count); $j++) {
            if ($cmdkeyLines[$j] -match '^\s*User:\s*(.+)$') { $entryUser = $Matches[1].Trim(); break }
        }
        $hostEntries += [pscustomobject]@{ Target = $entryTarget; User = $entryUser }
    }
}

if ($hostEntries) {
    Write-Finding "Cached credential(s) found for ${targetHost}:" "warn"
    foreach ($e in $hostEntries) {
        Write-Host "    Target: $($e.Target)"
        Write-Host "    User:   $($e.User)" -ForegroundColor Yellow
        Write-Host ""
        if ($owner -and $e.User -and ($e.User -ne $owner)) {
            Add-Verdict "Credential Manager has a cached '$($e.User)' credential for $targetHost, but the repo is owned by '$owner'. Delete it with: cmdkey /delete:$($e.Target -replace '^LegacyGeneric:target=','')"
        }
    }
    Write-Host "  Windows caches credentials PER HOST, not per repo. Every repo" -ForegroundColor DarkGray
    Write-Host "  on $targetHost reuses the entry above, no matter who owns it." -ForegroundColor DarkGray
} else {
    Write-Finding "No cached credential for $targetHost in Credential Manager."
    Write-Finding "If section 6 still reports a username, the credential is coming from Git Credential Manager's own store rather than from cmdkey." "warn"
}

# --------------------------------------------- 4. plaintext credential file -

Write-Section "4. Plaintext credential store"

$credFile = Join-Path $env:USERPROFILE ".git-credentials"
if (Test-Path $credFile) {
    Write-Finding "$credFile exists (passwords masked below):" "warn"
    Get-Content $credFile | ForEach-Object {
        Write-Host "    $($_ -replace '://([^:/@]+):[^@]*@', '://$1:***@')"
    }
} else {
    Write-Finding "No $credFile."
}

# ------------------------------------------------------------- 5. gh CLI ----

Write-Section "5. GitHub CLI account"

if (Get-Command gh -ErrorAction SilentlyContinue) {
    gh auth status 2>&1 | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Finding "gh CLI not installed. Not a factor here."
}

# ------------------------------------- 6. what git actually sends (the key) -

Write-Section "6. THE KEY CHECK - which account git actually sends"

$sentUser  = $null
$sentToken = $null

if ($scheme -eq "ssh") {
    Write-Finding "SSH remote: running 'ssh -T git@$hostName' instead."
    $sshOut = ssh -T -o StrictHostKeyChecking=accept-new "git@$hostName" 2>&1 | Out-String
    Write-Host "  $($sshOut.Trim())"
    if ($sshOut -match "Hi (?<u>[^!]+)!") {
        $sentUser = $Matches['u']
        Write-Finding "SSH key authenticates as: $sentUser" "warn"
    }
}
else {
    # Never let this check block on an interactive login prompt.
    $prevPrompt = $env:GIT_TERMINAL_PROMPT
    $env:GIT_TERMINAL_PROMPT = "0"
    $env:GCM_INTERACTIVE = "never"

    # Feed the request via a temp file rather than a PowerShell pipe.
    # Piping a here-string straight into a native command mangles the line
    # endings/encoding enough that git rejects it with
    # "refusing to work with credential missing protocol field".
    $reqFile = Join-Path $env:TEMP "ghdiag_credreq.txt"
    [System.IO.File]::WriteAllText(
        $reqFile,
        "protocol=https`nhost=$targetHost`n`n",
        (New-Object System.Text.ASCIIEncoding)
    )
    $fillOut = (cmd /c "git credential fill < `"$reqFile`" 2>&1") | Out-String
    Remove-Item $reqFile -ErrorAction SilentlyContinue

    $env:GIT_TERMINAL_PROMPT = $prevPrompt

    foreach ($line in ($fillOut -split "`r?`n")) {
        if ($line -match '^username=(.*)$') { $sentUser  = $Matches[1] }
        if ($line -match '^password=(.*)$') { $sentToken = $Matches[1] }
    }

    if ($sentUser) {
        Write-Host ""
        Write-Host "  git will authenticate to $targetHost as:  " -NoNewline
        Write-Host $sentUser -ForegroundColor Yellow
        Write-Host "  credential/token:                         $(Mask-Secret $sentToken)"
        Write-Host ""

        if ($owner -and ($sentUser -ne $owner)) {
            Write-Finding "MISMATCH. The repo is owned by '$owner' but git authenticates as '$sentUser'." "bad"
            Add-Verdict "git is sending the wrong account ('$sentUser', not '$owner'). Clear the cached credential and re-authenticate: re-run this script with -ClearCredential"
        } elseif ($owner) {
            Write-Finding "Account matches the repo owner '$owner'. The problem is therefore token scope or repo access, not identity." "good"
        }
    } else {
        Write-Finding "git credential fill returned no username. Raw output:" "warn"
        Write-Host $fillOut
    }
}

# --------------------------------------------------------- 7. GitHub API ----

if (-not $NoApi -and $hostName -match 'github\.com$' -and $sentToken) {

    Write-Section "7. GitHub API - identity, token scopes, repo permissions"

    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if (-not $curl) {
        Write-Finding "curl.exe not found. Skipping API checks." "warn"
    }
    else {
        # --- 7a. who does this token belong to
        $hdrFile = Join-Path $env:TEMP "ghdiag_headers.txt"
        $body = & curl.exe -s -D $hdrFile -H "Authorization: Bearer $sentToken" `
                           -H "Accept: application/vnd.github+json" `
                           "https://api.github.com/user" 2>$null
        $headers = if (Test-Path $hdrFile) { Get-Content $hdrFile -Raw } else { "" }

        if ($body -match '"login"\s*:\s*"([^"]+)"') {
            Write-Finding "Token belongs to GitHub account: $($Matches[1])" "warn"
        } elseif ($body -match '"message"\s*:\s*"([^"]+)"') {
            Write-Finding "GitHub says: $($Matches[1])" "bad"
        }

        # --- 7b. classic PAT scopes
        if ($headers -match '(?im)^x-oauth-scopes:\s*(.*)$') {
            $scopes = $Matches[1].Trim()
            if ([string]::IsNullOrWhiteSpace($scopes)) {
                Write-Finding "Token has NO scopes. A classic PAT needs the 'repo' scope to push." "bad"
                Add-Verdict "Token has no scopes. Regenerate it with 'repo' (classic) or 'Contents: read and write' (fine-grained)."
            } else {
                Write-Finding "Classic PAT scopes: $scopes"
                if ($scopes -notmatch '\brepo\b') {
                    Write-Finding "Missing the 'repo' scope - push will always 403." "bad"
                    Add-Verdict "Token is missing the 'repo' scope. Regenerate it at https://github.com/settings/tokens"
                }
            }
        } else {
            Write-Finding "No x-oauth-scopes header - this is a fine-grained PAT, a GitHub App token, or an OAuth device token."
        }

        # --- 7c. SAML SSO enforcement
        if ($headers -match '(?im)^x-github-sso:\s*(.*)$') {
            Write-Finding "SAML SSO required for this token: $($Matches[1].Trim())" "bad"
            Add-Verdict "The token must be SSO-authorized for the organization. Open the URL in the x-github-sso header above."
        }

        # --- 7d. actual permissions on the target repo
        if ($owner -and $repo) {
            $repoBody = & curl.exe -s -H "Authorization: Bearer $sentToken" `
                                   -H "Accept: application/vnd.github+json" `
                                   "https://api.github.com/repos/$owner/$repo" 2>$null

            Write-Host ""
            if ($repoBody -match '"push"\s*:\s*(true|false)') {
                $canPush = $Matches[1]
                if ($canPush -eq "true") {
                    Write-Finding "API reports push=true for $owner/$repo. If the push still fails, the branch is protected or the repo is archived." "good"
                    Add-Verdict "Token CAN push per the API. Check branch protection rules on the target branch, and whether the repo is archived (archived repos reject all pushes with 403)."
                } else {
                    Write-Finding "API reports push=false for $owner/$repo. This account has read-only access." "bad"
                    Add-Verdict "The authenticated account has read-only access to $owner/$repo. The owner must add it as a collaborator with Write permission."
                }
            }
            elseif ($repoBody -match '"message"\s*:\s*"Not Found"') {
                Write-Finding "API returns 'Not Found' for $owner/$repo. Either the name is wrong, or this token cannot see the repo at all (GitHub hides private repos as 404)." "bad"
                Add-Verdict "Repo $owner/$repo is invisible to this token. Verify the exact owner/name, or get access granted."
            }
            elseif ($repoBody -match '"archived"\s*:\s*true') {
                Write-Finding "Repo is ARCHIVED. Archived repos reject every push with 403." "bad"
            }
            else {
                Write-Finding "Unexpected API response for the repo lookup."
            }
        }

        Remove-Item $hdrFile -ErrorAction SilentlyContinue
    }
}
elseif (-not $NoApi -and -not $sentToken) {
    Write-Section "7. GitHub API"
    Write-Finding "No token available from the credential helper, so API checks were skipped."
}

# ------------------------------------------------- 8. optional: clear creds -

if ($ClearCredential) {
    Write-Section "8. Clearing cached credential for $targetHost"

    $targets = $cmdkeyOut -split "`r?`n" |
               Where-Object { $_ -match 'Target:' -and $_ -match [regex]::Escape($targetHost) }

    if ($targets) {
        foreach ($t in $targets) {
            $name = ($t -replace '^\s*Target:\s*', '').Trim()
            $name = $name -replace '^LegacyGeneric:target=', ''
            Write-Host "  cmdkey /delete:$name"
            cmdkey /delete:$name | Out-Null
        }
    } else {
        Write-Finding "Nothing matching in Credential Manager; trying git's helper anyway."
    }

    "protocol=https`nhost=$targetHost`n`n" | git credential reject 2>$null
    Write-Finding "Done. The next push will prompt you to sign in." "good"
    Write-Finding "Sign in as the account that owns or has write access to $owner/$repo." "good"
}

# --------------------------------------------------------------- verdict ----

Write-Section "VERDICT"

if ($script:Verdict.Count -eq 0) {
    Write-Host "  No single conclusive cause found. Check sections 3 and 6 by hand:"
    Write-Host "  whichever account section 6 prints is the one GitHub is rejecting."
} else {
    $i = 1
    foreach ($v in $script:Verdict) {
        Write-Host "  $i. $v" -ForegroundColor White
        $i++
    }
}

Write-Host ""
Write-Host "  Reminder: 403 = authenticated but not authorized. 401 would mean" -ForegroundColor DarkGray
Write-Host "  bad credentials. Your credentials are fine; the ACCOUNT is wrong" -ForegroundColor DarkGray
Write-Host "  or lacks write permission." -ForegroundColor DarkGray
Write-Host ""
Write-Host "  To clear the cached account and start over:" -ForegroundColor DarkGray
Write-Host "      gh-push-403-diagnose.cmd -ClearCredential" -ForegroundColor DarkGray
Write-Host ""
