// submission/static/submission/js/final_grading_form.js

new Vue({
    el: '#final-grading-form',
    data: {
        showScore: false,
        showCompare: false,
        syncScroll: true,
        compareUserId: "",
        compareCandidates: window.compareCandidates || [],
        comparePdfUrl: "",
        compareLabel: "",
        compareLoading: false,
        syncingScroll: false,
    },
    methods: {
        toggleScore() {
            this.showScore = !this.showScore;
        },
        toggleCompare() {
            this.showCompare = !this.showCompare;
            if (this.showCompare) {
                this.$nextTick(() => this.renderComparePdf());
            }
        },
        toggleSyncScroll() {
            if (!this.showCompare) return;
            this.syncScroll = !this.syncScroll;
        },
        onMainScroll(e) {
            if (!this.showCompare || !this.syncScroll || this.syncingScroll) return;
            const target = this.$refs.comparePdfArea;
            if (!target) return;
            this.syncingScroll = true;
            target.scrollTop = e.target.scrollTop;
            setTimeout(() => { this.syncingScroll = false; }, 0);
        },
        onCompareScroll(e) {
            if (!this.showCompare || !this.syncScroll || this.syncingScroll) return;
            const target = this.$refs.pdfArea;
            if (!target) return;
            this.syncingScroll = true;
            target.scrollTop = e.target.scrollTop;
            setTimeout(() => { this.syncingScroll = false; }, 0);
        },
        loadCompareUser() {
            if (!this.compareUserId) {
                this.comparePdfUrl = "";
                this.compareLabel = "";
                this.compareLoading = false;
                this.renderComparePdf();
                return;
            }
            this.compareLoading = true;
            const params = new URLSearchParams({
                submission_id: window.submissionId || "",
                user_id: this.compareUserId
            });
            fetch('/submission/compare_user_submission/?' + params.toString())
                .then(res => res.json())
                .then(data => {
                    if (data.status !== 'ok') {
                        this.comparePdfUrl = "";
                        this.compareLabel = "";
                        return;
                    }
                    this.comparePdfUrl = data.pdf_url || "";
                    const name = data.full_name || "";
                    const submitted = data.submitted_at || "";
                    this.compareLabel = [name, submitted].filter(Boolean).join(' ');
                })
                .catch(err => {
                    console.error(err);
                    this.comparePdfUrl = "";
                    this.compareLabel = "";
                })
                .finally(() => {
                    this.compareLoading = false;
                    if (this.showCompare) {
                        this.$nextTick(() => this.renderComparePdf());
                    }
                });
        },
        renderMainPdf() {
            const url = window.pdf_url;
            const container = this.$refs.pdfArea;
            if (!container) return;
            container.innerHTML = '';
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
        },
        renderComparePdf() {
            const container = this.$refs.comparePdfPages;
            if (!container) return;
            container.innerHTML = '';
            if (!this.comparePdfUrl) {
                this.compareLoading = false;
                return;
            }
            this.compareLoading = true;
            const CMAP_URL = "https://cdn.jsdelivr.net/npm/pdfjs-dist@2.16.105/cmaps/";
            const STANDARD_FONT_URL = "https://cdn.jsdelivr.net/npm/pdfjs-dist@2.16.105/standard_fonts/";
            const loadingTask = pdfjsLib.getDocument({
                url: this.comparePdfUrl,
                cMapUrl: CMAP_URL,
                cMapPacked: true,
                standardFontDataUrl: STANDARD_FONT_URL,
            });
            loadingTask.promise.then(async pdf => {
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
                    await page.render({ canvasContext: ctx, viewport }).promise;
                }
            }).catch(err => {
                console.error('Compare PDF 読み込みエラー:', err);
                container.innerHTML = '<p class="text-danger text-center mt-3">比較PDF を表示できませんでした。</p>';
            }).finally(() => {
                this.compareLoading = false;
            });
        },
    },
    mounted() {
        this.renderMainPdf();
    }
});
