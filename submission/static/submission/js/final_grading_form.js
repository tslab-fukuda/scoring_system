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
        similarityLoading: false,
        similarityProgress: 0,
        similarityProgressTimer: null,
        similarityChecked: false,
        similarityResults: [],
        similarityMessage: "",
        selectedSimilaritySubmissionId: null,
        selectedSimilarityRow: null,
        sectionExpandState: {},
        detailAccordionState: {},
        syncingScroll: false,
    },
    methods: {
        riskLabel(level) {
            if (level === 'high') return '高';
            if (level === 'medium') return '中';
            if (level === 'low') return '低';
            return '-';
        },
        riskClass(level) {
            if (level === 'high') return 'text-bg-danger';
            if (level === 'medium') return 'text-bg-warning';
            if (level === 'low') return 'text-bg-secondary';
            return 'text-bg-light';
        },
        sectionBadgeClass(level) {
            if (level === 'high') return 'text-bg-danger';
            if (level === 'medium') return 'text-bg-warning';
            return 'text-bg-secondary';
        },
        sectionExpandKey(row, title) {
            return `${row.submission_id}:${title}`;
        },
        isSectionExpanded(row, title) {
            const key = this.sectionExpandKey(row, title);
            return !!this.sectionExpandState[key];
        },
        toggleSectionExpand(row, title) {
            const key = this.sectionExpandKey(row, title);
            this.$set(this.sectionExpandState, key, !this.sectionExpandState[key]);
        },
        detailAccordionKey(row, title) {
            return `${row.submission_id}:${title}`;
        },
        isDetailAccordionOpen(row, title) {
            const key = this.detailAccordionKey(row, title);
            return !!this.detailAccordionState[key];
        },
        toggleDetailAccordion(row, title) {
            const rowPrefix = `${row.submission_id}:`;
            Object.keys(this.detailAccordionState).forEach((key) => {
                if (key.startsWith(rowPrefix)) {
                    this.$set(this.detailAccordionState, key, false);
                }
            });
            const key = this.detailAccordionKey(row, title);
            const nextState = !this.detailAccordionState[key];
            this.$set(this.detailAccordionState, key, nextState);
        },
        visibleSectionMatches(row, detail) {
            if (!detail) return [];
            if (this.isSectionExpanded(row, detail.title)) {
                return detail.all_matches || [];
            }
            return detail.top_matches || [];
        },
        openSimilarityCompare(row) {
            this.selectedSimilaritySubmissionId = row.submission_id;
            this.selectedSimilarityRow = row;
            this.sectionExpandState = {};
            this.detailAccordionState = {};
            if (!row.pdf_url) return;
            this.comparePdfUrl = row.pdf_url;
            const dateLabel = row.submitted_at || "";
            this.compareLabel = [row.student_name || "", dateLabel].filter(Boolean).join(" ");
            this.showCompare = true;
            this.$nextTick(() => this.renderComparePdf());
        },
        startSimilarityProgress() {
            this.clearSimilarityProgressTimer();
            this.similarityProgress = 5;
            this.similarityProgressTimer = setInterval(() => {
                if (!this.similarityLoading) return;
                const remaining = 95 - this.similarityProgress;
                if (remaining <= 0) return;
                const step = Math.max(0.5, remaining * 0.08);
                this.similarityProgress = Math.min(95, this.similarityProgress + step);
            }, 200);
        },
        clearSimilarityProgressTimer() {
            if (this.similarityProgressTimer) {
                clearInterval(this.similarityProgressTimer);
                this.similarityProgressTimer = null;
            }
        },
        runSimilarityCheck() {
            if (this.similarityLoading) return;
            this.similarityLoading = true;
            this.startSimilarityProgress();
            fetch(`/submission/submission_similarity_api/?submission_id=${encodeURIComponent(window.submissionId)}`)
                .then(res => res.json())
                .then(data => {
                    if (data.status !== 'success') {
                        alert(data.message || 'コピペチェックに失敗しました');
                        return;
                    }
                    this.similarityChecked = true;
                    this.similarityResults = data.results || [];
                    this.similarityMessage = `${data.message || ''}（比較件数: ${data.checked_count || 0}）`;
                    this.selectedSimilaritySubmissionId = null;
                    this.selectedSimilarityRow = null;
                    this.sectionExpandState = {};
                    this.detailAccordionState = {};
                })
                .catch(() => {
                    alert('コピペチェックに失敗しました');
                })
                .finally(() => {
                    this.clearSimilarityProgressTimer();
                    this.similarityProgress = 100;
                    setTimeout(() => {
                        this.similarityLoading = false;
                        this.similarityProgress = 0;
                    }, 180);
                });
        },
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
                const baseScale = 1.2;
                const dpr = Math.min(window.devicePixelRatio || 1, 2);
                for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
                    const page = await pdf.getPage(pageNum);
                    const viewport = page.getViewport({ scale: baseScale });
                    const cssWidth = viewport.width;
                    const cssHeight = viewport.height;

                    const canvas = document.createElement('canvas');
                    const ctx = canvas.getContext('2d');
                    canvas.style.display = 'block';
                    canvas.style.margin = '0 auto 16px auto';

                    canvas.width = Math.floor(cssWidth * dpr);
                    canvas.height = Math.floor(cssHeight * dpr);
                    canvas.style.width = `${cssWidth}px`;
                    canvas.style.height = `${cssHeight}px`;

                    container.appendChild(canvas);

                    await page.render({
                        canvasContext: ctx,
                        viewport: viewport,
                        transform: [dpr, 0, 0, dpr, 0, 0],
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
                const baseScale = 1.2;
                const dpr = Math.min(window.devicePixelRatio || 1, 2);
                for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
                    const page = await pdf.getPage(pageNum);
                    const viewport = page.getViewport({ scale: baseScale });
                    const cssWidth = viewport.width;
                    const cssHeight = viewport.height;
                    const canvas = document.createElement('canvas');
                    const ctx = canvas.getContext('2d');
                    canvas.style.display = 'block';
                    canvas.style.margin = '0 auto 16px auto';
                    canvas.width = Math.floor(cssWidth * dpr);
                    canvas.height = Math.floor(cssHeight * dpr);
                    canvas.style.width = `${cssWidth}px`;
                    canvas.style.height = `${cssHeight}px`;
                    container.appendChild(canvas);
                    await page.render({ canvasContext: ctx, viewport, transform: [dpr, 0, 0, dpr, 0, 0] }).promise;
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
    },
    beforeDestroy() {
        this.clearSimilarityProgressTimer();
    }
});
