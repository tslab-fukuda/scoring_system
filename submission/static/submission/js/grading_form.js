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
        historyStack: [],
        undoStack: [],
        stamps: [],
        selectedStamp: "",
        penWidth: 2,
        textFontSize: 18,
        defaultPenColor: '#ff0000',
        penColor: '#ff0000',
        penColors: ['#ff0000', '#1d4ed8', '#16a34a', '#111827'],
        highlightWidth: 10,
        defaultHighlightColor: 'rgba(255, 241, 87, 0.30)',
        highlightBaseColor: '#ffeb3b',
        highlightOpacity: 38,
        highlightColors: ['#ffeb3b', '#a3e635', '#67e8f9', '#f9a8d4'],
        eraserWidth: 1,
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
        currentEraserPoint: null,
        highlightStraightMode: false,
        highlightStraightTimer: null,
        activeTextEditor: null,
        activeTextDrag: null,
        nextTextAnnotationId: 1,
    },
    computed: {
        totalScore() {
            return this.scoreItems.reduce((acc, item) => acc + (item.value * (item.weight || 1)), 0);
        }
    },
    watch: {
        textFontSize(nextValue) {
            if (!this.activeTextEditor) return;
            this.activeTextEditor.fontSize = Math.max(10, Number(nextValue) || 18);
            this.syncTextEditorSize();
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
        setTool(nextTool) {
            if (this.tool === nextTool) return;
            this.finalizeActiveTextEditor();
            this.tool = nextTool;
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
        hexToRgba(hex, alpha) {
            const normalized = (hex || '').replace('#', '');
            if (normalized.length !== 6) return this.defaultHighlightColor;
            const r = parseInt(normalized.slice(0, 2), 16);
            const g = parseInt(normalized.slice(2, 4), 16);
            const b = parseInt(normalized.slice(4, 6), 16);
            if ([r, g, b].some(Number.isNaN)) return this.defaultHighlightColor;
            return `rgba(${r}, ${g}, ${b}, ${alpha})`;
        },
        getCurrentHighlightColor() {
            const alpha = Math.max(0.1, Math.min(0.6, (this.highlightOpacity || 0) / 100));
            return this.hexToRgba(this.highlightBaseColor, alpha);
        },
        getStrokeColor(stroke) {
            if (!stroke) return this.defaultPenColor;
            if (stroke.tool === 'highlight') return stroke.color || this.defaultHighlightColor;
            return stroke.color || this.defaultPenColor;
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
        ensurePageState(idx) {
            if (!this.drawData[idx]) this.$set(this.drawData, idx, []);
            if (!this.historyStack[idx]) this.$set(this.historyStack, idx, []);
            if (!this.undoStack[idx]) this.$set(this.undoStack, idx, []);
        },
        cloneStroke(stroke) {
            return {
                ...stroke,
                points: (stroke.points || []).map(point => ({ ...point })),
            };
        },
        generateTextAnnotationId() {
            const id = this.nextTextAnnotationId;
            this.nextTextAnnotationId += 1;
            return `text-${id}`;
        },
        pageTextAnnotations(idx) {
            return (this.drawData[idx] || [])
                .map((stroke, index) => ({ stroke, index }))
                .filter(entry => entry.stroke.tool === 'text');
        },
        isEditingText(pageIdx, strokeIndex) {
            return !!this.activeTextEditor
                && this.activeTextEditor.pageIdx === pageIdx
                && this.activeTextEditor.strokeIndex === strokeIndex;
        },
        resolveTextFontSize(idx, stroke) {
            const meta = this.pageMeta[idx];
            const cssWidth = meta ? meta.cssWidth || 1 : 1;
            const fallback = Math.max(10, this.textFontSize || 18);
            const ratio = stroke && stroke.fontSizeRatio;
            return Math.max(10, Math.round((ratio || (fallback / cssWidth)) * cssWidth));
        },
        resolveTextBoxWidth(idx, stroke) {
            const meta = this.pageMeta[idx];
            const cssWidth = meta ? meta.cssWidth || 0 : 0;
            const defaultWidth = Math.min(260, Math.max(180, cssWidth * 0.28 || 220));
            const ratio = stroke && stroke.widthRatio;
            return Math.max(140, Math.round((ratio || (defaultWidth / Math.max(cssWidth, 1))) * Math.max(cssWidth, 1)));
        },
        textAnnotationStyle(idx, stroke) {
            const meta = this.pageMeta[idx];
            const cssWidth = meta ? meta.cssWidth || 0 : 0;
            const cssHeight = meta ? meta.cssHeight || 0 : 0;
            const left = (stroke.xRatio || 0) * cssWidth;
            const top = (stroke.yRatio || 0) * cssHeight;
            const isEditing = this.activeTextEditor && this.activeTextEditor.strokeId === stroke.id;
            const fontSize = isEditing
                ? Math.max(10, this.activeTextEditor.fontSize || this.textFontSize || 18)
                : this.resolveTextFontSize(idx, stroke);
            const width = this.resolveTextBoxWidth(idx, stroke);
            return {
                left: `${left}px`,
                top: `${top}px`,
                width: `${width}px`,
                fontSize: `${fontSize}px`,
                lineHeight: `${Math.round(fontSize * 1.35)}px`,
            };
        },
        syncTextEditorSize() {
            if (!this.activeTextEditor) return;
            const editorRef = this.$refs[this.activeTextEditor.refKey];
            const editor = Array.isArray(editorRef) ? editorRef[0] : editorRef;
            if (!editor) return;
            editor.style.height = 'auto';
            editor.style.height = `${Math.max(editor.scrollHeight, Math.round(this.activeTextEditor.fontSize * 1.8))}px`;
        },
        focusActiveTextEditor() {
            if (!this.activeTextEditor) return;
            this.$nextTick(() => {
                const editorRef = this.$refs[this.activeTextEditor.refKey];
                const editor = Array.isArray(editorRef) ? editorRef[0] : editorRef;
                if (!editor) return;
                editor.focus();
                if (typeof editor.selectionStart === 'number') {
                    const text = editor.value || '';
                    editor.selectionStart = text.length;
                    editor.selectionEnd = text.length;
                }
                this.syncTextEditorSize();
            });
        },
        openTextEditor(pageIdx, strokeIndex, options = {}) {
            const stroke = (this.drawData[pageIdx] || [])[strokeIndex];
            if (!stroke || stroke.tool !== 'text') return;
            if (
                this.activeTextEditor &&
                (this.activeTextEditor.pageIdx !== pageIdx || this.activeTextEditor.strokeIndex !== strokeIndex)
            ) {
                this.finalizeActiveTextEditor();
            }
            this.activeTextEditor = {
                pageIdx,
                strokeIndex,
                strokeId: stroke.id,
                originalText: stroke.text || '',
                draftText: stroke.text || '',
                isNew: !!options.isNew,
                fontSize: this.resolveTextFontSize(pageIdx, stroke),
                refKey: `textEditor${pageIdx}-${stroke.id}`,
            };
            this.textFontSize = this.activeTextEditor.fontSize;
            this.focusActiveTextEditor();
        },
        createTextAnnotation(idx, point) {
            this.ensurePageState(idx);
            this.snapshotForHistory(idx);
            this.clearRedoHistory(idx);
            const widthRatio = Math.min(0.6, Math.max(0.18, 220 / Math.max(point.cssWidth, 1)));
            const fontSizeRatio = Math.max(10, this.textFontSize || 18) / Math.max(point.cssWidth, 1);
            const stroke = {
                tool: 'text',
                id: this.generateTextAnnotationId(),
                text: '',
                xRatio: point.x / point.cssWidth,
                yRatio: point.y / point.cssHeight,
                widthRatio,
                fontSizeRatio,
            };
            this.drawData[idx].push(stroke);
            const strokeIndex = this.drawData[idx].length - 1;
            this.openTextEditor(idx, strokeIndex, { isNew: true, force: true });
        },
        editTextAnnotation(pageIdx, strokeIndex) {
            this.openTextEditor(pageIdx, strokeIndex);
        },
        onTextEditorInput(e) {
            if (!this.activeTextEditor) return;
            this.activeTextEditor.draftText = e.target.value;
            this.syncTextEditorSize();
        },
        removeTextStroke(pageIdx, strokeIndex) {
            if (!this.drawData[pageIdx]) return;
            this.drawData[pageIdx].splice(strokeIndex, 1);
            this.redraw(pageIdx);
        },
        finalizeActiveTextEditor() {
            if (!this.activeTextEditor) return;
            this.commitTextEditor();
        },
        commitTextEditor() {
            if (!this.activeTextEditor) return;
            const editorState = this.activeTextEditor;
            const stroke = (this.drawData[editorState.pageIdx] || [])[editorState.strokeIndex];
            this.activeTextEditor = null;
            if (!stroke || stroke.tool !== 'text') return;
            const rawText = editorState.draftText || '';
            const nextText = rawText.replace(/\r\n/g, '\n');
            if (!nextText.trim()) {
                if (!editorState.isNew) {
                    this.snapshotForHistory(editorState.pageIdx);
                    this.clearRedoHistory(editorState.pageIdx);
                }
                this.removeTextStroke(editorState.pageIdx, editorState.strokeIndex);
                return;
            }
            if (stroke.text !== nextText) {
                if (!editorState.isNew) {
                    this.snapshotForHistory(editorState.pageIdx);
                    this.clearRedoHistory(editorState.pageIdx);
                }
                stroke.text = nextText;
            }
            const meta = this.pageMeta[editorState.pageIdx];
            if (meta && meta.cssWidth) {
                stroke.fontSizeRatio = Math.max(10, editorState.fontSize || this.textFontSize || 18) / meta.cssWidth;
            }
            this.redraw(editorState.pageIdx);
        },
        cancelTextEditor() {
            if (!this.activeTextEditor) return;
            const editorState = this.activeTextEditor;
            const stroke = (this.drawData[editorState.pageIdx] || [])[editorState.strokeIndex];
            this.activeTextEditor = null;
            if (!stroke || stroke.tool !== 'text') return;
            if (editorState.isNew && !(stroke.text || '').trim()) {
                this.removeTextStroke(editorState.pageIdx, editorState.strokeIndex);
                return;
            }
            stroke.text = editorState.originalText || stroke.text || '';
            this.redraw(editorState.pageIdx);
        },
        startTextAnnotationDrag(pageIdx, strokeIndex, e) {
            if (this.activeTextEditor) {
                this.finalizeActiveTextEditor();
            }
            const stroke = (this.drawData[pageIdx] || [])[strokeIndex];
            if (!stroke || stroke.tool !== 'text') return;
            const meta = this.pageMeta[pageIdx];
            if (!meta) return;
            this.activeTextDrag = {
                pageIdx,
                strokeIndex,
                strokeId: stroke.id,
                startClientX: e.clientX,
                startClientY: e.clientY,
                startXRatio: stroke.xRatio || 0,
                startYRatio: stroke.yRatio || 0,
                moved: false,
                historySaved: false,
            };
            if (e.currentTarget && e.currentTarget.setPointerCapture && e.pointerId != null) {
                try {
                    e.currentTarget.setPointerCapture(e.pointerId);
                } catch (err) {
                    // ignore
                }
            }
            if (e.cancelable) e.preventDefault();
        },
        dragTextAnnotation(e) {
            if (!this.activeTextDrag) return;
            const drag = this.activeTextDrag;
            const stroke = (this.drawData[drag.pageIdx] || [])[drag.strokeIndex];
            const meta = this.pageMeta[drag.pageIdx];
            if (!stroke || !meta) return;
            const dx = e.clientX - drag.startClientX;
            const dy = e.clientY - drag.startClientY;
            const moveThreshold = 4;
            if (!drag.moved && Math.abs(dx) < moveThreshold && Math.abs(dy) < moveThreshold) {
                if (e.cancelable) e.preventDefault();
                return;
            }
            if (!drag.historySaved) {
                this.snapshotForHistory(drag.pageIdx);
                this.clearRedoHistory(drag.pageIdx);
                drag.historySaved = true;
            }
            drag.moved = true;
            const nextXRatio = drag.startXRatio + (dx / Math.max(meta.cssWidth, 1));
            const nextYRatio = drag.startYRatio + (dy / Math.max(meta.cssHeight, 1));
            const maxX = Math.max(0, 1 - (stroke.widthRatio || 0.18));
            stroke.xRatio = Math.max(0, Math.min(maxX, nextXRatio));
            stroke.yRatio = Math.max(0, Math.min(0.98, nextYRatio));
            if (e.cancelable) e.preventDefault();
        },
        finishTextAnnotationDrag(e) {
            if (!this.activeTextDrag) return;
            const drag = this.activeTextDrag;
            if (e.currentTarget && e.currentTarget.releasePointerCapture && e.pointerId != null) {
                try {
                    e.currentTarget.releasePointerCapture(e.pointerId);
                } catch (err) {
                    // ignore
                }
            }
            this.activeTextDrag = null;
            if (!drag.moved) {
                this.editTextAnnotation(drag.pageIdx, drag.strokeIndex);
            } else {
                this.redraw(drag.pageIdx);
            }
            if (e.cancelable) e.preventDefault();
        },
        cancelTextAnnotationDrag(e) {
            if (!this.activeTextDrag) return;
            const drag = this.activeTextDrag;
            const stroke = (this.drawData[drag.pageIdx] || [])[drag.strokeIndex];
            if (stroke) {
                stroke.xRatio = drag.startXRatio;
                stroke.yRatio = drag.startYRatio;
            }
            this.activeTextDrag = null;
            this.redraw(drag.pageIdx);
            if (e.cancelable) e.preventDefault();
        },
        splitTextIntoLines(ctx, text, maxWidth) {
            const paragraphs = String(text || '').split('\n');
            const lines = [];
            paragraphs.forEach((paragraph) => {
                if (!paragraph) {
                    lines.push('');
                    return;
                }
                let current = '';
                for (const char of Array.from(paragraph)) {
                    const candidate = current + char;
                    if (!current || ctx.measureText(candidate).width <= maxWidth) {
                        current = candidate;
                        continue;
                    }
                    lines.push(current);
                    current = char;
                }
                if (current) lines.push(current);
            });
            return lines.length ? lines : [''];
        },
        drawTextAnnotation(ctx, idx, stroke) {
            const meta = this.pageMeta[idx];
            if (!meta) return;
            const cssWidth = meta.cssWidth;
            const cssHeight = meta.cssHeight;
            const x = (stroke.xRatio || 0) * cssWidth;
            const y = (stroke.yRatio || 0) * cssHeight;
            const width = this.resolveTextBoxWidth(idx, stroke);
            const fontSize = this.resolveTextFontSize(idx, stroke);
            const lineHeight = Math.round(fontSize * 1.35);
            ctx.save();
            ctx.fillStyle = '#ff0000';
            ctx.font = `${fontSize}px sans-serif`;
            ctx.textBaseline = 'top';
            const lines = this.splitTextIntoLines(ctx, stroke.text || '', Math.max(40, width));
            lines.forEach((line, lineIndex) => {
                ctx.fillText(line, x, y + (lineIndex * lineHeight));
            });
            ctx.restore();
        },
        exportCanvasDataUrl(idx) {
            const canvas = this.$refs['drawCanvas' + idx]?.[0];
            if (!canvas) return null;
            const hasDraw = this.drawData[idx] && this.drawData[idx].length > 0;
            if (!hasDraw) return null;
            const exportCanvas = document.createElement('canvas');
            exportCanvas.width = canvas.width;
            exportCanvas.height = canvas.height;
            const exportCtx = exportCanvas.getContext('2d');
            exportCtx.drawImage(canvas, 0, 0);
            const meta = this.pageMeta[idx];
            if (meta) {
                const dpr = meta.dpr || 1;
                exportCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
                (this.drawData[idx] || []).forEach((stroke) => {
                    if (stroke.tool === 'text' && (stroke.text || '').trim()) {
                        this.drawTextAnnotation(exportCtx, idx, stroke);
                    }
                });
            }
            return exportCanvas.toDataURL();
        },
        clonePageDrawData(idx) {
            return (this.drawData[idx] || []).map(stroke => this.cloneStroke(stroke));
        },
        snapshotForHistory(idx) {
            this.ensurePageState(idx);
            this.historyStack[idx].push(this.clonePageDrawData(idx));
            if (this.historyStack[idx].length > 100) {
                this.historyStack[idx].shift();
            }
        },
        clearRedoHistory(idx) {
            this.ensurePageState(idx);
            this.undoStack[idx] = [];
        },
        restorePageDrawData(idx, snapshot) {
            this.$set(this.drawData, idx, (snapshot || []).map(stroke => this.cloneStroke(stroke)));
            this.redraw(idx);
        },
        clearHighlightStraightTimer() {
            if (this.highlightStraightTimer) {
                clearTimeout(this.highlightStraightTimer);
                this.highlightStraightTimer = null;
            }
        },
        shouldUseHighlightStraightAssist(pointerType) {
            return this.tool === 'highlight' && pointerType === 'mouse';
        },
        startHighlightStraightTimer(idx) {
            this.clearHighlightStraightTimer();
            if (!this.shouldUseHighlightStraightAssist(this.activePointerType)) return;
            if (!this.drawing || this.currentPage !== idx || this.highlightStraightMode) return;
            this.highlightStraightTimer = setTimeout(() => {
                if (!this.drawing || this.currentPage !== idx || !this.shouldUseHighlightStraightAssist(this.activePointerType)) return;
                const strokes = this.drawData[idx] || [];
                const stroke = strokes[strokes.length - 1];
                if (!stroke || stroke.tool !== 'highlight' || !stroke.points || stroke.points.length === 0) return;
                const startPoint = { ...stroke.points[0] };
                const lastPoint = { ...(stroke.points[stroke.points.length - 1] || stroke.points[0]) };
                stroke.points = [startPoint, lastPoint];
                this.highlightStraightMode = true;
                this.redraw(idx);
            }, 1000);
        },
        appendPointToCurrentStroke(idx, point, options = {}) {
            const strokes = this.drawData[idx] || [];
            const stroke = strokes[strokes.length - 1];
            if (!stroke) return false;
            const newPoint = {
                xRatio: point.x / point.cssWidth,
                yRatio: point.y / point.cssHeight
            };
            const points = stroke.points || [];
            if (points.length === 0) {
                stroke.points = [newPoint];
                return true;
            }
            const lastPoint = points[points.length - 1];
            const lastX = lastPoint.xRatio * point.cssWidth;
            const lastY = lastPoint.yRatio * point.cssHeight;
            const dx = point.x - lastX;
            const dy = point.y - lastY;
            const distance = Math.sqrt((dx * dx) + (dy * dy));
            const replaceThreshold = options.replaceThreshold || 0;
            if (replaceThreshold > 0 && distance <= replaceThreshold) {
                points[points.length - 1] = newPoint;
                return false;
            }
            points.push(newPoint);
            return true;
        },
        distancePointToSegment(point, start, end) {
            const dx = end.x - start.x;
            const dy = end.y - start.y;
            if (dx === 0 && dy === 0) {
                const px = point.x - start.x;
                const py = point.y - start.y;
                return Math.sqrt((px * px) + (py * py));
            }
            const lengthSquared = (dx * dx) + (dy * dy);
            let t = ((point.x - start.x) * dx + (point.y - start.y) * dy) / lengthSquared;
            t = Math.max(0, Math.min(1, t));
            const projX = start.x + t * dx;
            const projY = start.y + t * dy;
            const distX = point.x - projX;
            const distY = point.y - projY;
            return Math.sqrt((distX * distX) + (distY * distY));
        },
        isPointNearEraserSegment(point, start, end, radius) {
            return this.distancePointToSegment(point, start, end) <= radius;
        },
        orientation(a, b, c) {
            const value = ((b.y - a.y) * (c.x - b.x)) - ((b.x - a.x) * (c.y - b.y));
            if (Math.abs(value) < 0.0001) return 0;
            return value > 0 ? 1 : 2;
        },
        onSegment(a, b, c) {
            return (
                b.x <= Math.max(a.x, c.x) + 0.0001 &&
                b.x + 0.0001 >= Math.min(a.x, c.x) &&
                b.y <= Math.max(a.y, c.y) + 0.0001 &&
                b.y + 0.0001 >= Math.min(a.y, c.y)
            );
        },
        segmentsIntersect(a1, a2, b1, b2) {
            const o1 = this.orientation(a1, a2, b1);
            const o2 = this.orientation(a1, a2, b2);
            const o3 = this.orientation(b1, b2, a1);
            const o4 = this.orientation(b1, b2, a2);

            if (o1 !== o2 && o3 !== o4) return true;
            if (o1 === 0 && this.onSegment(a1, b1, a2)) return true;
            if (o2 === 0 && this.onSegment(a1, b2, a2)) return true;
            if (o3 === 0 && this.onSegment(b1, a1, b2)) return true;
            if (o4 === 0 && this.onSegment(b1, a2, b2)) return true;
            return false;
        },
        distanceSegmentToSegment(a1, a2, b1, b2) {
            if (this.segmentsIntersect(a1, a2, b1, b2)) return 0;
            return Math.min(
                this.distancePointToSegment(a1, b1, b2),
                this.distancePointToSegment(a2, b1, b2),
                this.distancePointToSegment(b1, a1, a2),
                this.distancePointToSegment(b2, a1, a2),
            );
        },
        isStrokeSegmentNearEraserSegment(strokeStart, strokeEnd, eraserStart, eraserEnd, radius) {
            return this.distanceSegmentToSegment(strokeStart, strokeEnd, eraserStart, eraserEnd) <= radius;
        },
        pushUniqueStrokePoint(points, point) {
            if (!point) return;
            const last = points[points.length - 1];
            if (
                last &&
                Math.abs((last.xRatio || 0) - (point.xRatio || 0)) < 0.000001 &&
                Math.abs((last.yRatio || 0) - (point.yRatio || 0)) < 0.000001
            ) {
                return;
            }
            points.push({ ...point });
        },
        splitStrokeByEraser(stroke, start, end, cssWidth, cssHeight, radius) {
            const originalPoints = stroke.points || [];
            if (originalPoints.length === 0) return [];
            const strokeRadius = radius + ((stroke.width || this.penWidth) / 2);
            if (originalPoints.length === 1) {
                const onlyPoint = {
                    x: originalPoints[0].xRatio * cssWidth,
                    y: originalPoints[0].yRatio * cssHeight,
                };
                return this.isPointNearEraserSegment(onlyPoint, start, end, strokeRadius)
                    ? []
                    : [{ ...stroke, points: [{ ...originalPoints[0] }] }];
            }
            const chunks = [];
            let current = [];
            const commitChunk = () => {
                if (current.length >= 2) {
                    chunks.push({
                        ...stroke,
                        points: current.map(point => ({ ...point })),
                    });
                }
                current = [];
            };
            for (let index = 0; index < originalPoints.length - 1; index++) {
                const startPoint = originalPoints[index];
                const endPoint = originalPoints[index + 1];
                const strokeStart = {
                    x: startPoint.xRatio * cssWidth,
                    y: startPoint.yRatio * cssHeight,
                };
                const strokeEnd = {
                    x: endPoint.xRatio * cssWidth,
                    y: endPoint.yRatio * cssHeight,
                };
                if (this.isStrokeSegmentNearEraserSegment(strokeStart, strokeEnd, start, end, strokeRadius)) {
                    commitChunk();
                    continue;
                }
                this.pushUniqueStrokePoint(current, startPoint);
                this.pushUniqueStrokePoint(current, endPoint);
            }
            commitChunk();
            return chunks;
        },
        stampHitByEraser(stroke, canvas, idx, start, end, radius) {
            const meta = this.getCanvasMeta(idx, canvas);
            const cssWidth = meta.cssWidth;
            const cssHeight = meta.cssHeight;
            const x = (stroke.xRatio || 0) * cssWidth;
            const y = (stroke.yRatio || 0) * cssHeight;
            const ctx = canvas.getContext('2d');
            ctx.save();
            ctx.setTransform(1, 0, 0, 1, 0, 0);
            ctx.font = '16px sans-serif';
            const textWidth = ctx.measureText(stroke.text || '').width;
            ctx.restore();
            const padding = 4;
            const rect = {
                left: x - padding,
                right: x + textWidth + padding,
                top: y - 16 - padding,
                bottom: y + padding,
            };
            const samples = [
                { x: rect.left, y: rect.top },
                { x: rect.right, y: rect.top },
                { x: rect.left, y: rect.bottom },
                { x: rect.right, y: rect.bottom },
                { x: (rect.left + rect.right) / 2, y: (rect.top + rect.bottom) / 2 },
            ];
            return samples.some(point => this.isPointNearEraserSegment(point, start, end, radius));
        },
        applyEraserSegmentToPage(idx, start, end) {
            const canvas = this.$refs['drawCanvas' + idx]?.[0];
            if (!canvas) return;
            this.ensurePageState(idx);
            if (!this.drawData[idx] || this.drawData[idx].length === 0) return;
            const meta = this.getCanvasMeta(idx, canvas);
            const cssWidth = meta.cssWidth;
            const cssHeight = meta.cssHeight;
            const radius = this.eraserWidth / 2;
            const nextDrawData = [];
            let changed = false;
            (this.drawData[idx] || []).forEach(stroke => {
                if (stroke.tool === 'stamp') {
                    if (this.stampHitByEraser(stroke, canvas, idx, start, end, radius)) {
                        changed = true;
                        return;
                    }
                    nextDrawData.push(this.cloneStroke(stroke));
                    return;
                }
                const keptChunks = this.splitStrokeByEraser(stroke, start, end, cssWidth, cssHeight, radius);
                if (keptChunks.length !== 1 || (stroke.points || []).length !== (keptChunks[0]?.points || []).length) {
                    changed = true;
                }
                keptChunks.forEach(chunk => nextDrawData.push(chunk));
            });
            if (changed) {
                this.$set(this.drawData, idx, nextDrawData);
                this.redraw(idx);
            }
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
            this.clearHighlightStraightTimer();
            this.highlightStraightMode = false;
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
            this.ensurePageState(idx);
            if (this.tool === 'text') {
                const point = this.getCanvasPoint(idx, canvas, e);
                this.currentPage = idx;
                this.createTextAnnotation(idx, point);
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
                this.snapshotForHistory(idx);
                this.clearRedoHistory(idx);
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
            this.currentEraserPoint = { x: point.x, y: point.y };
            this.snapshotForHistory(idx);
            this.clearRedoHistory(idx);
            if (this.tool === 'eraser') {
                this.applyEraserSegmentToPage(idx, this.currentEraserPoint, this.currentEraserPoint);
                if (e.cancelable) e.preventDefault();
                return;
            }
            let width = this.penWidth;
            let color = this.penColor;
            if (this.tool === 'highlight') width = this.highlightWidth;
            if (this.tool === 'highlight') color = this.getCurrentHighlightColor();
            this.drawData[idx].push({
                tool: this.tool,
                width: width,
                color: color,
                points: [{
                    xRatio: point.x / point.cssWidth,
                    yRatio: point.y / point.cssHeight
                }]
            });
            if (this.shouldUseHighlightStraightAssist(pointerType)) {
                this.startHighlightStraightTimer(idx);
            }
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
            const point = this.getCanvasPoint(idx, canvas, e);
            const x = point.x;
            const y = point.y;
            if (this.tool === 'eraser') {
                this.applyEraserSegmentToPage(idx, this.currentEraserPoint || { x: this.lastX, y: this.lastY }, { x, y });
                this.currentEraserPoint = { x, y };
            } else if (this.tool === 'highlight') {
                this.prepareDrawContext(ctx, idx);
            } else {
                this.prepareDrawContext(ctx, idx);
                ctx.globalCompositeOperation = 'source-over';
                const currentStroke = (this.drawData[idx] || [])[this.drawData[idx].length - 1];
                ctx.strokeStyle = this.getStrokeColor(currentStroke);
                ctx.lineWidth = this.penWidth;
            }
            if (this.tool !== 'eraser' && this.tool !== 'highlight') {
                ctx.lineCap = "round";
                ctx.lineJoin = "round";
                ctx.beginPath();
                ctx.moveTo(this.lastX, this.lastY);
                ctx.lineTo(x, y);
                ctx.stroke();
                ctx.globalCompositeOperation = 'source-over';
            }
            this.lastX = x; this.lastY = y;
            if (this.tool !== 'eraser') {
                if (this.tool === 'highlight') {
                    const strokes = this.drawData[idx] || [];
                    const stroke = strokes[strokes.length - 1];
                    if (stroke && stroke.tool === 'highlight' && this.highlightStraightMode && stroke.points && stroke.points.length > 0) {
                        const startPoint = stroke.points[0];
                        stroke.points = [startPoint, {
                            xRatio: x / point.cssWidth,
                            yRatio: y / point.cssHeight
                        }];
                    } else {
                        const replaceThreshold = Math.max(1.5, (this.highlightWidth || 1) * 0.15);
                        this.appendPointToCurrentStroke(idx, point, { replaceThreshold });
                    }
                } else {
                    this.appendPointToCurrentStroke(idx, point);
                }
                if (this.tool === 'highlight') {
                    this.redraw(idx);
                    this.startHighlightStraightTimer(idx);
                }
            }
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
            this.currentEraserPoint = null;
            this.clearHighlightStraightTimer();
            this.highlightStraightMode = false;
            this.drawing = false;
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
                if (stroke.tool === 'text') {
                    return;
                }
                if (!stroke.points || stroke.points.length === 0) return;
                if (stroke.tool === 'highlight') {
                    ctx.globalCompositeOperation = 'source-over';
                    ctx.strokeStyle = this.getStrokeColor(stroke);
                    ctx.lineWidth = stroke.width || this.highlightWidth;
                    ctx.lineCap = "butt";
                    ctx.lineJoin = "round";
                } else {
                    ctx.globalCompositeOperation = 'source-over';
                    ctx.strokeStyle = this.getStrokeColor(stroke);
                    ctx.lineWidth = stroke.width || this.penWidth;
                    ctx.lineCap = "round";
                    ctx.lineJoin = "round";
                }
                ctx.beginPath();
                for (let i = 0; i < stroke.points.length; i++) {
                    const pt = stroke.points[i];
                    const x = pt.xRatio * cssWidth;
                    const y = pt.yRatio * cssHeight;
                    if (i == 0) ctx.moveTo(x, y);
                    else ctx.lineTo(x, y);
                }
                ctx.stroke();
                ctx.globalCompositeOperation = 'source-over';
            });
        },
        undo(idx) {
            this.ensurePageState(idx);
            if (!this.historyStack[idx] || this.historyStack[idx].length === 0) return;
            this.undoStack[idx].push(this.clonePageDrawData(idx));
            const snapshot = this.historyStack[idx].pop();
            this.restorePageDrawData(idx, snapshot);
        },
        redo(idx) {
            this.ensurePageState(idx);
            if (!this.undoStack[idx] || this.undoStack[idx].length === 0) return;
            this.historyStack[idx].push(this.clonePageDrawData(idx));
            const snapshot = this.undoStack[idx].pop();
            this.restorePageDrawData(idx, snapshot);
        },
        saveGrading() {
            this.finalizeActiveTextEditor();
            let images = [];
            this.pdfPages.forEach((_, idx) => {
                images.push(this.exportCanvasDataUrl(idx));
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
                this.$set(this.pageMeta, i, { cssWidth, cssHeight, dpr });
                this.$set(this.loadedPages, i, true);
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
        this.finalizeActiveTextEditor();
        this.clearSimilarityProgressTimer();
    }
});
