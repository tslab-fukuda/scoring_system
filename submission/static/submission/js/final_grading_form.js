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
        const CMAP_URL = "https://cdn.jsdelivr.net/npm/pdfjs-dist@2.16.105/cmaps/";
        const STANDARD_FONT_URL = "https://cdn.jsdelivr.net/npm/pdfjs-dist@2.16.105/standard_fonts/";
        pdfjsLib.GlobalWorkerOptions.workerSrc =
            "https://cdn.jsdelivr.net/npm/pdfjs-dist@2.16.105/build/pdf.worker.min.js";


        const loadingTask = pdfjsLib.getDocument({
            url: url,
            cMapUrl: CMAP_URL,
            cMapPacked: true,
            standardFontDataUrl: STANDARD_FONT_URL,
        });

        const renderPagesSequentially = async (pdf) => {
            for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
                const page = await pdf.getPage(pageNum);
                const viewport = page.getViewport({ scale: 1.2 });

                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');
                canvas.style.display = 'block';
                canvas.style.margin = '0 auto 16px auto';

                canvas.width = viewport.width;
                canvas.height = viewport.height;

                container.appendChild(canvas);

                await page.render({
                    canvasContext: ctx,
                    viewport: viewport,
                }).promise;
            }
        };

        loadingTask.promise.then(pdf => renderPagesSequentially(pdf)).catch(err => {
            console.error('PDF 読み込みエラー:', err);
            container.innerHTML = '<p class="text-danger text-center mt-3">PDF を表示できませんでした。</p>';
        });
    }
});
