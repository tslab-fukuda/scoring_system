(function () {
    new Vue({
        el: '#help-ticket-history-app',
        data: {
            offerings: (window.helpTicketHistoryConfig && window.helpTicketHistoryConfig.offerings) || [],
            selectedOfferingId: (window.helpTicketHistoryConfig && window.helpTicketHistoryConfig.defaultOfferingId) || null,
            selectedCourseId: null,
            selectedYear: null,
            actualRole: (window.helpTicketHistoryConfig && window.helpTicketHistoryConfig.actualRole) || '',
            filters: {
                status: 'resolved',
                requestType: 'all',
                resolutionCategory: 'all',
                experimentGroup: '',
                experimentNumber: '',
                createdDate: '',
            },
            tickets: [],
            loading: false,
            errorMessage: '',
            showDetailModal: false,
            selectedTicket: null,
            detailLoading: false,
            detailError: '',
        },
        computed: Object.assign({}, window.offeringSelectorHelper.computed, {
            selectedOffering() {
                return (this.offerings || []).find((offering) => Number(offering.id) === Number(this.selectedOfferingId)) || null;
            },
            experimentNumberOptions() {
                if (!this.selectedOffering || !Array.isArray(this.selectedOffering.experiment_numbers)) return [];
                return this.selectedOffering.experiment_numbers;
            },
            isStudent() {
                return this.actualRole === 'student';
            },
        }),
        watch: {
            selectedOfferingId() {
                this.syncExperimentNumber();
                this.fetchTickets();
            },
        },
        methods: Object.assign({}, window.offeringSelectorHelper.methods, {
            syncExperimentNumber() {
                if (this.filters.experimentNumber && !this.experimentNumberOptions.includes(this.filters.experimentNumber)) {
                    this.filters.experimentNumber = '';
                }
            },
            clearFilters() {
                this.filters.status = 'resolved';
                this.filters.requestType = 'all';
                this.filters.resolutionCategory = 'all';
                this.filters.experimentGroup = '';
                this.filters.experimentNumber = '';
                this.filters.createdDate = '';
                this.fetchTickets();
            },
            fetchTickets() {
                if (!this.selectedOfferingId) {
                    this.tickets = [];
                    return;
                }
                this.loading = true;
                this.errorMessage = '';
                const params = new URLSearchParams({
                    offering_id: this.selectedOfferingId,
                    status: this.filters.status,
                    request_type: this.filters.requestType,
                });
                if (!this.isStudent) {
                    params.set('resolution_category', this.filters.resolutionCategory);
                }
                if (this.filters.experimentGroup) params.set('experiment_group', this.filters.experimentGroup);
                if (this.filters.experimentNumber) params.set('experiment_number', this.filters.experimentNumber);
                if (this.filters.createdDate) params.set('created_date', this.filters.createdDate);
                fetch(`/attendance/help_ticket_history/api/?${params.toString()}`, {
                    credentials: 'same-origin',
                })
                    .then((response) => response.json())
                    .then((data) => {
                        if (data.status !== 'ok') {
                            throw new Error(data.message || '履歴の取得に失敗しました');
                        }
                        this.tickets = data.tickets || [];
                    })
                    .catch((error) => {
                        this.tickets = [];
                        this.errorMessage = error.message || '履歴の取得に失敗しました';
                    })
                    .finally(() => {
                        this.loading = false;
                    });
            },
            openDetail(ticket) {
                this.selectedTicket = null;
                this.detailError = '';
                this.detailLoading = true;
                this.showDetailModal = true;
                const params = new URLSearchParams({
                    kind: 'experiment_help',
                    id: ticket.id,
                });
                fetch(`/attendance/notifications/detail/?${params.toString()}`, {
                    credentials: 'same-origin',
                })
                    .then((response) => response.json())
                    .then((data) => {
                        if (data.status !== 'ok') {
                            throw new Error(data.message || '詳細の取得に失敗しました');
                        }
                        this.selectedTicket = data.notification || null;
                    })
                    .catch((error) => {
                        this.selectedTicket = null;
                        this.detailError = error.message || '詳細の取得に失敗しました';
                    })
                    .finally(() => {
                        this.detailLoading = false;
                    });
            },
            closeDetail() {
                this.showDetailModal = false;
                this.selectedTicket = null;
                this.detailLoading = false;
                this.detailError = '';
            },
        }),
        mounted() {
            this.ensureOfferingSelected();
            this.syncExperimentNumber();
            if (this.selectedOfferingId) {
                this.fetchTickets();
            }
        },
    });
})();
