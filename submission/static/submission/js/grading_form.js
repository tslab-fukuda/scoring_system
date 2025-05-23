new Vue({
    el: '#grading-form',
    data: {
        tool: 'pen',
        showScore: false,
        scoreItems: [
            { key: 'content', label: '内容不足', value: 0 },
            { key: 'consideration', label: '考察不足', value: 0 },
            { key: 'format', label: 'フォーマットミス', value: 0 }
        ],
        pdfPages: [],
        drawing: false,
        lastX: 0,
        lastY: 0,
        currentPage: null,
        drawData: [],  // 各ページの手書き座標を保存
        drawData: [],    // ページごとの描画履歴 [ [stroke1, stroke2, ...], ... ]
        undoStack: [],
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
            // 新しいストローク開始
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
            // 描画終了ごとにundoStackをクリア（通常のundo/redo動作）
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
                body: JSON.stringify({ drawImages: images })
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
                            window.location.href = "/submission/teacher_dashboard/";
                        };
                    } else {
                        // もしiframeが見つからないならPDFだけ別タブで表示（安全策）
                        window.open(res.new_file_url, "_blank");
                        window.location.href = "/submission/teacher_dashboard/";
                    }
                }
            });
        }
    },
    mounted() {
        // PDF.js 全ページスクロール
        const url = window.pdf_url;
        pdfjsLib.getDocument(url).promise.then(pdf => {
            this.pdfPages = Array(pdf.numPages).fill(0);
            this.$nextTick(() => {
                for (let i = 0; i < pdf.numPages; i++) {
                    pdf.getPage(i + 1).then(page => {
                        const viewport = page.getViewport({ scale: 1.4 });
                        // PDF canvas
                        const pdfCanvas = this.$refs['pdfCanvas' + i][0];
                        pdfCanvas.width = viewport.width;
                        pdfCanvas.height = viewport.height;
                        page.render({ canvasContext: pdfCanvas.getContext('2d'), viewport });
                        // Draw canvas
                        const drawCanvas = this.$refs['drawCanvas' + i][0];
                        drawCanvas.width = viewport.width;
                        drawCanvas.height = viewport.height;
                    });
                }
            });
        });
        // キーボードショートカット
        window.addEventListener('keydown', (e) => {
            // アクティブページにのみundo/redo
            if (document.activeElement.tagName === "INPUT" || document.activeElement.tagName === "TEXTAREA") return;
            // Ctrl+Z
            if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
                if (this.currentPage != null) this.undo(this.currentPage);
                else if (this.pdfPages.length > 0) this.undo(0);
                e.preventDefault();
            }
            // Ctrl+Y
            if ((e.ctrlKey || e.metaKey) && e.key === 'y') {
                if (this.currentPage != null) this.redo(this.currentPage);
                else if (this.pdfPages.length > 0) this.redo(0);
                e.preventDefault();
            }
        });
    }
});