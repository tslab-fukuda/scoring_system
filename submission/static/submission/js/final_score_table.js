new Vue({
    el: '#final-score-table',
    data: {
        students: STUDENTS_DATA,
        experimentNumbers: EXPERIMENT_NUMBERS,
        sortField: '',
        sortAsc: true,
        filters: { day: '', group: '' },
        offerings: (FINAL_SCORE_META && FINAL_SCORE_META.offerings) || [],
        selectedOfferingId: (FINAL_SCORE_META && FINAL_SCORE_META.defaultOfferingId) || null,
        selectedCourseId: '',
        selectedYear: '',
    },
    computed: {
        courseOptions() {
            const map = {};
            this.offerings.forEach(o => {
                map[o.course_id] = { course_id: o.course_id, course_code: o.course_code, course_name: o.course_name };
            });
            return Object.values(map);
        },
        yearOptions() {
            const years = this.offerings
                .filter(o => !this.selectedCourseId || String(o.course_id) === String(this.selectedCourseId))
                .map(o => o.year);
            return Array.from(new Set(years)).sort((a, b) => b - a);
        },
        processedStudents() {
            let list = this.students.slice();
            if (this.filters.day) list = list.filter(s => s.experiment_day === this.filters.day);
            if (this.filters.group) list = list.filter(s => s.experiment_group === this.filters.group);
            if (this.sortField) {
                list.sort((a, b) => {
                    const av = a[this.sortField] || '';
                    const bv = b[this.sortField] || '';
                    if (typeof av === 'number' && typeof bv === 'number') {
                        return this.sortAsc ? av - bv : bv - av;
                    }
                    return this.sortAsc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
                });
            }
            return list;
        },
        csvUrl() {
            const params = [];
            if (this.selectedOfferingId) params.push(`offering_id=${encodeURIComponent(this.selectedOfferingId)}`);
            if (this.filters.day) params.push(`day=${encodeURIComponent(this.filters.day)}`);
            if (this.filters.group) params.push(`group=${encodeURIComponent(this.filters.group)}`);
            const query = params.length ? `?${params.join('&')}` : '';
            return `/submission/final_score_list/csv/${query}`;
        },
        acceptedUrl() {
            const params = [];
            if (this.selectedOfferingId) params.push(`offering_id=${encodeURIComponent(this.selectedOfferingId)}`);
            if (this.filters.day) params.push(`day=${encodeURIComponent(this.filters.day)}`);
            if (this.filters.group) params.push(`group=${encodeURIComponent(this.filters.group)}`);
            const query = params.length ? `?${params.join('&')}` : '';
            return `/submission/final_score_list/download_accepted/${query}`;
        }
    },
    methods: {
        syncSelectionFromOffering() {
            const current = this.offerings.find(o => Number(o.id) === Number(this.selectedOfferingId));
            if (current) {
                this.selectedCourseId = String(current.course_id);
                this.selectedYear = String(current.year);
            }
        },
        resolveOfferingId() {
            if (this.selectedCourseId && this.selectedYear) {
                const found = this.offerings.find(
                    o => String(o.course_id) === String(this.selectedCourseId) && String(o.year) === String(this.selectedYear)
                );
                return found ? found.id : null;
            }
            return null;
        },
        fetchStudents() {
            const offeringId = this.resolveOfferingId();
            this.selectedOfferingId = offeringId;
            const params = offeringId ? `?offering_id=${encodeURIComponent(offeringId)}` : '';
            fetch(`/submission/final_score_list/data/${params}`)
                .then(r => r.json())
                .then(data => {
                    this.students = data.students || [];
                    this.experimentNumbers = data.experiment_numbers || this.experimentNumbers;
                });
        },
        toggleSort(field) {
            if (this.sortField === field) {
                this.sortAsc = !this.sortAsc;
            } else {
                this.sortField = field;
                this.sortAsc = true;
            }
        }
    },
    watch: {
        selectedCourseId(newVal, oldVal) {
            if (!newVal) {
                this.selectedYear = '';
                this.students = [];
                return;
            }
            if (oldVal && newVal !== oldVal) {
                this.selectedYear = '';
            }
        },
        selectedYear() {
            if (!this.selectedCourseId || !this.selectedYear) {
                this.students = [];
                return;
            }
            this.fetchStudents();
        }
    },
    mounted() {
        this.syncSelectionFromOffering();
        if (this.selectedCourseId && this.selectedYear) {
            this.fetchStudents();
        }
    }
});
