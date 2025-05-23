new Vue({
  el: '#vue-submit-app',
  data: {
    pdfUrl: null,
    scrollAtEnd: false,
    formData: null,
    csrfToken: document.querySelector('input[name="csrfmiddlewaretoken"]').value,
    date: document.querySelector('input[name="date"]') ? document.querySelector('input[name="date"]').value : "",
    pdfNumPages: 0,
    reportType: "",        // ← 追加
    experimentNumber: "",  // ← 追加
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
        this.formData.append('report_type', this.reportType);
        this.formData.append('experiment_number', this.experimentNumber);
        this.$nextTick(this.renderAllPages);
      } else {
        alert("PDFファイルのみ選択してください。");
        this.pdfUrl = null;
      }
    },
    renderAllPages() {
      if (!this.pdfUrl) return;
      // PDF.js worker設定
      if (window.pdfjsLib) {
        pdfjsLib.GlobalWorkerOptions.workerSrc =
          "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
        pdfjsLib.getDocument(this.pdfUrl).promise.then(pdf => {
          this.pdfNumPages = pdf.numPages;
          // containerを空に
          const container = document.getElementById('pdf-preview-container');
          container.innerHTML = '';
          // 全ページcanvas生成
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
          // 全ページ描画後にスクロール監視
          Promise.all(renderPromises).then(() => {
            this.scrollAtEnd = false;
            container.addEventListener('scroll', this.onScrollPdfPreview);
            // 初回スクロール判定
            this.onScrollPdfPreview();
          });
        });
      }
    },
    onScrollPdfPreview() {
      const container = document.getElementById('pdf-preview-container');
      // スクロールが最下部に到達したらボタン有効化
      if (!container) return;
      const isAtEnd = container.scrollTop + container.clientHeight >= container.scrollHeight - 5;
      this.scrollAtEnd = isAtEnd;
    },
    onConfirm() {
      // DB登録
      this.formData.set('report_type', this.reportType);
      this.formData.set('experiment_number', this.experimentNumber);
      for (let pair of this.formData.entries()) {
        console.log(pair[0] + ': ' + pair[1]);
      }
      fetch("", {
        method: "POST",
        body: this.formData,
        headers: { "X-Requested-With": "XMLHttpRequest" }
      }).then(res => res.json())
        .then(data => {
          if (data.status === 'success') {
            window.location.href = data.redirect_url;
          } else {
            alert(data.message || '提出に失敗しました');
          }
        });
    }
  }
});