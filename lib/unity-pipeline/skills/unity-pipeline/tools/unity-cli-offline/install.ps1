<#
.SYNOPSIS
    Unity CLI 安装脚本（Windows，离线优先 + 在线回退）。

.DESCRIPTION
    安装 Unity CLI 命令行工具（Windows 版）。

    离线优先：  优先从本技能内置的离线安装包安装（无网络依赖），
                通过 SHA-256 校验后复制到 %LOCALAPPDATA%\Unity\bin 并加入用户 PATH。
    在线回退：  若离线包缺少当前平台二进制，则回退到官方 CDN 在线下载安装。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1

.PARAMETER Target
    要安装的版本。默认 "latest"（推荐）。

.PARAMETER Channel
    版本通道：""（stable）/ "alpha" / "beta"。默认取 $env:UNITY_CLI_CHANNEL。

.PARAMETER OfflineDir
    离线安装包所在目录（含二进制与版本清单）。默认脚本所在目录。

.PARAMETER InstallDir
    安装目录。默认 %LOCALAPPDATA%\Unity\bin。

.PARAMETER Proxy
    在线回退时使用的代理地址（如 http://127.0.0.1:7897）。国内网络直连官方 CDN
    可能拿到缓存旧版本，走代理可获取真实最新版本。

.LINK
    https://unity.com
#>

param(
    [string]$Target = "latest",
    [ValidateSet("", "alpha", "beta")]
    [string]$Channel = $env:UNITY_CLI_CHANNEL,
    [string]$OfflineDir = $PSScriptRoot,
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "Unity\bin"),
    [string]$Proxy = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # 加快下载

$CdnBase = "https://public-cdn.cloud.unity3d.com/hub/prod/cli/"

# 通道决定版本清单文件名：latest.json / latest-beta.json / latest-alpha.json
$ManifestFile = switch ($Channel) {
    "alpha" { "latest-alpha.json" }
    "beta"  { "latest-beta.json" }
    default { "latest.json" }
}

# ---------- 平台检查 ----------

if ([System.IntPtr]::Size -ne 8) {
    Write-Host "`n  error Windows 32 位不受支持。Unity CLI 需要 64 位系统。`n" -ForegroundColor Red
    exit 1
}

$arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "x64" }
$platformKey = "win32-$arch"

# ---------- 输出辅助 ----------

function Write-Info($msg) {
    Write-Host "  " -NoNewline
    Write-Host "信息" -ForegroundColor Cyan -NoNewline
    Write-Host "  $msg"
}

function Write-Warn($msg) {
    Write-Host "  " -NoNewline
    Write-Host "警告" -ForegroundColor Yellow -NoNewline
    Write-Host "  $msg"
}

function Fail($msg) {
    Write-Host "`n  " -NoNewline
    Write-Host "错误" -ForegroundColor Red -NoNewline
    Write-Host " $msg`n"
    exit 1
}

# ---------- 获取版本清单（在线） ----------

function Get-Manifest {
    $url = "${CdnBase}${ManifestFile}"
    Write-Info "正在检查最新版本..."
    try {
        $iwrParams = @{ Uri = $url; ErrorAction = "Stop" }
        if ($Proxy) {
            $iwrParams["Proxy"] = $Proxy
        }
        if ($PSVersionTable.PSVersion.Major -lt 6) {
            $iwrParams["UseBasicParsing"] = $true
        }
        $response = Invoke-WebRequest @iwrParams
        return $response.Content | ConvertFrom-Json
    }
    catch {
        Fail "获取版本清单失败：$url`n  $_"
    }
}

# ---------- 下载二进制（在线） ----------

function Get-Binary($url, $dest) {
    Write-Info "正在下载二进制..."
    try {
        $wc = New-Object System.Net.WebClient
        if ($Proxy) {
            $wc.Proxy = New-Object System.Net.WebProxy($Proxy)
        }
        $wc.DownloadFile($url, $dest)
    }
    catch {
        Fail "下载二进制失败：$url`n  $_"
    }
}

# ---------- SHA-256 校验 ----------

function Confirm-Sha256($file, $expected) {
    Write-Info "正在校验 SHA-256..."
    $actual = (Get-FileHash -Path $file -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $expected.ToLower()) {
        Remove-Item $file -Force -ErrorAction SilentlyContinue
        Fail "SHA-256 校验失败。`n    期望: $expected`n    实际:   $actual"
    }
}

# ---------- 用户 PATH 管理 ----------

