document.addEventListener('DOMContentLoaded', function() {
    pdfjsLib.GlobalWorkerOptions.workerSrc =
      "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
  
    const url = window.PDF_URL;
    let pdfDoc = null, pageNum = 1;
    let totalPages = 0;
    let viewedPages = new Set();
  
    function renderPage(num) {
      pdfDoc.getPage(num).then(function(page) {
        const viewport = page.getViewport({ scale: 1.15 });
        const canvas = document.createElement('canvas');
        canvas.className = "mb-3";
        const ctx = canvas.getContext('2d');
        canvas.height = viewport.height;
        canvas.width = viewport.width;
        document.getElementById('pdf-container').appendChild(canvas);
  
        page.render({ canvasContext: ctx, viewport: viewport }).promise.then(function() {
          viewedPages.add(num);
          // 最後のページを表示したら確定ボタンを表示
          if (viewedPages.size === totalPages) {
            document.getElementById('confirmBtn').style.display = '';
          }
        });
      });
    }
  
    if (url) {
      pdfjsLib.getDocument(url).promise.then(function(pdfDoc_) {
        pdfDoc = pdfDoc_;
        totalPages = pdfDoc.numPages;
        for (let i = 1; i <= totalPages; i++) {
          renderPage(i);
        }
        if (totalPages === 1) {
          document.getElementById('confirmBtn').style.display = '';
        }
      });
    }
  });
  