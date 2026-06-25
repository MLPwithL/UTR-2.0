$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$root = 'D:\文件管理\东吴证券\UTR股票复现'
$docx = Join-Path $root 'agent_workspace\outputs\summary.docx'
$outDir = Join-Path $root 'agent_workspace\summary_qa_pages'
[System.IO.Directory]::CreateDirectory($outDir) | Out-Null

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($docx, $false, $true)
    $pageCount = $doc.ComputeStatistics(2)
    for ($page = 1; $page -le $pageCount; $page++) {
        $startRange = $doc.GoTo(1, 1, $page)
        $start = $startRange.Start
        if ($page -lt $pageCount) {
            $nextRange = $doc.GoTo(1, 1, $page + 1)
            $end = $nextRange.Start - 1
        } else {
            $end = $doc.Content.End - 1
        }
        $range = $doc.Range($start, $end)
        $emfPath = Join-Path $outDir ("page-{0}.emf" -f $page)
        $bytes = $range.EnhMetaFileBits
        [System.IO.File]::WriteAllBytes($emfPath, $bytes)
        $image = [System.Drawing.Image]::FromFile($emfPath)
        $path = Join-Path $outDir ("page-{0}.png" -f $page)
        $image.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
        $image.Dispose()
        Remove-Item -LiteralPath $emfPath
        Write-Output $path
    }
    $doc.Close($false)
}
finally {
    $word.Quit()
}
