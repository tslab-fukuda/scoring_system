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
    },
    computed: {
        totalScore() {
            return this.scoreItems.reduce((acc, item) => acc + (item.value * (item.weight || 1)), 0);
        }
    },
    methods: {
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
            if (this.tool === 'stamp') {
                const canvas = this.$refs['drawCanvas' + idx][0];
                const rect = e.target.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                if (!this.drawData[idx]) this.drawData[idx] = [];
                if (!this.undoStack[idx]) this.undoStack[idx] = [];
                this.drawData[idx].push({
                    tool: 'stamp',
                    text: this.selectedStamp,
                    xRatio: x / canvas.width,
                    yRatio: y / canvas.height
                });
                this.redraw(idx);
                return;
            }
            if (!this.isDrawable()) return;
            this.drawing = true;
            this.currentPage = idx;
            const canvas = this.$refs['drawCanvas' + idx][0];
            const rect = e.target.getBoundingClientRect();
            this.lastX = e.clientX - rect.left;
            this.lastY = e.clientY - rect.top;
            if (!this.drawData[idx]) this.drawData[idx] = [];
            if (!this.undoStack[idx]) this.undoStack[idx] = [];
            let width = this.penWidth;
            if (this.tool === 'highlight') width = this.highlightWidth;
            this.drawData[idx].push({
                tool: this.tool,
                width: width,
                points: [{
                    xRatio: this.lastX / canvas.width,
                    yRatio: this.lastY / canvas.height
                }]
            });
        },
        draw(idx, e) {
            if (this.tool === 'stamp') return;
            if (!this.drawing || this.currentPage !== idx || !this.isDrawable()) return;
            const canvas = this.$refs['drawCanvas' + idx][0];
            const ctx = canvas.getContext('2d');
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
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
                xRatio: x / canvas.width,
                yRatio: y / canvas.height
            });
        },
        stopDraw(idx) {
            if (this.tool === 'stamp') return;
            if (!this.isDrawable()) return;
            this.drawing = false;
            this.undoStack[idx] = [];
        },
        redraw(idx) {
            const canvas = this.$refs['drawCanvas' + idx][0];
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            (this.drawData[idx] || []).forEach(stroke => {
                if (stroke.tool === 'stamp') {
                    const x = stroke.xRatio * canvas.width;
                    const y = stroke.yRatio * canvas.height;
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
                    const x = pt.xRatio * canvas.width;
                    const y = pt.yRatio * canvas.height;
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
                const viewport = page.getViewport({ scale: 1.4 });
                const pdfCanvas = this.$refs['pdfCanvas' + i][0];
                pdfCanvas.width = viewport.width;
                pdfCanvas.height = viewport.height;
                page.render({ canvasContext: pdfCanvas.getContext('2d'), viewport });
                const drawCanvas = this.$refs['drawCanvas' + i][0];
                drawCanvas.width = viewport.width;
                drawCanvas.height = viewport.height;
                this.loadedPages[i] = true;
            });
        }
    },
    mounted() {
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
