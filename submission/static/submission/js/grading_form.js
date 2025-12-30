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
        syncingScroll: false,
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
        directScrollLastY: 0,
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
        getTouchAverageYFromList(touches) {
            if (!touches || touches.length === 0) return 0;
            const total = touches.reduce((sum, touch) => sum + touch.clientY, 0);
            return total / touches.length;
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
                this.directScrollLastY = this.getTouchAverageYFromList(directTouches);
            }
            if (e.cancelable) e.preventDefault();
        },
        onPdfTouchMove(e) {
            if (!this.useTouchType) return;
            if (!this.directScrollActive) return;
            const directTouches = this.getTouchesByType(e, 'direct');
            if (directTouches.length >= 2) {
                const currentY = this.getTouchAverageYFromList(directTouches);
                const deltaY = currentY - this.directScrollLastY;
                const scrollArea = this.$refs.pdfArea;
                if (scrollArea) {
                    scrollArea.scrollTop -= deltaY;
                }
                this.directScrollLastY = currentY;
            }
            if (e.cancelable) e.preventDefault();
        },
        onPdfTouchEnd(e) {
            if (!this.useTouchType) return;
            const directTouches = this.getTouchesByType(e, 'direct');
            if (directTouches.length < 2) {
                this.directScrollActive = false;
                this.directScrollLastY = 0;
            }
            if (e.cancelable) e.preventDefault();
        },
        prepareDrawContext(ctx, idx) {
            const meta = this.pageMeta[idx];
            const dpr = meta ? meta.dpr || 1 : 1;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        },
        toggleScorePanel() {
            this.showScore = !this.showScore;
        },
        toggleCompare() {
            this.showCompare = !this.showCompare;
            if (this.showCompare) {
                this.compareRendered = false;
                this.$nextTick(() => this.renderComparePdf());
            } else {
                this.compareRendered = false;
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
        renderComparePdf() {
            if (!this.comparePdfUrl || this.compareRendered) return;
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
                this.compareRendered = true;
            }).catch(err => {
                console.error('Compare PDF error:', err);
                container.innerHTML = '<div class="text-danger small p-2">比較PDFを表示できませんでした。</div>';
            }).finally(() => {
                this.compareLoading = false;
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
        loadPage(pdf, i) {
            if (this.loadedPages[i]) return;
            pdf.getPage(i + 1).then(page => {
                const baseScale = 1.4;
                const viewport = page.getViewport({ scale: baseScale });
                const dpr = Math.min(window.devicePixelRatio || 1, 2);
                const cssWidth = viewport.width;
                const cssHeight = viewport.height;
                const pdfCanvas = this.$refs['pdfCanvas' + i][0];
                const pdfCtx = pdfCanvas.getContext('2d');
                pdfCanvas.width = Math.floor(cssWidth * dpr);
                pdfCanvas.height = Math.floor(cssHeight * dpr);
                pdfCanvas.style.width = `${cssWidth}px`;
                pdfCanvas.style.height = `${cssHeight}px`;
                page.render({ canvasContext: pdfCtx, viewport, transform: [dpr, 0, 0, dpr, 0, 0] });
                const drawCanvas = this.$refs['drawCanvas' + i][0];
                const drawCtx = drawCanvas.getContext('2d');
                drawCanvas.width = Math.floor(cssWidth * dpr);
                drawCanvas.height = Math.floor(cssHeight * dpr);
                drawCanvas.style.width = `${cssWidth}px`;
                drawCanvas.style.height = `${cssHeight}px`;
                drawCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
                this.pageMeta[i] = { cssWidth, cssHeight, dpr };
                this.loadedPages[i] = true;
            });
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
    }
});
