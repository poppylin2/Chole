# PowerShell 5+ / 7+ 均可

$OutFileMD   = "project_dump.md"
$OutFileJSON = "project_dump.json"

# 需要排除的目录（整段路径中匹配目录名即过滤，适用于任何层级）
$ExcludeDirs = @(
  '.git','__pycache__','.venv','venv','.mypy_cache','.pytest_cache',
  'node_modules','.next','dist','build','miscellenous'
)

# 仅排除“当前根目录”下的这些目录（不会影响更深层的同名目录）
$ProjectRoot = (Get-Location).Path
$ds = [IO.Path]::DirectorySeparatorChar
$ExcludeRootDirs = @('langfuse-sh')  # ← 需求：排除根目录下的 langfuse/
$ExcludeRootRegex = if ($ExcludeRootDirs.Count -gt 0) {
  # 形如 ^C:\path\to\proj\langfuse\  的前缀匹配
  $paths = $ExcludeRootDirs | ForEach-Object {
    [regex]::Escape((Join-Path $ProjectRoot $_) + $ds)
  }
  '^(?:' + ($paths -join '|') + ')'
} else { '' }

# 需要包含的文件名/扩展名模式（保持与原脚本一致）
$IncludePatterns = @(
  '*.py','*.md','*.txt','*.sh',
  '*.env','.env','*.env.*','.env.*','.env.example','*.env.example'
)

# 清理旧输出，避免把旧的 dump 内容再次读入
Remove-Item -Force -ErrorAction SilentlyContinue $OutFileMD, $OutFileJSON

# Markdown 头部
"# Project Source Dump" | Set-Content -Encoding UTF8 $OutFileMD
""                         | Add-Content -Encoding UTF8 $OutFileMD
("Generated at: {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz")) | Add-Content -Encoding UTF8 $OutFileMD
""                         | Add-Content -Encoding UTF8 $OutFileMD

# 组合用于路径过滤的正则：\(.git|node_modules|...)(\|$)
$ExcludeRegex = '\\(?:' + ($ExcludeDirs -join '|').Replace('.', '\.') + ')(?:\\|$)'

# 收集文件
$files =
  Get-ChildItem -Recurse -File -Force |
  Where-Object {
    # 排除在指定目录中的文件（任意层级）
    $_.FullName -notmatch $ExcludeRegex
  } |
  Where-Object {
    # 仅排除根目录下的特定目录（如 .\langfuse\**）
    if ([string]::IsNullOrEmpty($ExcludeRootRegex)) { $true }
    else { $_.FullName -notmatch $ExcludeRootRegex }
  } |
  Where-Object {
    # 只要匹配包含模式之一
    $name = $_.Name
    $IncludePatterns | Where-Object { $name -like $_ } | Measure-Object | Select-Object -ExpandProperty Count
  } |
  Where-Object {
    # 排除本脚本的产物，避免自我包含
    $_.Name -ne $OutFileMD -and $_.Name -ne $OutFileJSON
  } |
  Sort-Object FullName

# 记录 JSON 的对象列表
$records = New-Object System.Collections.Generic.List[object]

foreach ($f in $files) {
  # 相对路径（去掉开头 .\）
  $rel = (Resolve-Path -Relative $f.FullName) -replace '^\.(?:\\|/)', ''

  # 语言围栏映射
  $fenceLang = switch -Wildcard ($f.Name) {
    '*.py'        { 'python'; break }
    '*.sh'        { 'bash';   break }
    '*.md'        { 'markdown'; break }
    '*.txt'       { ''; break }
    '*.env'       { 'env'; break }
    '*.env.*'     { 'env'; break }
    '.env'        { 'env'; break }
    '.env.*'      { 'env'; break }
    '.env.example'{ 'env'; break }
    '*.env.example' { 'env'; break }
    default       { '' }
  }

  # 分隔与标题
  "" | Add-Content -Encoding UTF8 $OutFileMD
  "==============================" | Add-Content -Encoding UTF8 $OutFileMD
  "FILE: $rel" | Add-Content -Encoding UTF8 $OutFileMD
  "==============================" | Add-Content -Encoding UTF8 $OutFileMD
  "" | Add-Content -Encoding UTF8 $OutFileMD

  # 代码围栏
  if ([string]::IsNullOrEmpty($fenceLang)) {
    '```' | Add-Content -Encoding UTF8 $OutFileMD
  } else {
    ('```' + $fenceLang) | Add-Content -Encoding UTF8 $OutFileMD
  }

  # 文件内容（按原样写入）
  Get-Content -Path $f.FullName -Raw -Encoding UTF8 | Add-Content -Encoding UTF8 $OutFileMD
  "" | Add-Content -Encoding UTF8 $OutFileMD
  '```' | Add-Content -Encoding UTF8 $OutFileMD
  "" | Add-Content -Encoding UTF8 $OutFileMD

  # JSON 记录项
  $bytes = $f.Length
  $kb    = [int][math]::Ceiling($bytes / 1024.0)
  $hash  = (Get-FileHash -Algorithm SHA256 -Path $f.FullName).Hash

  $records.Add([pscustomobject]@{
    path       = $rel
    extension  = $f.Extension
    bytes      = $bytes
    kb         = $kb
    sha256     = $hash
    modifiedAt = $f.LastWriteTimeUtc.ToString("o")
  })
}

# 写出 JSON（UTF-8 无 BOM）
$records | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $OutFileJSON

Write-Host "Done. Wrote to $OutFileMD and $OutFileJSON"
