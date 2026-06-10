// submission/static/submission/js/final_grading_form.js

new Vue({
    el: '#final-grading-form',
    data: {
        showDeduction: false,
        showRubric: false,
        showPdfControls: true,
        pdfControlsStorageKey: 'finalGradingForm.showPdfControls',
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
        rubricState: window.finalRubricState || {},
        rubricSelectedOptionIds: Object.assign({}, (window.finalRubricState && window.finalRubricState.selected_option_ids) || {}),
        rubricNeedsReviewCriterionIds: (window.finalRubricState && window.finalRubricState.needs_review_criterion_ids) || [],
        rubricValidationAttempted: false,
        rubricSubmitError: window.finalRubricError || "",
        rubricSavedTotal: window.finalRubricSavedTotal,
        scoreDetailsTotal: window.finalScoreDetailsTotal,
        adjustmentScoreInput: String(window.finalAdjustmentScore ?? 0),
        zoomPercent: 100,
        zoomMin: 50,
        zoomMax: 200,
        zoomStep: 5,
        mainPdfRenderToken: 0,
        comparePdfRenderToken: 0,
    },
    computed: {
        rubricExists() {
            return !!this.rubricState.exists;
        },
        rubricCriteria() {
            return this.rubricState.criteria || [];
        },
        rubricVersion() {
            return this.rubricState.rubric ? this.rubricState.rubric.version : "-";
        },
        rubricScopeLabel() {
            return this.rubricState.rubric ? (this.rubricState.rubric.scope_label || '-') : '-';
        },
        rubricMissingCriterionIds() {
            return this.rubricCriteria
                .filter((criterion) => !this.rubricSelectedOptionIds[String(criterion.id)])
                .map((criterion) => String(criterion.id));
        },
        rubricNeedsReview() {
            return this.rubricNeedsReviewCriterionIds.some((criterionId) => {
                return !this.rubricSelectedOptionIds[String(criterionId)];
            });
        },
        rubricMaxOptionCount() {
            return Math.max(1, ...this.rubricCriteria.map((criterion) => (criterion.options || []).length || 0));
        },
        rubricOptionGridStyle() {
            return {
                gridTemplateColumns: `repeat(${this.rubricMaxOptionCount}, minmax(110px, 1fr))`,
            };
        },
        rubricPanelInnerStyle() {
            return {};
        },
        rubricTotalScore() {
            const optionMap = {};
            this.rubricCriteria.forEach((criterion) => {
                (criterion.options || []).forEach((option) => {
                    optionMap[String(option.id)] = Number(option.points || 0);
                });
            });
            return Object.values(this.rubricSelectedOptionIds).reduce((sum, optionId) => {
                return sum + (optionMap[String(optionId)] || 0);
            }, 0);
        },
        adjustmentScoreValue() {
            const parsed = Number(this.adjustmentScoreInput);
            return Number.isFinite(parsed) ? parsed : 0;
        },
        displayedFinalScore() {
            if (this.rubricExists) {
                return this.rubricTotalScore + this.adjustmentScoreValue;
            }
            if (this.rubricSavedTotal !== null && this.rubricSavedTotal !== '' && this.rubricSavedTotal !== undefined) {
                return this.rubricSavedTotal;
            }
            return this.scoreDetailsTotal;
        },
        serializedRubricSelection() {
            return JSON.stringify(this.rubricSelectedOptionIds || {});
        },
    },
    methods: {
        loadPdfControlsPreference() {
            try {
                const saved = window.localStorage.getItem(this.pdfControlsStorageKey);
                if (saved !== null) {
                    this.showPdfControls = saved !== 'false';
                }
            } catch (error) {
                this.showPdfControls = true;
            }
            this.$nextTick(() => {
                this.applyPdfControlsVisibility();
                this.updatePdfControlsToggleButton();
            });
        },
        savePdfControlsPreference() {
            try {
                window.localStorage.setItem(this.pdfControlsStorageKey, String(this.showPdfControls));
            } catch (error) {
                // localStorage が使えない環境では当回表示だけ維持する。
            }
        },
        applyPdfControlsVisibility() {
            const panel = this.$el ? this.$el.querySelector('.grading-control-panel') : null;
            if (panel) {
                panel.hidden = !this.showPdfControls;
            }
        },
        updatePdfControlsToggleButton() {
            const button = document.getElementById('final-pdf-controls-toggle');
            if (button) {
                button.textContent = this.showPdfControls ? '操作欄を隠す' : '操作欄を表示';
            }
        },
        togglePdfControls() {
            this.showPdfControls = !this.showPdfControls;
            this.$nextTick(() => {
                this.applyPdfControlsVisibility();
                this.updatePdfControlsToggleButton();
            });
            this.savePdfControlsPreference();
        },
        selectRubricOption(criterionId, optionId) {
            this.$set(this.rubricSelectedOptionIds, String(criterionId), optionId);
            this.rubricSubmitError = "";
        },
        isRubricOptionSelected(criterionId, optionId) {
            return String(this.rubricSelectedOptionIds[String(criterionId)]) === String(optionId);
        },
        criterionNeedsReview(criterionId) {
            return this.rubricNeedsReviewCriterionIds.includes(String(criterionId))
                && !this.rubricSelectedOptionIds[String(criterionId)];
        },
        criterionIsMissing(criterionId) {
            return this.rubricValidationAttempted && !this.rubricSelectedOptionIds[String(criterionId)];
        },
        criterionPhaseClass(title) {
            const text = String(title || '');
            if (text.includes('前半')) {
                return 'rubric-criterion-phase-first';
            }
            if (text.includes('後半')) {
                return 'rubric-criterion-phase-second';
            }
            return '';
        },
        handleRubricSubmit(event) {
            if (!this.rubricExists) {
                event.preventDefault();
                this.rubricSubmitError = "最終評価基準が未設定です。";
                return;
            }
            if (this.rubricMissingCriterionIds.length) {
                event.preventDefault();
                this.rubricValidationAttempted = true;
                this.rubricSubmitError = "未選択のクライテリアがあります。すべて選択してから保存してください。";
            }
        },
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
        toggleDeduction() {
            const nextState = !this.showDeduction;
            this.showDeduction = nextState;
            if (nextState) this.showRubric = false;
        },
        toggleRubric() {
            const nextState = !this.showRubric;
            this.showRubric = nextState;
            if (nextState) this.showDeduction = false;
        },
        handleGlobalKeydown(event) {
            if (event.key !== 'Escape') {
                return;
            }
            if (this.showRubric) {
                this.showRubric = false;
                return;
            }
            if (this.showDeduction) {
                this.showDeduction = false;
            }
        },
        toggleCompare() {
            this.showCompare = !this.showCompare;
            if (this.showCompare) {
                this.$nextTick(() => this.renderComparePdf());
            } else {
                this.comparePdfRenderToken += 1;
            }
        },
        toggleSyncScroll() {
            if (!this.showCompare) return;
            this.syncScroll = !this.syncScroll;
        },
        normalizeZoom(value) {
            const numeric = Number(value);
            if (!Number.isFinite(numeric)) return this.zoomPercent;
            const stepped = Math.round(numeric / this.zoomStep) * this.zoomStep;
            return Math.min(this.zoomMax, Math.max(this.zoomMin, stepped));
        },
        setZoom(value) {
            const next = this.normalizeZoom(value);
            if (next === this.zoomPercent) return;
            this.zoomPercent = next;
            this.$nextTick(() => {
                this.renderMainPdf();
                if (this.showCompare && this.comparePdfUrl) {
                    this.renderComparePdf();
                }
            });
        },
        zoomIn() {
            this.setZoom(this.zoomPercent + this.zoomStep);
        },
        zoomOut() {
            this.setZoom(this.zoomPercent - this.zoomStep);
        },
        getPdfRenderScale() {
            return 1.2 * (this.zoomPercent / 100);
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
            const renderToken = ++this.mainPdfRenderToken;
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
                if (renderToken !== this.mainPdfRenderToken) return;
                const baseScale = this.getPdfRenderScale();
                const dpr = Math.min(window.devicePixelRatio || 1, 2);
                const pageSlots = [];
                for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
                    const slot = document.createElement('div');
                    slot.className = 'pdf-render-page-slot';
                    container.appendChild(slot);
                    pageSlots.push(slot);
                }
                for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
                    if (renderToken !== this.mainPdfRenderToken) return;
                    const page = await pdf.getPage(pageNum);
                    if (renderToken !== this.mainPdfRenderToken) return;
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

                    pageSlots[pageNum - 1].appendChild(canvas);

                    await page.render({
                        canvasContext: ctx,
                        viewport: viewport,
                        transform: [dpr, 0, 0, dpr, 0, 0],
                    }).promise;
                }
            };

            loadingTask.promise.then(pdf => renderPagesSequentially(pdf)).catch(err => {
                if (renderToken !== this.mainPdfRenderToken) return;
                console.error('PDF 読み込みエラー:', err);
                container.innerHTML = '<p class="text-danger text-center mt-3">PDF を表示できませんでした。</p>';
            });
        },
        renderComparePdf() {
            const renderToken = ++this.comparePdfRenderToken;
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
                if (renderToken !== this.comparePdfRenderToken) return;
                const baseScale = this.getPdfRenderScale();
                const dpr = Math.min(window.devicePixelRatio || 1, 2);
                const pageSlots = [];
                for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
                    const slot = document.createElement('div');
                    slot.className = 'pdf-render-page-slot';
                    container.appendChild(slot);
                    pageSlots.push(slot);
                }
                for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
                    if (renderToken !== this.comparePdfRenderToken) return;
                    const page = await pdf.getPage(pageNum);
                    if (renderToken !== this.comparePdfRenderToken) return;
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
                    pageSlots[pageNum - 1].appendChild(canvas);
                    await page.render({ canvasContext: ctx, viewport, transform: [dpr, 0, 0, dpr, 0, 0] }).promise;
                }
            }).catch(err => {
                if (renderToken !== this.comparePdfRenderToken) return;
                console.error('Compare PDF 読み込みエラー:', err);
                container.innerHTML = '<p class="text-danger text-center mt-3">比較PDF を表示できませんでした。</p>';
            }).finally(() => {
                if (renderToken !== this.comparePdfRenderToken) return;
                this.compareLoading = false;
            });
        },
    },
    mounted() {
        this.loadPdfControlsPreference();
        const toggleButton = document.getElementById('final-pdf-controls-toggle');
        if (toggleButton) {
            toggleButton.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
                this.togglePdfControls();
            });
        }
        this.renderMainPdf();
        window.addEventListener('keydown', this.handleGlobalKeydown);
    },
    beforeDestroy() {
        this.clearSimilarityProgressTimer();
        window.removeEventListener('keydown', this.handleGlobalKeydown);
    }
});
