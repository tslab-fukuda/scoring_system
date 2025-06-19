new Vue({
    el: '#final-score-table',
    data: {
        students: STUDENTS_DATA,
        experimentNumbers: EXPERIMENT_NUMBERS,
        sortField: '',
        sortAsc: true,
        filters: { day: '', group: '' }
    },
    computed: {
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
        }
    },
    methods: {
        toggleSort(field) {
            if (this.sortField === field) {
                this.sortAsc = !this.sortAsc;
            } else {
                this.sortField = field;
                this.sortAsc = true;
            }
        }
    }
});
