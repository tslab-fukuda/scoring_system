document.addEventListener('DOMContentLoaded', function () {
    new Vue({
      el: "#confirm-app",
      data: {
        scrolledToBottom: false,
        pdfUrl: window.PDF_URL,
      },
      mounted() {
        if (this.pdfUrl) {
          this.loadPdf();
          this.setupScrollHandler();
        }
      },
      methods: {
        loadPdf() {
          const container = this.$refs.pdfPages;
          pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
          pdfjsLib.getDocument(this.pdfUrl).promise.then(pdfDoc => {
            for (let pageNum = 1; pageNum <= pdfDoc.numPages; pageNum++) {
              pdfDoc.getPage(pageNum).then(page => {
                const viewport = page.getViewport({ scale: 1.1 });
                const canvas = document.createElement('canvas');
                canvas.width = viewport.width;
                canvas.height = viewport.height;
                container.appendChild(canvas);
                page.render({
                  canvasContext: canvas.getContext('2d'),
                  viewport: viewport
                });
              });
            }
          });
        },
        setupScrollHandler() {
          // .pdf-viewerが一番外側のスクロール対象
          const viewer = document.querySelector('.pdf-viewer');
          if (!viewer) return;
          viewer.addEventListener('scroll', () => {
            if (viewer.scrollTop + viewer.clientHeight >= viewer.scrollHeight - 20) {
              this.scrolledToBottom = true;
            }
          });
        }
      }
    });
  });