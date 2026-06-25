$ErrorActionPreference = 'Stop'
$root = 'D:\文件管理\东吴证券\UTR股票复现'
$html = Join-Path $root 'agent_workspace\weekly_summary_source.html'
$docx = Join-Path $root 'agent_workspace\outputs\summary.docx'
$pdf = Join-Path $root 'agent_workspace\summary_qa.pdf'

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($html, $false, $false)
    if ($doc.Tables.Count -gt 0) {
        $tableStart = $doc.Tables.Item(1).Range.Duplicate
        $tableStart.Collapse(1)
        $tableStart.InsertBreak(7)
    }
    $section = $doc.Sections.Item(1)
    $section.PageSetup.TopMargin = $word.InchesToPoints(0.85)
    $section.PageSetup.BottomMargin = $word.InchesToPoints(0.8)
    $section.PageSetup.LeftMargin = $word.InchesToPoints(1.0)
    $section.PageSetup.RightMargin = $word.InchesToPoints(1.0)
    $section.PageSetup.HeaderDistance = $word.InchesToPoints(0.492)
    $section.PageSetup.FooterDistance = $word.InchesToPoints(0.492)

    $header = $section.Headers.Item(1).Range
    $header.Text = '东吴证券 UTR 2.0 因子复现项目｜周报'
    $header.Font.NameFarEast = '微软雅黑'
    $header.Font.Name = 'Microsoft YaHei'
    $header.Font.Size = 8.5
    $header.Font.Color = 6710886
    $header.ParagraphFormat.Alignment = 2

    $footer = $section.Footers.Item(1).Range
    $footer.Text = '第 '
    $footer.Collapse(0)
    [void]$footer.Fields.Add($footer, 33)
    $footer.InsertAfter(' 页')
    $section.Footers.Item(1).Range.Font.NameFarEast = '微软雅黑'
    $section.Footers.Item(1).Range.Font.Name = 'Microsoft YaHei'
    $section.Footers.Item(1).Range.Font.Size = 9
    $section.Footers.Item(1).Range.Font.Color = 6710886
    $section.Footers.Item(1).Range.ParagraphFormat.Alignment = 2

    $doc.SaveAs2($docx, 16)
    $doc.ExportAsFixedFormat($pdf, 17)
    $pages = $doc.ComputeStatistics(2)
    $words = $doc.ComputeStatistics(0)
    $doc.Close($false)
    Write-Output "DOCX=$docx"
    Write-Output "PDF=$pdf"
    Write-Output "PAGES=$pages"
    Write-Output "WORDS=$words"
}
finally {
    $word.Quit()
}
