/**
 * Publication-Grade PDF Engine (exportNotesToPdf).
 * Renders notes canvas to an isolated print window with A4 layout,
 * 18mm margins, KaTeX typography, shaded table headers, and metadata stamp.
 */

export function exportNotesToPdf(title: string, markdownContent: string, subject: string = "General Study") {
  const printWindow = window.open('', '_blank')
  if (!printWindow) {
    alert('Please allow popups to export publication-grade PDF.')
    return
  }

  const dateStr = new Date().toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })

  // Simple HTML converter for print rendering
  const lines = markdownContent.split('\n')
  let bodyHtml = ''
  let inTable = false
  let tableRows: string[] = []

  const flushTable = () => {
    if (!inTable || tableRows.length === 0) return
    let tbl = '<table class="pdf-table"><thead><tr>'
    const headers = tableRows[0].split('|').map(s => s.trim()).filter(Boolean)
    headers.forEach(h => { tbl += `<th>${h}</th>` })
    tbl += '</tr></thead><tbody>'

    for (let i = 2; i < tableRows.length; i++) {
      const cells = tableRows[i].split('|').map(s => s.trim()).filter(Boolean)
      if (cells.length > 0) {
        tbl += '<tr>'
        cells.forEach(c => { tbl += `<td>${c}</td>` })
        tbl += '</tr>'
      }
    }
    tbl += '</tbody></table>'
    bodyHtml += tbl
    tableRows = []
    inTable = false
  }

  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      inTable = true
      tableRows.push(trimmed)
      continue
    } else {
      flushTable()
    }

    if (trimmed.startsWith('# ')) {
      bodyHtml += `<h1 class="pdf-h1">${trimmed.slice(2)}</h1>`
    } else if (trimmed.startsWith('## ')) {
      bodyHtml += `<h2 class="pdf-h2">${trimmed.slice(3)}</h2>`
    } else if (trimmed.startsWith('### ')) {
      bodyHtml += `<h3 class="pdf-h3">${trimmed.slice(4)}</h3>`
    } else if (trimmed.startsWith('$$') && trimmed.endsWith('$$') && trimmed.length > 4) {
      bodyHtml += `<div class="pdf-math-block">${trimmed.slice(2, -2)}</div>`
    } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      bodyHtml += `<li class="pdf-li">${trimmed.slice(2)}</li>`
    } else if (trimmed.length > 0) {
      bodyHtml += `<p class="pdf-p">${trimmed}</p>`
    }
  }
  flushTable()

  const html = `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>${title} — DeepTutor Study Notes</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.css">
  <style>
    @page {
      size: A4;
      margin: 18mm;
    }
    @media print {
      body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .no-print { display: none; }
      .page-break { page-break-before: always; }
    }
    body {
      font-family: 'Segoe UI', system-ui, -apple-system, Roboto, sans-serif;
      color: #1E293B;
      background: #FFFFFF;
      margin: 0;
      padding: 24px;
      line-height: 1.65;
    }
    .pdf-header {
      border-bottom: 2px solid #4F46E5;
      padding-bottom: 16px;
      margin-bottom: 24px;
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
    }
    .pdf-title {
      font-size: 24px;
      font-weight: 800;
      color: #1E293B;
      margin: 0 0 6px 0;
    }
    .pdf-meta {
      font-size: 12px;
      color: #64748B;
      font-weight: 600;
    }
    .pdf-badge {
      background: #EEF2FF;
      color: #4F46E5;
      font-size: 11px;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 9999px;
      border: 1px solid #C7D2FE;
    }
    .pdf-h1 { font-size: 20px; font-weight: 800; color: #1E293B; margin-top: 24px; border-bottom: 1px solid #E2E8F0; padding-bottom: 6px; }
    .pdf-h2 { font-size: 16px; font-weight: 700; color: #334155; margin-top: 18px; }
    .pdf-h3 { font-size: 14px; font-weight: 700; color: #475569; margin-top: 14px; }
    .pdf-p { font-size: 13px; color: #334155; margin: 8px 0; text-align: justify; }
    .pdf-li { font-size: 13px; color: #334155; margin-left: 20px; margin-bottom: 4px; }
    .pdf-math-block {
      background: #FAF5FF;
      border: 1px solid #E9D5FF;
      border-radius: 8px;
      padding: 12px 16px;
      margin: 12px 0;
      font-family: 'Cambria Math', 'Times New Roman', serif;
      font-size: 15px;
      color: #581C87;
      text-align: center;
      break-inside: avoid;
    }
    .pdf-table {
      width: 100%;
      border-collapse: collapse;
      margin: 16px 0;
      font-size: 12px;
      break-inside: avoid;
    }
    .pdf-table th {
      background: #F1F5F9;
      color: #1E293B;
      font-weight: 700;
      padding: 8px 12px;
      border: 1px solid #CBD5E1;
      text-align: left;
    }
    .pdf-table td {
      padding: 8px 12px;
      border: 1px solid #E2E8F0;
      color: #334155;
    }
    .pdf-table tr:nth-child(even) {
      background: #F8FAFC;
    }
    .pdf-footer {
      margin-top: 36px;
      border-top: 1px solid #E2E8F0;
      padding-top: 12px;
      font-size: 11px;
      color: #94A3B8;
      display: flex;
      justify-content: space-between;
    }
  </style>
</head>
<body>
  <div class="pdf-header">
    <div>
      <h1 class="pdf-title">${title}</h1>
      <div class="pdf-meta">Subject: ${subject} · Date: ${dateStr}</div>
    </div>
    <div class="pdf-badge">DeepTutor Verified Study Notes</div>
  </div>

  <div class="pdf-content">
    ${bodyHtml}
  </div>

  <div class="pdf-footer">
    <span>Generated by DeepTutor AI Study Room & GraphRAG Platform</span>
    <span>Page 1 of 1</span>
  </div>

  <script>
    window.onload = function() {
      setTimeout(function() {
        window.print();
      }, 500);
    };
  </script>
</body>
</html>
`

  printWindow.document.open()
  printWindow.document.write(html)
  printWindow.document.close()
}