function Add-ToUserPath($dir) {
    $current = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $dirs = @($current -split ";" | Where-Object { $_ -ne "" })
    if ($dirs -contains $dir) {
        return $false  # 已存在
    }
    $newPath = ($dirs + $dir) -join ";"
    [System.Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    return $true
}

# ---------- 从本地文件安装（离线） ----------

function Install-BinaryFile($sourceFile, $version, $sha256) {
    if (-not (Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }
    $destFile = Join-Path $InstallDir "unity.exe"

    Write-Info "正在复制二进制到 $InstallDir ..."
    Copy-Item -Path $sourceFile -Destination $destFile -Force

    if ($sha256) {
        Confirm-Sha256 $destFile $sha256
    }
    else {
        Write-Warn "缺少校验值，已跳过离线文件的 SHA-256 校验。"
    }

    # 加入用户 PATH
    $pathUpdated = Add-ToUserPath $InstallDir
    return $pathUpdated
}

# ---------- 成功输出 ----------

function Show-Success($version, $pathUpdated) {
    Write-Host ""
    Write-Host "  [成功] " -ForegroundColor Green -NoNewline
    Write-Host "Unity CLI $version 安装完成！" -ForegroundColor White
    Write-Host ""
    Write-Host "  快速上手:" -ForegroundColor White
    Write-Host "    unity --help           查看可用命令"
    Write-Host "    unity editors list     列出已安装的 Unity 编辑器"
    Write-Host "    unity install          安装 Unity 编辑器"
    Write-Host "    unity upgrade          升级 CLI 到最新版本"
    Write-Host ""

    if ($pathUpdated) {
        Write-Host "  提示: 请重启终端后再使用 " -NoNewline
        Write-Host "unity" -ForegroundColor Cyan -NoNewline
        Write-Host " 命令。"
    }
    else {
        Write-Host "  " -NoNewline
        Write-Host "unity" -ForegroundColor Cyan -NoNewline
        Write-Host " 已就绪 - 打开新终端运行 " -NoNewline
        Write-Host "unity --help" -ForegroundColor Cyan -NoNewline
        Write-Host " 即可开始。"
    }
    Write-Host ""
}

# ---------- 主流程 ----------

Write-Host ""
Write-Host "  Unity CLI 安装脚本（离线优先）" -ForegroundColor White
Write-Host ""

# 第 1 步：离线安装（优先）

$offlineBinary = Join-Path $OfflineDir "unity-windows-$arch.exe"

if (Test-Path $offlineBinary) {
    $offlineManifest = Join-Path $OfflineDir $ManifestFile
    $sha256 = $null
    $version = "offline"

    if (Test-Path $offlineManifest) {
        try {
            $m = Get-Content $offlineManifest -Raw | ConvertFrom-Json
            $binInfo = $m.binaries.$platformKey
            if ($binInfo) {
                $sha256 = $binInfo.sha256
                $version = $m.version
            }
        }
        catch {
            Write-Warn "解析离线版本清单失败，已跳过 SHA-256 校验。"
        }
    }
    else {
        Write-Warn "未找到离线版本清单，已跳过 SHA-256 校验。"
    }

    Write-Info "离线安装：版本 $version，平台 $platformKey"
    $pathUpdated = Install-BinaryFile $offlineBinary $version $sha256
    Show-Success $version $pathUpdated
    exit 0
}

# 第 2 步：在线回退（离线包缺少二进制）

Write-Warn "未找到离线二进制：$offlineBinary，回退到在线安装。"

$manifest = Get-Manifest

# 解析版本与二进制信息
$version = if ($Target -eq "latest") { $manifest.version } else { $Target }
$binaryInfo = $manifest.binaries.$platformKey

if (-not $binaryInfo) {
    $available = ($manifest.binaries | Get-Member -MemberType NoteProperty).Name -join ", "
    Fail "平台 '$platformKey' 没有可用二进制。可用平台: $available"
}

$filename = $binaryInfo.filename
$sha256   = $binaryInfo.sha256

Write-Info "正在安装版本 $version，平台 $platformKey ..."

# 下载到临时路径
$tmpFile = Join-Path $env:TEMP "unity-cli-install-$([System.Guid]::NewGuid().ToString('N')).exe"
$downloadUrl = "${CdnBase}${version}/$filename"

Get-Binary $downloadUrl $tmpFile

try {
    # 校验 SHA-256
    Confirm-Sha256 $tmpFile $sha256

    # 移动到安装位置
    if (-not (Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }
    $destFile = Join-Path $InstallDir "unity.exe"
    Move-Item -Path $tmpFile -Destination $destFile -Force

    # 加入用户 PATH
    $pathUpdated = Add-ToUserPath $InstallDir
}
catch {
    Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
    throw
}

Show-Success $version $pathUpdated
exit 0
