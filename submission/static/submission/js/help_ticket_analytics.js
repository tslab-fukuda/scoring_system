(function () {
    function emptyAnalytics() {
        return {
            summary: {
                total_count: 0,
                question_count: 0,
                call_count: 0,
                unclassified_count: 0,
            },
            charts: {
                resolution_category: { labels: [], counts: [], keys: [] },
                request_type_ratio: { labels: [], counts: [], keys: [] },
                hourly: { labels: [], counts: [] },
                session: { labels: [], datasets: [] },
                resolution_experiment: { labels: [], datasets: [] },
            },
            tables: {
                handled_by: [],
                experiment_group: [],
            },
            response_time: {
                resolved_count: 0,
                average_minutes: 0,
                median_minutes: 0,
                max_minutes: 0,
            },
        };
    }

    function destroyChart(chart) {
        if (chart) {
            chart.destroy();
        }
        return null;
    }

    new Vue({
        el: '#help-ticket-analytics-app',
        data: {
            offerings: (window.helpTicketAnalyticsConfig && window.helpTicketAnalyticsConfig.offerings) || [],
            selectedOfferingId: (window.helpTicketAnalyticsConfig && window.helpTicketAnalyticsConfig.defaultOfferingId) || null,
            selectedCourseId: null,
            selectedYear: null,
            actualRole: (window.helpTicketAnalyticsConfig && window.helpTicketAnalyticsConfig.actualRole) || '',
            filters: {
                dateFrom: '',
                dateTo: '',
                status: 'resolved',
                requestType: 'all',
                resolutionCategory: 'all',
            },
            analytics: emptyAnalytics(),
            loading: false,
            errorMessage: '',
            charts: {
                resolutionCategory: null,
                requestType: null,
                hourly: null,
                daily: null,
                resolutionExperiment: null,
                handledBy: null,
                experimentGroup: null,
            },
        },
        computed: Object.assign({}, window.offeringSelectorHelper.computed, {
            selectedOffering() {
                return (this.offerings || []).find((offering) => Number(offering.id) === Number(this.selectedOfferingId)) || null;
            },
        }),
        watch: {
            selectedOfferingId() {
                this.fetchAnalytics();
            },
        },
        methods: Object.assign({}, window.offeringSelectorHelper.methods, {
            chartWrapStyle(kind) {
                if (kind === 'handledBy') {
                    const count = ((this.analytics.tables.handled_by || []).length);
                    return {
                        height: `${Math.max(280, count * 38)}px`,
                    };
                }
                if (kind === 'experimentGroup') {
                    const count = ((((this.analytics.tables.experiment_group || {}).labels) || []).length);
                    return {
                        height: `${Math.max(460, count * 30)}px`,
                    };
                }
                return {};
            },
            clearFilters() {
                this.filters.dateFrom = '';
                this.filters.dateTo = '';
                this.filters.status = 'resolved';
                this.filters.requestType = 'all';
                this.filters.resolutionCategory = 'all';
                this.fetchAnalytics();
            },
            fetchAnalytics() {
                if (!this.selectedOfferingId) {
                    this.analytics = emptyAnalytics();
                    this.renderCharts();
                    return;
                }
                this.loading = true;
                this.errorMessage = '';
                const params = new URLSearchParams({
                    offering_id: this.selectedOfferingId,
                    status: this.filters.status,
                    request_type: this.filters.requestType,
                    resolution_category: this.filters.resolutionCategory,
                });
                if (this.filters.dateFrom) params.set('date_from', this.filters.dateFrom);
                if (this.filters.dateTo) params.set('date_to', this.filters.dateTo);
                fetch(`/attendance/help_ticket_analytics/api/?${params.toString()}`, {
                    credentials: 'same-origin',
                })
                    .then((response) => response.json())
                    .then((data) => {
                        if (data.status !== 'ok') {
                            throw new Error(data.message || '分析データの取得に失敗しました');
                        }
                        this.analytics = data.analytics || emptyAnalytics();
                        this.$nextTick(() => this.renderCharts());
                    })
                    .catch((error) => {
                        this.analytics = emptyAnalytics();
                        this.renderCharts();
                        this.errorMessage = error.message || '分析データの取得に失敗しました';
                    })
                    .finally(() => {
                        this.loading = false;
                    });
            },
            renderCharts() {
                if (typeof Chart === 'undefined') return;
                const palette = ['#0d6efd', '#ffc107', '#dc3545', '#198754'];
                const darkPalette = ['#7fb1ff', '#ffe08a', '#ff9aa6', '#8ae2b8'];
                const isDark = document.body.classList.contains('dark-mode');
                const colors = isDark ? darkPalette : palette;
                const tickColor = isDark ? '#e5e7eb' : '#374151';
                const gridColor = isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.08)';

                this.charts.resolutionCategory = destroyChart(this.charts.resolutionCategory);
                this.charts.requestType = destroyChart(this.charts.requestType);
                this.charts.hourly = destroyChart(this.charts.hourly);
                this.charts.daily = destroyChart(this.charts.daily);
                this.charts.resolutionExperiment = destroyChart(this.charts.resolutionExperiment);
                this.charts.handledBy = destroyChart(this.charts.handledBy);
                this.charts.experimentGroup = destroyChart(this.charts.experimentGroup);

                const resolutionCtx = document.getElementById('analytics-resolution-chart');
                if (resolutionCtx) {
                    this.charts.resolutionCategory = new Chart(resolutionCtx, {
                        type: 'bar',
                        data: {
                            labels: this.analytics.charts.resolution_category.labels,
                            datasets: [{
                                label: '件数',
                                data: this.analytics.charts.resolution_category.counts,
                                backgroundColor: colors,
                            }],
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { display: false } },
                            scales: {
                                x: {
                                    ticks: { color: tickColor, autoSkip: false, maxRotation: 0, minRotation: 0 },
                                    grid: { color: gridColor },
                                },
                                y: { beginAtZero: true, ticks: { color: tickColor }, grid: { color: gridColor } },
                            },
                        },
                    });
                }

                const requestCtx = document.getElementById('analytics-request-type-chart');
                if (requestCtx) {
                    this.charts.requestType = new Chart(requestCtx, {
                        type: 'doughnut',
                        data: {
                            labels: this.analytics.charts.request_type_ratio.labels,
                            datasets: [{
                                data: this.analytics.charts.request_type_ratio.counts,
                                backgroundColor: colors.slice(0, 2),
                            }],
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: {
                                    position: 'bottom',
                                    labels: { color: tickColor },
                                },
                            },
                        },
                    });
                }

                const hourlyCtx = document.getElementById('analytics-hourly-chart');
                if (hourlyCtx) {
                    this.charts.hourly = new Chart(hourlyCtx, {
                        type: 'bar',
                        data: {
                            labels: this.analytics.charts.hourly.labels,
                            datasets: [{
                                label: '件数',
                                data: this.analytics.charts.hourly.counts,
                                backgroundColor: colors[0],
                            }],
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { display: false } },
                            scales: {
                                x: {
                                    ticks: { color: tickColor, autoSkip: false, maxRotation: 55, minRotation: 55, font: { size: 10 } },
                                    grid: { color: gridColor },
                                },
                                y: { beginAtZero: true, ticks: { color: tickColor }, grid: { color: gridColor } },
                            },
                        },
                    });
                }

                const dailyCtx = document.getElementById('analytics-daily-chart');
                if (dailyCtx) {
                    this.charts.daily = new Chart(dailyCtx, {
                        type: 'bar',
                        data: {
                            labels: this.analytics.charts.session.labels,
                            datasets: (this.analytics.charts.session.datasets || []).map((dataset, index) => ({
                                label: dataset.label,
                                data: dataset.counts,
                                backgroundColor: colors[index % colors.length],
                            })),
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { labels: { color: tickColor } } },
                            scales: {
                                x: {
                                    ticks: { color: tickColor, autoSkip: false, maxRotation: 35, minRotation: 35, font: { size: 10 } },
                                    grid: { color: gridColor },
                                },
                                y: { beginAtZero: true, ticks: { color: tickColor }, grid: { color: gridColor } },
                            },
                        },
                    });
                }

                const resolutionExperimentCtx = document.getElementById('analytics-resolution-experiment-chart');
                if (resolutionExperimentCtx) {
                    this.charts.resolutionExperiment = new Chart(resolutionExperimentCtx, {
                        type: 'bar',
                        data: {
                            labels: this.analytics.charts.resolution_experiment.labels,
                            datasets: (this.analytics.charts.resolution_experiment.datasets || []).map((dataset, index) => ({
                                label: dataset.label,
                                data: dataset.counts,
                                backgroundColor: colors[index % colors.length],
                            })),
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { labels: { color: tickColor } } },
                            scales: {
                                x: {
                                    stacked: true,
                                    ticks: { color: tickColor, autoSkip: false, maxRotation: 35, minRotation: 35, font: { size: 10 } },
                                    grid: { color: gridColor },
                                },
                                y: { stacked: true, beginAtZero: true, ticks: { color: tickColor }, grid: { color: gridColor } },
                            },
                        },
                    });
                }

                const handlerCtx = document.getElementById('analytics-handler-chart');
                if (handlerCtx) {
                    this.charts.handledBy = new Chart(handlerCtx, {
                        type: 'bar',
                        data: {
                            labels: (this.analytics.tables.handled_by || []).map((item) => item.label),
                            datasets: [{
                                label: '件数',
                                data: (this.analytics.tables.handled_by || []).map((item) => item.count),
                                backgroundColor: colors[1],
                            }],
                        },
                        options: {
                            indexAxis: 'y',
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { display: false } },
                            scales: {
                                x: { beginAtZero: true, ticks: { color: tickColor }, grid: { color: gridColor } },
                                y: { ticks: { color: tickColor, autoSkip: false }, grid: { color: gridColor } },
                            },
                        },
                    });
                }

                const groupCtx = document.getElementById('analytics-group-chart');
                if (groupCtx) {
                    this.charts.experimentGroup = new Chart(groupCtx, {
                        type: 'bar',
                        data: {
                            labels: ((this.analytics.tables.experiment_group || {}).labels || []),
                            datasets: (((this.analytics.tables.experiment_group || {}).datasets) || []).map((dataset, index) => ({
                                label: dataset.label,
                                data: dataset.counts,
                                backgroundColor: colors[index % colors.length],
                            })),
                        },
                        options: {
                            indexAxis: 'y',
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { labels: { color: tickColor } } },
                            scales: {
                                x: { beginAtZero: true, ticks: { color: tickColor }, grid: { color: gridColor } },
                                y: { ticks: { color: tickColor, autoSkip: false }, grid: { color: gridColor } },
                            },
                        },
                    });
                }
            },
        }),
        mounted() {
            this.ensureOfferingSelected();
            if (this.selectedOfferingId) {
                this.fetchAnalytics();
            } else {
                this.renderCharts();
            }
        },
        beforeDestroy() {
            Object.keys(this.charts).forEach((key) => {
                this.charts[key] = destroyChart(this.charts[key]);
            });
        },
    });
})();
