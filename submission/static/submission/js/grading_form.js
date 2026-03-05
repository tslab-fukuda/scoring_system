new Vue({
    el: '#grading-form',
    data: {
        tool: 'pen',
        showScore: false,
        scoreItems: [],
        hiddenScoreItems: [],
        pdfPages: [],
        loadedPages: {},
        drawing: false,
        lastX: 0,
        lastY: 0,
        currentPage: null,
        drawData: [],
        undoStack: [],
        stamps: [],
        selectedStamp: "",
        penWidth: 2,
        highlightWidth: 10,
        showCompare: false,
        syncScroll: true,
        comparePdfUrl: window.comparePdfUrl || "",
        compareSubmittedAt: window.compareSubmittedAt || "",
        compareLoading: false,
        compareRendered: false,
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
        mainLastScrollTop: 0,
        compareLastScrollTop: 0,
        pageMeta: {},
        activePointerId: null,
        activePointerType: "",
        touchPoints: {},
        twoFingerScroll: false,
        lastTwoFingerY: 0,
        previousOverflowY: "",
        lastPenTime: 0,
        useTouchType: false,
        directScrollActive: false,
        directScrollLastX: 0,
        directScrollLastY: 0,
        zoomPercent: 100,
        zoomMin: 50,
        zoomMax: 200,
        zoomStep: 5,
        pdfDoc: null,
    },
    computed: {
        totalScore() {
            return this.scoreItems.reduce((acc, item) => acc + (item.value * (item.weight || 1)), 0);
        }
    },
    methods: {
        getCanvasMeta(idx, canvas) {
            const meta = this.pageMeta[idx];
            if (meta) return meta;
            const rect = canvas.getBoundingClientRect();
            return {
                cssWidth: rect.width || canvas.clientWidth || canvas.width,
                cssHeight: rect.height || canvas.clientHeight || canvas.height,
                dpr: 1,
            };
        },
        getCanvasPoint(idx, canvas, e) {
            const rect = canvas.getBoundingClientRect();
            const meta = this.getCanvasMeta(idx, canvas);
            return {
                x: e.clientX - rect.left,
                y: e.clientY - rect.top,
                cssWidth: meta.cssWidth || rect.width,
                cssHeight: meta.cssHeight || rect.height,
                dpr: meta.dpr || 1,
            };
        },
        getTouchAverageY() {
            const points = Object.values(this.touchPoints || {});
            if (points.length === 0) return 0;
            const total = points.reduce((sum, point) => sum + point.y, 0);
            return total / points.length;
        },
        getTouchesByType(e, desiredType) {
            const touches = Array.from((e && e.touches) || []);
            return touches.filter(touch => {
                const type = touch.touchType || 'direct';
                return type === desiredType;
            });
        },
        getTouchAveragePoint(touches) {
            if (!touches || touches.length === 0) return { x: 0, y: 0 };
            const total = touches.reduce((sum, touch) => {
                sum.x += touch.clientX;
                sum.y += touch.clientY;
                return sum;
            }, { x: 0, y: 0 });
            return {
                x: total.x / touches.length,
                y: total.y / touches.length,
            };
        },
        makeStylusEvent(touch) {
            return {
                pointerType: 'pen',
                pointerId: touch.identifier,
                clientX: touch.clientX,
                clientY: touch.clientY,
                cancelable: true,
                __fromTouch: true,
            };
        },
        resolvePointerType(e) {
            const rawType = e && e.pointerType ? e.pointerType : 'mouse';
            if (rawType !== 'touch') return rawType;
            if (!this.isDrawable()) return rawType;
            const now = Date.now();
            if (this.isStylusEvent(e)) return 'pen';
            if (now - this.lastPenTime < 800) return 'pen';
            return rawType;
        },
        isStylusEvent(e) {
            if (!e) return false;
            if (e.pointerType === 'pen') return true;
            if (e.pointerType !== 'touch') return false;
            const tiltX = Math.abs(e.tiltX || 0);
            const tiltY = Math.abs(e.tiltY || 0);
            if (tiltX > 0 || tiltY > 0) return true;
            const width = e.width || 0;
            const height = e.height || 0;
            if (width > 0 && height > 0 && width <= 10 && height <= 10) return true;
            return false;
        },
        onTouchStart(idx, e) {
            if (!this.useTouchType) return;
            const stylusTouches = this.getTouchesByType(e, 'stylus');
            if (stylusTouches.length > 0) {
                const stylusEvent = this.makeStylusEvent(stylusTouches[0]);
                this.startDraw(idx, stylusEvent);
                if (e.cancelable) e.preventDefault();
                if (e.stopPropagation) e.stopPropagation();
            }
        },
        onTouchMove(idx, e) {
            if (!this.useTouchType) return;
            const stylusTouches = this.getTouchesByType(e, 'stylus');
            if (stylusTouches.length > 0) {
                const stylusEvent = this.makeStylusEvent(stylusTouches[0]);
                this.draw(idx, stylusEvent);
                if (e.cancelable) e.preventDefault();
                if (e.stopPropagation) e.stopPropagation();
            }
        },
        onTouchEnd(idx, e) {
            if (!this.useTouchType) return;
            const remainingStylus = this.getTouchesByType(e, 'stylus');
            if (remainingStylus.length === 0) {
                this.stopDraw(idx, { pointerType: 'pen', pointerId: this.activePointerId, cancelable: true, __fromTouch: true });
                if (e && e.cancelable) e.preventDefault();
                if (e && e.stopPropagation) e.stopPropagation();
            }
        },
        onPdfTouchStart(e) {
            if (!this.useTouchType) return;
            const stylusTouches = this.getTouchesByType(e, 'stylus');
            if (stylusTouches.length > 0) {
                if (e.cancelable) e.preventDefault();
                return;
            }
            const directTouches = this.getTouchesByType(e, 'direct');
            if (directTouches.length >= 2) {
                this.directScrollActive = true;
                const point = this.getTouchAveragePoint(directTouches);
                this.directScrollLastX = point.x;
                this.directScrollLastY = point.y;
            }
            if (e.cancelable) e.preventDefault();
        },
        onPdfTouchMove(e) {
            if (!this.useTouchType) return;
            if (!this.directScrollActive) return;
            const directTouches = this.getTouchesByType(e, 'direct');
            if (directTouches.length >= 2) {
                const point = this.getTouchAveragePoint(directTouches);
                const deltaX = point.x - this.directScrollLastX;
                const deltaY = point.y - this.directScrollLastY;
                const scrollArea = this.$refs.pdfArea;
                if (scrollArea) {
                    scrollArea.scrollTop -= deltaY;
                    scrollArea.scrollLeft -= deltaX;
                }
                this.directScrollLastX = point.x;
                this.directScrollLastY = point.y;
            }
            if (e.cancelable) e.preventDefault();
        },
        onPdfTouchEnd(e) {
            if (!this.useTouchType) return;
            const directTouches = this.getTouchesByType(e, 'direct');
            if (directTouches.length < 2) {
                this.directScrollActive = false;
                this.directScrollLastX = 0;
                this.directScrollLastY = 0;
            }
            if (e.cancelable) e.preventDefault();
        },
        prepareDrawContext(ctx, idx) {
            const meta = this.pageMeta[idx];
            const dpr = meta ? meta.dpr || 1 : 1;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        },
        getMainScale() {
            const baseScale = 1.4;
            return baseScale * (this.zoomPercent / 100);
        },
        getCompareScale() {
            return this.getMainScale();
        },
        getScrollRatio(el) {
            if (!el) return 0;
            const maxScroll = Math.max(el.scrollHeight - el.clientHeight, 0);
            if (maxScroll <= 0) return 0;
            return el.scrollTop / maxScroll;
        },
        setScrollByRatio(el, ratio) {
            if (!el) return;
            const maxScroll = Math.max(el.scrollHeight - el.clientHeight, 0);
            el.scrollTop = Math.max(0, Math.min(1, ratio)) * maxScroll;
        },
        refreshScrollAnchors() {
            const mainArea = this.$refs.pdfArea;
            const compareArea = this.$refs.comparePdfArea;
            if (mainArea) this.mainLastScrollTop = mainArea.scrollTop;
            if (compareArea) this.compareLastScrollTop = compareArea.scrollTop;
        },
        syncByScrollDelta(sourceEl, targetEl, sourceKey, targetKey) {
            const current = sourceEl ? sourceEl.scrollTop : 0;
            const previous = this[sourceKey] || 0;
            const delta = current - previous;
            this[sourceKey] = current;
            if (!targetEl || delta === 0) return;
            const maxTargetScroll = Math.max(targetEl.scrollHeight - targetEl.clientHeight, 0);
            const next = Math.max(0, Math.min(maxTargetScroll, targetEl.scrollTop + delta));
            targetEl.scrollTop = next;
            this[targetKey] = next;
        },
        clampZoom(value) {
            const stepped = Math.round(value / this.zoomStep) * this.zoomStep;
            return Math.min(this.zoomMax, Math.max(this.zoomMin, stepped));
        },
        setZoom(value) {
            const next = this.clampZoom(value);
            if (next === this.zoomPercent) return;
            this.zoomPercent = next;
            this.applyZoom();
        },
        zoomIn() {
            this.setZoom(this.zoomPercent + this.zoomStep);
        },
        zoomOut() {
            this.setZoom(this.zoomPercent - this.zoomStep);
        },
        applyZoom() {
            if (!this.pdfDoc) return;
            const scrollArea = this.$refs.pdfArea;
            const scrollRatio = this.getScrollRatio(scrollArea);
            const compareArea = this.$refs.comparePdfArea;
            const compareScrollRatio = this.getScrollRatio(compareArea);
            const pages = this.pdfPages.length;
            for (let i = 0; i < pages; i++) {
                if (this.loadedPages[i]) {
                    this.renderPageAtScale(this.pdfDoc, i, true);
                }
            }
            if (this.showCompare) {
                this.compareRendered = false;
                this.$nextTick(() => this.renderComparePdf());
            }
            if (scrollArea) {
                this.$nextTick(() => {
                    this.setScrollByRatio(scrollArea, scrollRatio);
                    this.setScrollByRatio(this.$refs.comparePdfArea, compareScrollRatio);
                    this.refreshScrollAnchors();
                });
            }
        },
        toggleScorePanel() {
            this.showScore = !this.showScore;
        },
        toggleCompare() {
            this.showCompare = !this.showCompare;
            if (this.showCompare) {
                this.compareRendered = false;
                this.$nextTick(() => {
                    this.refreshScrollAnchors();
                    this.renderComparePdf();
                });
            } else {
                this.compareRendered = false;
                this.$nextTick(() => this.refreshScrollAnchors());
            }
        },
        toggleSyncScroll() {
            if (!this.showCompare) return;
            this.syncScroll = !this.syncScroll;
            if (this.syncScroll) this.refreshScrollAnchors();
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
            this.compareSubmittedAt = row.submitted_at || '';
            this.showCompare = true;
            this.compareRendered = false;
            this.$nextTick(() => {
                this.refreshScrollAnchors();
                this.renderComparePdf();
            });
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
        onMainScroll(e) {
            if (!this.showCompare || !this.syncScroll || this.syncingScroll) {
                this.mainLastScrollTop = e.target ? e.target.scrollTop : 0;
                return;
            }
            const target = this.$refs.comparePdfArea;
            if (!target) return;
            this.syncingScroll = true;
            this.syncByScrollDelta(e.target, target, 'mainLastScrollTop', 'compareLastScrollTop');
            setTimeout(() => { this.syncingScroll = false; }, 0);
        },
        onCompareScroll(e) {
            if (!this.showCompare || !this.syncScroll || this.syncingScroll) {
                this.compareLastScrollTop = e.target ? e.target.scrollTop : 0;
                return;
            }
            const target = this.$refs.pdfArea;
            if (!target) return;
            this.syncingScroll = true;
            this.syncByScrollDelta(e.target, target, 'compareLastScrollTop', 'mainLastScrollTop');
            setTimeout(() => { this.syncingScroll = false; }, 0);
        },
        renderComparePdf() {
            if (!this.comparePdfUrl || this.compareRendered) return;
            const prevRatio = this.getScrollRatio(this.$refs.comparePdfArea);
            const container = this.$refs.comparePdfPages;
            if (!container) return;
            container.innerHTML = '';
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
                const scale = this.getCompareScale();
                const dpr = Math.min(window.devicePixelRatio || 1, 2);
                for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
                    const page = await pdf.getPage(pageNum);
                    const viewport = page.getViewport({ scale });
                    const cssWidth = viewport.width;
                    const cssHeight = viewport.height;
                    const canvas = document.createElement('canvas');
                    const ctx = canvas.getContext('2d');
                    canvas.style.display = 'block';
                    canvas.style.margin = '0 0 16px 0';
                    canvas.width = Math.floor(cssWidth * dpr);
                    canvas.height = Math.floor(cssHeight * dpr);
                    canvas.style.width = `${cssWidth}px`;
                    canvas.style.height = `${cssHeight}px`;
                    container.appendChild(canvas);
                    await page.render({ canvasContext: ctx, viewport, transform: [dpr, 0, 0, dpr, 0, 0] }).promise;
                }
                this.compareRendered = true;
            }).catch(err => {
                console.error('Compare PDF error:', err);
                container.innerHTML = '<div class="text-danger small p-2">比較PDFを表示できませんでした。</div>';
            }).finally(() => {
                this.compareLoading = false;
                this.$nextTick(() => {
                    this.setScrollByRatio(this.$refs.comparePdfArea, prevRatio);
                    this.refreshScrollAnchors();
                });
            });
        },
        inc(item) { item.value++; },
        dec(item) { if (item.value > 0) item.value--; },
        isPenActive() { return this.tool === 'pen'; },
        isDrawable() { return this.tool === 'pen' || this.tool === 'eraser' || this.tool === 'highlight'; },
        startDraw(idx, e) {
            if (this.useTouchType && e && !e.__fromTouch && (e.pointerType === 'touch' || e.pointerType === 'pen')) {
                return;
            }
            const pointerType = this.resolvePointerType(e);
            if (pointerType === 'touch') {
                if (this.activePointerType === 'pen' && this.drawing) {
                    if (e.cancelable) e.preventDefault();
                    return;
                }
                if (e.pointerId != null) {
                    this.touchPoints[e.pointerId] = { y: e.clientY };
                }
                if (Object.keys(this.touchPoints).length >= 2) {
                    this.twoFingerScroll = true;
                    this.lastTwoFingerY = this.getTouchAverageY();
                }
                if (e.cancelable) e.preventDefault();
                return;
            }
            const canvas = this.$refs['drawCanvas' + idx][0];
            const scrollArea = this.$refs.pdfArea;
            if (!canvas) return;
            if (canvas.setPointerCapture && e.pointerId != null && pointerType === 'mouse') {
                try {
                    canvas.setPointerCapture(e.pointerId);
                } catch (err) {
                    // ignore
                }
            }
            this.activePointerId = e.pointerId != null ? e.pointerId : null;
            this.activePointerType = pointerType;
            if (pointerType === 'pen') {
                canvas.style.touchAction = 'none';
                this.lastPenTime = Date.now();
                if (scrollArea) {
                    this.previousOverflowY = scrollArea.style.overflowY;
                    scrollArea.style.overflowY = 'hidden';
                }
            }
            if (this.tool === 'stamp') {
                const point = this.getCanvasPoint(idx, canvas, e);
                if (!this.drawData[idx]) this.drawData[idx] = [];
                if (!this.undoStack[idx]) this.undoStack[idx] = [];
                this.drawData[idx].push({
                    tool: 'stamp',
                    text: this.selectedStamp,
                    xRatio: point.x / point.cssWidth,
                    yRatio: point.y / point.cssHeight
                });
                this.redraw(idx);
                if (pointerType === 'pen') {
                    canvas.style.touchAction = 'none';
                    if (scrollArea) {
                        scrollArea.style.overflowY = this.previousOverflowY || 'auto';
                    }
                    this.previousOverflowY = '';
                }
                this.activePointerId = null;
                this.activePointerType = "";
                if (e.cancelable) e.preventDefault();
                return;
            }
            if (!this.isDrawable()) return;
            this.drawing = true;
            this.currentPage = idx;
            if (pointerType === 'pen') {
                this.lastPenTime = Date.now();
            }
            const point = this.getCanvasPoint(idx, canvas, e);
            this.lastX = point.x;
            this.lastY = point.y;
            if (!this.drawData[idx]) this.drawData[idx] = [];
            if (!this.undoStack[idx]) this.undoStack[idx] = [];
            let width = this.penWidth;
            if (this.tool === 'highlight') width = this.highlightWidth;
            this.drawData[idx].push({
                tool: this.tool,
                width: width,
                points: [{
                    xRatio: point.x / point.cssWidth,
                    yRatio: point.y / point.cssHeight
                }]
            });
            if (e.cancelable) e.preventDefault();
        },
        draw(idx, e) {
            if (this.useTouchType && e && !e.__fromTouch && (e.pointerType === 'touch' || e.pointerType === 'pen')) {
                return;
            }
            const pointerType = this.resolvePointerType(e);
            if (pointerType === 'touch') {
                if (this.activePointerType === 'pen' && this.drawing) {
                    if (e.cancelable) e.preventDefault();
                    return;
                }
                if (e.pointerId == null || !this.touchPoints[e.pointerId]) return;
                this.touchPoints[e.pointerId].y = e.clientY;
                if (Object.keys(this.touchPoints).length >= 2) {
                    const scrollArea = this.$refs.pdfArea;
                    if (scrollArea) {
                        const currentAvgY = this.getTouchAverageY();
                        const deltaY = currentAvgY - this.lastTwoFingerY;
                        scrollArea.scrollTop -= deltaY;
                        this.lastTwoFingerY = currentAvgY;
                    }
                    this.twoFingerScroll = true;
                }
                if (e.cancelable) e.preventDefault();
                return;
            }
            if (this.tool === 'stamp') return;
            if (!this.drawing || this.currentPage !== idx || !this.isDrawable()) return;
            if (this.activePointerId != null && e.pointerId != null && e.pointerId !== this.activePointerId) return;
            if (pointerType === 'pen') {
                this.lastPenTime = Date.now();
            }
            const canvas = this.$refs['drawCanvas' + idx][0];
            const scrollArea = this.$refs.pdfArea;
            const ctx = canvas.getContext('2d');
            this.prepareDrawContext(ctx, idx);
            const point = this.getCanvasPoint(idx, canvas, e);
            const x = point.x;
            const y = point.y;
            if (this.tool === 'eraser') {
                ctx.globalCompositeOperation = 'destination-out';
                ctx.lineWidth = 30;
            } else if (this.tool === 'highlight') {
                ctx.globalCompositeOperation = 'source-over';
                ctx.strokeStyle = 'rgba(255,255,0,0.1)';
                ctx.lineWidth = this.highlightWidth;
            } else {
                ctx.globalCompositeOperation = 'source-over';
                ctx.strokeStyle = "red";
                ctx.lineWidth = this.penWidth;
            }
            ctx.lineCap = "round";
            ctx.beginPath();
            ctx.moveTo(this.lastX, this.lastY);
            ctx.lineTo(x, y);
            ctx.stroke();
            ctx.globalCompositeOperation = 'source-over';
            this.lastX = x; this.lastY = y;
            this.drawData[idx][this.drawData[idx].length - 1].points.push({
                xRatio: x / point.cssWidth,
                yRatio: y / point.cssHeight
            });
            if (e.cancelable) e.preventDefault();
        },
        stopDraw(idx, e) {
            if (this.useTouchType && e && !e.__fromTouch && (e.pointerType === 'touch' || e.pointerType === 'pen')) {
                return;
            }
            const pointerType = this.resolvePointerType(e);
            if (pointerType === 'touch' && this.activePointerType !== 'pen') {
                if (e && e.pointerId != null && this.touchPoints[e.pointerId]) {
                    delete this.touchPoints[e.pointerId];
                }
                if (Object.keys(this.touchPoints).length < 2) {
                    this.twoFingerScroll = false;
                    this.lastTwoFingerY = 0;
                }
                if (e && e.cancelable) e.preventDefault();
                return;
            }
            if (this.tool === 'stamp') return;
            if (!this.isDrawable()) return;
            if (this.activePointerId != null && e && e.pointerId != null && e.pointerId !== this.activePointerId) {
                if (this.activePointerType !== 'pen') return;
            }
            const canvas = this.$refs['drawCanvas' + idx]?.[0];
            const scrollArea = this.$refs.pdfArea;
            if (canvas && canvas.releasePointerCapture && this.activePointerId != null && this.activePointerType === 'mouse') {
                try {
                    canvas.releasePointerCapture(this.activePointerId);
                } catch (err) {
                    // ignore
                }
            }
            if (canvas && this.activePointerType === 'pen') {
                canvas.style.touchAction = 'none';
                if (scrollArea) {
                    scrollArea.style.overflowY = this.previousOverflowY || 'auto';
                }
                this.previousOverflowY = '';
            }
            this.activePointerId = null;
            this.activePointerType = "";
            this.drawing = false;
            this.undoStack[idx] = [];
            if (pointerType === 'pen') {
                this.lastPenTime = Date.now();
            }
            if (e && e.cancelable) e.preventDefault();
        },
        redraw(idx) {
            const canvas = this.$refs['drawCanvas' + idx][0];
            const scrollArea = this.$refs.pdfArea;
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const meta = this.getCanvasMeta(idx, canvas);
            const dpr = meta.dpr || 1;
            ctx.setTransform(1, 0, 0, 1, 0, 0);
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            const cssWidth = meta.cssWidth;
            const cssHeight = meta.cssHeight;
            (this.drawData[idx] || []).forEach(stroke => {
                if (stroke.tool === 'stamp') {
                    const x = stroke.xRatio * cssWidth;
                    const y = stroke.yRatio * cssHeight;
                    ctx.save();
                    ctx.font = '16px sans-serif';
                    const textWidth = ctx.measureText(stroke.text).width;
                    const padding = 4;
                    ctx.strokeStyle = 'red';
                    ctx.lineWidth = 1;
                    ctx.strokeRect(x - padding, y - 16 - padding, textWidth + padding * 2, 16 + padding * 2);
                    ctx.fillStyle = 'red';
                    ctx.fillText(stroke.text, x, y);
                    ctx.restore();
                    return;
                }
                if (!stroke.points || stroke.points.length === 0) return;
                if (stroke.tool === 'eraser') {
                    ctx.globalCompositeOperation = 'destination-out';
                    ctx.lineWidth = 10;
                } else if (stroke.tool === 'highlight') {
                    ctx.globalCompositeOperation = 'source-over';
                    ctx.strokeStyle = 'rgba(255,255,0,0.1)';
                    ctx.lineWidth = stroke.width || this.highlightWidth;
                } else {
                    ctx.globalCompositeOperation = 'source-over';
                    ctx.strokeStyle = "red";
                    ctx.lineWidth = stroke.width || this.penWidth;
                }
                ctx.beginPath();
                for (let i = 0; i < stroke.points.length; i++) {
                    const pt = stroke.points[i];
                    const x = pt.xRatio * cssWidth;
                    const y = pt.yRatio * cssHeight;
                    if (i == 0) ctx.moveTo(x, y);
                    else ctx.lineTo(x, y);
                }
                ctx.lineCap = "round";
                ctx.stroke();
                ctx.globalCompositeOperation = 'source-over';
            });
        },
        undo(idx) {
            if (!this.drawData[idx] || this.drawData[idx].length === 0) return;
            if (!this.undoStack[idx]) this.undoStack[idx] = [];
            this.undoStack[idx].push(this.drawData[idx].pop());
            this.redraw(idx);
        },
        redo(idx) {
            if (!this.undoStack[idx] || this.undoStack[idx].length === 0) return;
            if (!this.drawData[idx]) this.drawData[idx] = [];
            this.drawData[idx].push(this.undoStack[idx].pop());
            this.redraw(idx);
        },
        saveGrading() {
            let images = [];
            this.pdfPages.forEach((_, idx) => {
                const canvas = this.$refs['drawCanvas' + idx][0];
            const scrollArea = this.$refs.pdfArea;
                const hasDraw = this.drawData[idx] && this.drawData[idx].length > 0;
                images.push(hasDraw ? canvas.toDataURL() : null);
            });
            const mergedScoreItems = this.scoreItems.concat(this.hiddenScoreItems);
            fetch(window.location.pathname, {
                method: "POST",
                headers: {
                    "X-CSRFToken": window.csrfToken,
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    drawImages: images,
                    scoreItems: mergedScoreItems
                })
            })
                .then(res => res.json())
                .then(res => {
                    if (res.status === "ok" && res.new_file_url) {
                        console.log("Preview fetch target:", res.new_file_url);
                        const iframe = document.getElementById("pdf-preview-iframe");
                        if (iframe) {
                            const cacheBust = Date.now();
                            iframe.src = `/submission/graded_pdf/${window.submissionId}/?t=${cacheBust}`;
                            const modal = new bootstrap.Modal(document.getElementById('pdfPreviewModal'));
                            const modalEl = document.getElementById('pdfPreviewModal');
                            if (modalEl) modalEl.removeAttribute('aria-hidden'); // スクリーンリーダー用に表示時は非非表示扱い
                            modal.show();
                            iframe.onload = function() {
                                // 読み込み失敗（HTMLや空白）の場合に備えて高さを確保
                                iframe.style.background = '#fff';
                            };
                            document.getElementById("pdf-preview-close-btn").onclick = function () {
                                let redirectUrl = "/submission/teacher_dashboard/";
                                console.log(window.userRole);
                                if (window.userRole === "admin") {
                                    redirectUrl = "/submission/admin_dashboard/";
                                } else if (window.userRole === "course-teacher") {
                                    redirectUrl = "/submission/course_teacher_dashboard/";
                                }
                                if (modalEl) modalEl.setAttribute('aria-hidden', 'true');
                                window.location.href = redirectUrl;
                            };
                        } else {
                            let redirectUrl = "/submission/teacher_dashboard/";
                            console.log(window.userRole);
                            if (window.userRole === "admin") {
                                redirectUrl = "/submission/admin_dashboard/";
                            } else if (window.userRole === "course-teacher") {
                                redirectUrl = "/submission/course_teacher_dashboard/";
                            }
                            window.open(res.new_file_url, "_blank");
                            window.location.href = redirectUrl;
                        }
                    }
                });
        },
        renderPageAtScale(pdf, i, force) {
            if (this.loadedPages[i] && !force) return;
            const scale = this.getMainScale();
            pdf.getPage(i + 1).then(page => {
                const viewport = page.getViewport({ scale });
                const dpr = Math.min(window.devicePixelRatio || 1, 2);
                const cssWidth = viewport.width;
                const cssHeight = viewport.height;
                const pdfCanvas = this.$refs['pdfCanvas' + i]?.[0];
                if (!pdfCanvas) return;
                const pdfCtx = pdfCanvas.getContext('2d');
                pdfCanvas.width = Math.floor(cssWidth * dpr);
                pdfCanvas.height = Math.floor(cssHeight * dpr);
                pdfCanvas.style.width = `${cssWidth}px`;
                pdfCanvas.style.height = `${cssHeight}px`;
                page.render({ canvasContext: pdfCtx, viewport, transform: [dpr, 0, 0, dpr, 0, 0] });
                const drawCanvas = this.$refs['drawCanvas' + i]?.[0];
                if (!drawCanvas) return;
                drawCanvas.width = Math.floor(cssWidth * dpr);
                drawCanvas.height = Math.floor(cssHeight * dpr);
                drawCanvas.style.width = `${cssWidth}px`;
                drawCanvas.style.height = `${cssHeight}px`;
                this.pageMeta[i] = { cssWidth, cssHeight, dpr };
                this.loadedPages[i] = true;
                if (this.drawData[i] && this.drawData[i].length > 0) {
                    this.redraw(i);
                }
            });
        },
        loadPage(pdf, i) {
            this.renderPageAtScale(pdf, i, false);
        }
    },
    mounted() {
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
            || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
        this.useTouchType = isIOS;
        const CMAP_URL = "https://cdn.jsdelivr.net/npm/pdfjs-dist@2.16.105/cmaps/";
        const STANDARD_FONT_URL = "https://cdn.jsdelivr.net/npm/pdfjs-dist@2.16.105/standard_fonts/";
        pdfjsLib.GlobalWorkerOptions.workerSrc =
            "https://cdn.jsdelivr.net/npm/pdfjs-dist@2.16.105/build/pdf.worker.min.js";
        // 採点項目の動的反映
        const offeringId = window.courseOfferingId || "";
        const scoringUrl = offeringId
            ? `/submission/scoring_items_api/?offering_id=${encodeURIComponent(offeringId)}`
            : "/submission/scoring_items_api/";
        fetch(scoringUrl)
            .then(res => res.json())
            .then(items => {
                const saved = window.initialScoreDetails || [];
                const applySavedValues = (list) => {
                    list.forEach(item => {
                        const found = saved.find(s => {
                            if (s.code && item.code && s.code === item.code) return true;
                            return s.label === item.label;
                        });
                        if (found) {
                            item.value = found.value || 0;
                        }
                    });
                };
                if (window.reportType === "prep") {
                    const allItems = items.pre || [];
                    const visible = allItems.filter(i => i.show_in_grading_form !== false);
                    const hidden = allItems.filter(i => i.show_in_grading_form === false);
                    this.scoreItems = visible.map(lab => ({
                        label: lab.label,
                        weight: lab.weight,
                        value: 0,
                        key: lab.code || lab.label,
                        code: lab.code || ""
                    }));
                    this.hiddenScoreItems = hidden.map(lab => ({
                        label: lab.label,
                        weight: lab.weight,
                        value: 0,
                        key: lab.code || lab.label,
                        code: lab.code || ""
                    }));
                } else {
                    const allItems = items.main || [];
                    const visible = allItems.filter(i => i.show_in_grading_form !== false);
                    const hidden = allItems.filter(i => i.show_in_grading_form === false);
                    this.scoreItems = visible.map(lab => ({
                        label: lab.label,
                        weight: lab.weight,
                        value: 0,
                        key: lab.code || lab.label,
                        code: lab.code || ""
                    }));
                    this.hiddenScoreItems = hidden.map(lab => ({
                        label: lab.label,
                        weight: lab.weight,
                        value: 0,
                        key: lab.code || lab.label,
                        code: lab.code || ""
                    }));
                }
                applySavedValues(this.scoreItems);
                applySavedValues(this.hiddenScoreItems);
            });
        // PDF.js lazy load
        const url = window.pdf_url;
        const loadingTask = pdfjsLib.getDocument({
            url: url,
            cMapUrl: CMAP_URL,
            cMapPacked: true,
            standardFontDataUrl: STANDARD_FONT_URL,
        });

        loadingTask.promise.then(pdf => {
            this.pdfDoc = pdf;
            this.pdfPages = Array(pdf.numPages).fill(0);
            // まず先頭3ページだけ
            for (let i = 0; i < Math.min(3, pdf.numPages); i++) this.loadPage(pdf, i);
            // IntersectionObserverで残りページ
            this.$nextTick(() => {
                const io = new IntersectionObserver(entries => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            const idx = Number(entry.target.dataset.idx);
                            if (!this.loadedPages[idx]) this.loadPage(pdf, idx);
                        }
                    });
                }, { root: document.querySelector("#pdf-area"), threshold: 0.1 });
                this.pdfPages.forEach((_, idx) => {
                    const el = this.$refs['pdfCanvas' + idx]?.[0];
                    if (el) {
                        el.dataset.idx = idx;
                        io.observe(el);
                    }
                });
            });
        });

        // スタンプ取得
        fetch("/submission/stamps_api/")
            .then(res => res.json())
            .then(data => {
                this.stamps = data.stamps || [];
                if (this.stamps.length) this.selectedStamp = this.stamps[0].text;
            });

        // キーボードショートカット
        window.addEventListener('keydown', (e) => {
            if (document.activeElement.tagName === "INPUT" || document.activeElement.tagName === "TEXTAREA") return;
            if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
                if (this.currentPage != null) this.undo(this.currentPage);
                else if (this.pdfPages.length > 0) this.undo(0);
                e.preventDefault();
            }
            if ((e.ctrlKey || e.metaKey) && e.key === 'y') {
                if (this.currentPage != null) this.redo(this.currentPage);
                else if (this.pdfPages.length > 0) this.redo(0);
                e.preventDefault();
            }
        });
    },
    beforeDestroy() {
        this.clearSimilarityProgressTimer();
    }
});
