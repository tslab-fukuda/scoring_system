new Vue({
  el: '#vue-submit-app',
  data: {
    pdfUrl: null,
    scrollAtEnd: false,
    formData: null,
    csrfToken: document.querySelector('input[name="csrfmiddlewaretoken"]').value,
    date: document.querySelector('input[name="date"]') ? document.querySelector('input[name="date"]').value : "",
    pdfNumPages: 0,
  },
  methods: {
    onFileChange(e) {
      const file = e.target.files[0];
      if (file && file.type === "application/pdf") {
        this.pdfUrl = URL.createObjectURL(file);
        this.formData = new FormData();
        this.formData.append('csrfmiddlewaretoken', this.csrfToken);
        this.formData.append('file', file);
        this.formData.append('date', this.date);
        this.$nextTick(this.renderAllPages);
      } else {
        alert("PDFファイルのみ選択してください。");
        this.pdfUrl = null;
      }
    },
    renderAllPages() {
      if (!this.pdfUrl) return;
      if (window.pdfjsLib) {
        pdfjsLib.GlobalWorkerOptions.workerSrc =
          "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
        pdfjsLib.getDocument(this.pdfUrl).promise.then(pdf => {
          this.pdfNumPages = pdf.numPages;
          const container = document.getElementById('pdf-preview-container');
          container.innerHTML = '';
          let renderPromises = [];
          for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
            renderPromises.push(
              pdf.getPage(pageNum).then(page => {
                let viewport = page.getViewport({ scale: 1.2 });
                let canvas = document.createElement('canvas');
                canvas.style.display = 'block';
                canvas.style.margin = '0 auto 20px auto';
                canvas.width = viewport.width;
                canvas.height = viewport.height;
                container.appendChild(canvas);
                let ctx = canvas.getContext('2d');
                let renderContext = { canvasContext: ctx, viewport: viewport };
                return page.render(renderContext).promise;
              })
            );
          }
          Promise.all(renderPromises).then(() => {
            this.scrollAtEnd = false;
            container.addEventListener('scroll', this.onScrollPdfPreview);
            this.onScrollPdfPreview();
          });
        });
      }
    },
    onScrollPdfPreview() {
      const container = document.getElementById('pdf-preview-container');
      if (!container) return;
      const isAtEnd = container.scrollTop + container.clientHeight >= container.scrollHeight - 5;
      this.scrollAtEnd = isAtEnd;
    },
    onConfirm() {
      fetch("", {
        method: "POST",
        body: this.formData,
        headers: { "X-Requested-With": "XMLHttpRequest" }
      }).then(res => res.json())
        .then(data => {
          if (data.status === 'success' && data.redirect_url) {
            window.location.href = data.redirect_url;
          } else {
            alert(data.message || '提出に失敗しました');
          }
        }).catch(() => alert('通信エラーが発生しました'));
    }
  }
});