(function () {
    function defaultOptionLabel(index) {
        const labels = ['S', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I'];
        return labels[index] || `評価${index + 1}`;
    }

    function defaultOptionDescription(index) {
        const descriptions = [
            'よくできている',
            'そこそこできている',
            '一部不十分',
            '不十分箇所が多い',
            '書いているだけ',
            '書いていない',
        ];
        return descriptions[index] || '';
    }

    function computeOptionPoints(maxPoints, optionCount) {
        const safeMaxPoints = Math.max(0, Number(maxPoints) || 0);
        const safeOptionCount = Math.max(1, Number(optionCount) || 1);
        if (safeOptionCount === 1) return [safeMaxPoints];
        const denominator = safeOptionCount - 1;
        const points = [];
        for (let index = 0; index < safeOptionCount; index += 1) {
            const ratio = (denominator - index) / denominator;
            points.push(Math.round(safeMaxPoints * ratio));
        }
        return points;
    }

    function cloneCriteria(criteria) {
        return (criteria || []).map((criterion) => ({
            source_criterion_id: criterion.source_criterion_id || criterion.id || null,
            title: criterion.title || '',
            max_points: Number(criterion.max_points || 0),
            order: Number(criterion.order || 0),
            options: (criterion.options || []).map((option, optionIndex) => ({
                source_option_id: option.source_option_id || option.id || null,
                label: option.label || defaultOptionLabel(optionIndex),
                description: option.description || '',
                points: Number(option.points || 0),
                order: Number(option.order || optionIndex),
            })),
        }));
    }

    new Vue({
        el: '#final-rubric-settings',
        data: {
            offerings: (window.finalRubricOfferings && window.finalRubricOfferings.offerings) || [],
            selectedOfferingId: (window.finalRubricOfferings && window.finalRubricOfferings.defaultOfferingId) || null,
            selectedCourseId: null,
            selectedYear: null,
            selectedExperimentNumber: (window.finalRubricSettings && window.finalRubricSettings.initialExperimentNumber) || '',
            selectedScope: (window.finalRubricSettings && window.finalRubricSettings.initialScope) || 'offering',
            canEditDefault: !!(window.finalRubricSettings && window.finalRubricSettings.canEditDefault),
            criteria: [],
            activeVersion: null,
            loadedFrom: null,
            copyCandidates: [],
            selectedSourceRubricId: '',
            showExportGuide: false,
            loading: false,
            saving: false,
            errorMessage: '',
            saveMessage: '',
        },
        computed: Object.assign({}, window.offeringSelectorHelper.computed, {
            selectedOffering() {
                return (this.offerings || []).find((offering) => Number(offering.id) === Number(this.selectedOfferingId)) || null;
            },
            experimentNumberOptions() {
                if (!this.selectedOffering || !Array.isArray(this.selectedOffering.experiment_numbers)) return [];
                return this.selectedOffering.experiment_numbers;
            },
            rubricMaxScore() {
                return this.criteria.reduce((sum, criterion) => sum + (Number(criterion.max_points) || 0), 0);
            },
            selectedScopeLabel() {
                return this.selectedScope === 'default' ? 'デフォルト' : '年度個別';
            },
            requiresExperimentNumber() {
                return this.selectedScope !== 'default';
            },
            canEditCurrent() {
                if (this.selectedScope === 'default') return this.canEditDefault;
                return true;
            },
        }),
        watch: {
            selectedOfferingId() {
                this.syncExperimentSelection();
                this.loadRubricDefinition();
            },
            selectedExperimentNumber(newValue, oldValue) {
                if (this.requiresExperimentNumber && newValue && newValue !== oldValue) {
                    this.loadRubricDefinition();
                }
            },
            selectedScope(newValue, oldValue) {
                if (newValue && newValue !== oldValue) {
                    this.loadRubricDefinition();
                }
            },
        },
        methods: Object.assign({}, window.offeringSelectorHelper.methods, {
            selectScope(scope) {
                this.selectedScope = scope === 'default' ? 'default' : 'offering';
            },
            triggerImport() {
                if (this.loading || !this.canEditCurrent) return;
                if (this.$refs.importFileInput) {
                    this.$refs.importFileInput.value = '';
                    this.$refs.importFileInput.click();
                }
            },
            openExportGuide() {
                if (this.loading || !this.criteria.length) return;
                if (this.requiresExperimentNumber && !this.selectedExperimentNumber) return;
                this.showExportGuide = true;
            },
            closeExportGuide() {
                this.showExportGuide = false;
            },
            syncExperimentSelection() {
                const numbers = this.experimentNumberOptions;
                if (!this.requiresExperimentNumber) {
                    return;
                }
                if (!numbers.length) {
                    this.selectedExperimentNumber = '';
                    this.criteria = [];
                    return;
                }
                if (!numbers.includes(this.selectedExperimentNumber)) {
                    this.selectedExperimentNumber = numbers[0];
                }
            },
            normalizeLoadedCriteria(criteria) {
                const normalized = cloneCriteria(criteria);
                normalized.forEach((criterion, index) => {
                    criterion.order = index;
                    this.refreshCriterionPoints(criterion);
                });
                return normalized;
            },
            loadRubricDefinition(sourceRubricId = '') {
                if (!this.selectedOfferingId) return;
                if (this.requiresExperimentNumber && !this.selectedExperimentNumber) return;
                this.loading = true;
                this.errorMessage = '';
                this.saveMessage = '';
                const params = new URLSearchParams({
                    offering_id: this.selectedOfferingId,
                    scope: this.selectedScope,
                });
                if (this.requiresExperimentNumber && this.selectedExperimentNumber) {
                    params.set('experiment_number', this.selectedExperimentNumber);
                }
                if (sourceRubricId) {
                    params.set('source_rubric_id', sourceRubricId);
                }
                fetch(`/submission/final_rubric_definition_api/?${params.toString()}`)
                    .then((response) => response.json())
                    .then((data) => {
                        if (data.status !== 'ok') {
                            this.errorMessage = data.message || '評価基準の取得に失敗しました';
                            return;
                        }
                        this.criteria = this.normalizeLoadedCriteria((data.rubric_payload || {}).criteria || []);
                        this.activeVersion = data.active_version;
                        this.loadedFrom = data.loaded_from || null;
                        this.copyCandidates = data.copy_candidates || [];
                        this.selectedSourceRubricId = '';
                    })
                    .catch(() => {
                        this.errorMessage = '評価基準の取得に失敗しました';
                    })
                    .finally(() => {
                        this.loading = false;
                    });
            },
            applyCopySource() {
                if (!this.selectedSourceRubricId) return;
                this.loadRubricDefinition(this.selectedSourceRubricId);
            },
            handleImportFile(event) {
                const file = event && event.target && event.target.files ? event.target.files[0] : null;
                if (!file || !this.selectedOfferingId) return;
                if (this.requiresExperimentNumber && !this.selectedExperimentNumber) return;
                this.loading = true;
                this.errorMessage = '';
                this.saveMessage = '';
                const formData = new FormData();
                formData.append('file', file);
                formData.append('offering_id', this.selectedOfferingId);
                if (this.requiresExperimentNumber && this.selectedExperimentNumber) {
                    formData.append('experiment_number', this.selectedExperimentNumber);
                }
                formData.append('scope', this.selectedScope);
                fetch('/submission/final_rubric_import_api/', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': window.csrfToken,
                    },
                    body: formData,
                })
                    .then((response) => response.json())
                    .then((data) => {
                        if (data.status !== 'ok') {
                            this.errorMessage = data.message || 'Excel の読み込みに失敗しました';
                            return;
                        }
                        this.criteria = this.normalizeLoadedCriteria((data.rubric_payload || {}).criteria || []);
                        this.loadedFrom = null;
                        this.selectedSourceRubricId = '';
                        this.saveMessage = data.message || 'Excel を読み込みました';
                    })
                    .catch(() => {
                        this.errorMessage = 'Excel の読み込みに失敗しました';
                    })
                    .finally(() => {
                        this.loading = false;
                        if (this.$refs.importFileInput) {
                            this.$refs.importFileInput.value = '';
                        }
                    });
            },
            addCriterion() {
                const optionCount = this.criteria[0] ? this.criteria[0].options.length : 6;
                const points = computeOptionPoints(5, optionCount);
                this.criteria.push({
                    source_criterion_id: null,
                    title: `クライテリア${this.criteria.length + 1}`,
                    max_points: 5,
                    order: this.criteria.length,
                    options: Array.from({ length: optionCount }).map((_, index) => ({
                        source_option_id: null,
                        label: defaultOptionLabel(index),
                        description: defaultOptionDescription(index),
                        points: points[index],
                        order: index,
                    })),
                });
            },
            removeCriterion(index) {
                if (this.criteria.length <= 1) return;
                this.criteria.splice(index, 1);
                this.criteria.forEach((criterion, criterionIndex) => {
                    criterion.order = criterionIndex;
                });
            },
            changeOptionCount(criterion, nextCountValue) {
                const nextCount = Math.max(2, Math.min(10, Number(nextCountValue) || 2));
                const currentOptions = criterion.options || [];
                const nextOptions = [];
                for (let index = 0; index < nextCount; index += 1) {
                    const existing = currentOptions[index] || {};
                    nextOptions.push({
                        source_option_id: existing.source_option_id || null,
                        label: existing.label || defaultOptionLabel(index),
                        description: existing.description || defaultOptionDescription(index),
                        points: 0,
                        order: index,
                    });
                }
                criterion.options = nextOptions;
                this.refreshCriterionPoints(criterion);
            },
            refreshCriterionPoints(criterion) {
                const points = computeOptionPoints(criterion.max_points, criterion.options.length);
                criterion.options.forEach((option, index) => {
                    option.order = index;
                    option.points = points[index];
                    if (!option.label) option.label = defaultOptionLabel(index);
                    if (!option.description && option.description !== '') {
                        option.description = defaultOptionDescription(index);
                    }
                });
            },
            buildPayload() {
                return {
                    criteria: this.criteria.map((criterion, criterionIndex) => ({
                        source_criterion_id: criterion.source_criterion_id || null,
                        title: String(criterion.title || '').trim(),
                        max_points: Number(criterion.max_points || 0),
                        order: criterionIndex,
                        options: (criterion.options || []).map((option, optionIndex) => ({
                            source_option_id: option.source_option_id || null,
                            label: String(option.label || '').trim() || defaultOptionLabel(optionIndex),
                            description: String(option.description || '').trim(),
                            order: optionIndex,
                        })),
                    })),
                };
            },
            exportRubric() {
                if (!this.selectedOfferingId) return;
                if (this.requiresExperimentNumber && !this.selectedExperimentNumber) return;
                if (!this.criteria.length) {
                    this.errorMessage = 'エクスポートするクライテリアがありません';
                    return;
                }
                this.showExportGuide = false;
                this.loading = true;
                this.errorMessage = '';
                this.saveMessage = '';
                fetch('/submission/final_rubric_export_api/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': window.csrfToken,
                    },
                    body: JSON.stringify({
                        offering_id: this.selectedOfferingId,
                        experiment_number: this.requiresExperimentNumber ? this.selectedExperimentNumber : '',
                        scope: this.selectedScope,
                        payload: this.buildPayload(),
                    }),
                })
                    .then(async (response) => {
                        if (!response.ok) {
                            let message = 'Excel のエクスポートに失敗しました';
                            try {
                                const data = await response.json();
                                message = data.message || message;
                            } catch (error) {
                                // ignore JSON parse failure and use default message
                            }
                            throw new Error(message);
                        }
                        const blob = await response.blob();
                        const disposition = response.headers.get('Content-Disposition') || '';
                        const matched = disposition.match(/filename=\"?([^"]+)\"?/);
                        const filename = matched ? matched[1] : 'final_rubric.xlsx';
                        const objectUrl = window.URL.createObjectURL(blob);
                        const link = document.createElement('a');
                        link.href = objectUrl;
                        link.download = filename;
                        document.body.appendChild(link);
                        link.click();
                        link.remove();
                        window.URL.revokeObjectURL(objectUrl);
                        this.saveMessage = 'Excel をエクスポートしました';
                    })
                    .catch((error) => {
                        this.errorMessage = error.message || 'Excel のエクスポートに失敗しました';
                    })
                    .finally(() => {
                        this.loading = false;
                    });
            },
            saveRubric() {
                if (!this.selectedOfferingId) return;
                if (this.requiresExperimentNumber && !this.selectedExperimentNumber) return;
                if (!this.criteria.length) {
                    this.errorMessage = 'クライテリアを1件以上設定してください';
                    return;
                }
                if (Number(this.rubricMaxScore) !== 100) {
                    this.errorMessage = `合計満点が100点ではありません。現在は ${this.rubricMaxScore} 点です。100点に調整してから保存してください。`;
                    return;
                }
                if (!this.canEditCurrent) {
                    this.errorMessage = 'この基準は編集できません';
                    return;
                }
                if (this.criteria.some((criterion) => !String(criterion.title || '').trim())) {
                    this.errorMessage = 'クライテリア名が未入力の行があります';
                    return;
                }
                this.saving = true;
                this.errorMessage = '';
                this.saveMessage = '';
                fetch('/submission/final_rubric_definition_api/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': window.csrfToken,
                    },
                    body: JSON.stringify({
                        offering_id: this.selectedOfferingId,
                        experiment_number: this.requiresExperimentNumber ? this.selectedExperimentNumber : '',
                        scope: this.selectedScope,
                        source_rubric_id: this.loadedFrom ? this.loadedFrom.id : null,
                        payload: this.buildPayload(),
                    }),
                })
                    .then((response) => response.json())
                    .then((data) => {
                        if (data.status !== 'ok') {
                            this.errorMessage = data.message || '評価基準の保存に失敗しました';
                            return;
                        }
                        this.criteria = this.normalizeLoadedCriteria((data.rubric_payload || {}).criteria || []);
                        this.activeVersion = data.active_version;
                        this.loadedFrom = {
                            id: (data.rubric_payload || {}).id || null,
                            scope: this.selectedScope,
                            scope_label: this.selectedScopeLabel,
                            year: this.selectedOffering ? this.selectedOffering.year : null,
                            experiment_number: this.selectedExperimentNumber,
                            version: data.active_version,
                        };
                        this.saveMessage = data.message || '評価基準を保存しました';
                    })
                    .catch(() => {
                        this.errorMessage = '評価基準の保存に失敗しました';
                    })
                    .finally(() => {
                        this.saving = false;
                    });
            },
        }),
        mounted() {
            this.ensureOfferingSelected();
            this.syncExperimentSelection();
            this.loadRubricDefinition();
        },
    });
})();
