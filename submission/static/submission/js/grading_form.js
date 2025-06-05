new Vue({
    el: '#grading-form',
    data: {
        tool: 'pen',
        showScore: false,
        scoreItems: [],
        pdfPages: [],
        loadedPages: {},
        drawing: false,
        lastX: 0,
        lastY: 0,
        currentPage: null,
        drawData: [],
        undoStack: [],
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
        inc(item) { item.value++; },
        dec(item) { if (item.value > 0) item.value--; },
        isPenActive() { return this.tool === 'pen'; },
        startDraw(idx, e) {
            if (!this.isPenActive()) return;
            this.drawing = true;
            this.currentPage = idx;
            const rect = e.target.getBoundingClientRect();
            this.lastX = e.clientX - rect.left;
            this.lastY = e.clientY - rect.top;
            if (!this.drawData[idx]) this.drawData[idx] = [];
            if (!this.undoStack[idx]) this.undoStack[idx] = [];
            this.drawData[idx].push([{ x: this.lastX, y: this.lastY }]);
        },
        draw(idx, e) {
            if (!this.drawing || this.currentPage !== idx || !this.isPenActive()) return;
            const canvas = this.$refs['drawCanvas' + idx][0];
            const ctx = canvas.getContext('2d');
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            ctx.strokeStyle = "red";
            ctx.lineWidth = 2;
            ctx.lineCap = "round";
            ctx.beginPath();
            ctx.moveTo(this.lastX, this.lastY);
            ctx.lineTo(x, y);
            ctx.stroke();
            this.lastX = x; this.lastY = y;
            this.drawData[idx][this.drawData[idx].length - 1].push({ x, y });
        },
        stopDraw(idx) {
            if (!this.isPenActive()) return;
            this.drawing = false;
            this.currentPage = null;
            this.undoStack[idx] = [];
        },
        redraw(idx) {
            const canvas = this.$refs['drawCanvas' + idx][0];
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            (this.drawData[idx] || []).forEach(stroke => {
                ctx.beginPath();
                for (let i = 0; i < stroke.length; i++) {
                    if (i == 0) ctx.moveTo(stroke[i].x, stroke[i].y);
                    else ctx.lineTo(stroke[i].x, stroke[i].y);
                }
                ctx.strokeStyle = "red";
                ctx.lineWidth = 2;
                ctx.lineCap = "round";
                ctx.stroke();
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
                images.push(canvas.toDataURL());
            });
            fetch(window.location.pathname, {
                method: "POST",
                headers: {
                    "X-CSRFToken": window.csrfToken,
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ 
                    drawImages: images,
                    scoreItems: this.scoreItems
                 })
            })
            .then(res => res.json())
            .then(res => {
                if (res.status === "ok" && res.new_file_url) {
                    const iframe = document.getElementById("pdf-preview-iframe");
                    if (iframe) {
                        iframe.src = res.new_file_url;
                        const modal = new bootstrap.Modal(document.getElementById('pdfPreviewModal'));
                        modal.show();
                        document.getElementById("pdf-preview-close-btn").onclick = function () {
                            let redirectUrl = "/submission/teacher_dashboard/";
                            console.log(window.userRole);
                            if (window.userRole === "admin") {
                                redirectUrl = "/submission/admin_dashboard/";
                            }
                            window.location.href = redirectUrl;
                        };
                    } else {
                        let redirectUrl = "/submission/teacher_dashboard/";
                        console.log(window.userRole);
                        if (window.userRole === "admin") {
                            redirectUrl = "/submission/admin_dashboard/";
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
        // 採点項目の動的反映
        fetch("/submission/scoring_items_api/")
          .then(res => res.json())
          .then(items => {
            if (window.reportType === "prep") {
                this.scoreItems = (items.pre || []).map(lab => ({
                    label: lab.label,
                    weight: lab.weight,
                    value: 0,
                    key: lab.label
                  }));
            } else {
                this.scoreItems = (items.main || []).map(lab => ({
                    label: lab.label,
                    weight: lab.weight,
                    value: 0,
                    key: lab.label
                  }));
            }
            // console.table(this.scoreItems)
          });
        // PDF.js lazy load
        const url = window.pdf_url;
        pdfjsLib.getDocument(url).promise.then(pdf => {
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
