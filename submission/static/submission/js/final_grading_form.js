// submission/static/submission/js/final_grading_form.js

new Vue({
  el: '#final-grading-form',
  data: {
    showScore: false,
  },
  methods: {
    toggleScore() {
      this.showScore = !this.showScore;
    },
  },
  mounted() {
    const url = window.pdf_url;
    const container = document.getElementById('final-pdf-pages');

    pdfjsLib.getDocument(url).promise.then(pdf => {
      // 全ページ描画
      for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
        pdf.getPage(pageNum).then(page => {
          const viewport = page.getViewport({ scale: 1.2 });

          const canvas = document.createElement('canvas');
          const ctx = canvas.getContext('2d');
          canvas.style.display = 'block';
          canvas.style.margin = '0 auto 16px auto';

          canvas.width = viewport.width;
          canvas.height = viewport.height;

          container.appendChild(canvas);

          page.render({
            canvasContext: ctx,
            viewport: viewport,
          });
        });
      }
    }).catch(err => {
      console.error('PDF 読み込みエラー:', err);
      container.innerHTML = '<p class="text-danger text-center mt-3">PDF を表示できませんでした。</p>';
    });
  }
});
