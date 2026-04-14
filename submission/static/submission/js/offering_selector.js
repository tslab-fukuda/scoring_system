(function () {
    function normalizeNumber(value) {
        const numeric = Number(value);
        return Number.isNaN(numeric) ? null : numeric;
    }

    function uniqueYears(offerings, courseId) {
        const years = offerings
            .filter(o => !courseId || String(o.course_id) === String(courseId))
            .map(o => o.year);
        return Array.from(new Set(years)).sort((a, b) => Number(a) - Number(b));
    }

    window.offeringSelectorHelper = {
        computed: {
            showOfferingSelector() {
                return true;
            },
            courseOptions() {
                const map = {};
                (this.offerings || []).forEach(o => {
                    if (!map[o.course_id]) {
                        map[o.course_id] = {
                            course_id: o.course_id,
                            course_code: o.course_code,
                            course_name: o.course_name,
                        };
                    }
                });
                return Object.values(map);
            },
            yearOptions() {
                return uniqueYears(this.offerings || [], this.selectedCourseId);
            },
        },
        methods: {
            resolveOfferingId(courseId, year) {
                const candidate = (this.offerings || [])
                    .filter(o => String(o.course_id) === String(courseId) && String(o.year) === String(year))
                    .sort((a, b) => (Number(b.year) - Number(a.year)) || (Number(b.id) - Number(a.id)));
                return candidate.length ? normalizeNumber(candidate[0].id) : null;
            },
            ensureOfferingSelected() {
                if (this.selectedOfferingId) {
                    const current = (this.offerings || []).find(o => Number(o.id) === Number(this.selectedOfferingId));
                    if (current) {
                        this.selectedCourseId = current.course_id;
                        this.selectedYear = current.year;
                    }
                    return;
                }
                if (!(this.offerings || []).length) return;
                const latest = [...this.offerings].sort((a, b) => (Number(b.year) - Number(a.year)) || (Number(b.id) - Number(a.id)))[0];
                if (!latest) return;
                this.selectedCourseId = latest.course_id;
                this.selectedYear = latest.year;
                this.selectedOfferingId = normalizeNumber(latest.id);
            },
            selectCourse(courseId) {
                if (String(this.selectedCourseId) === String(courseId)) return;
                this.selectedCourseId = courseId;
                const years = uniqueYears(this.offerings || [], courseId);
                this.selectedYear = years.length ? years[years.length - 1] : null;
                this.updateOfferingFromSelection();
            },
            selectYear(year) {
                if (String(this.selectedYear) === String(year)) return;
                this.selectedYear = year;
                this.updateOfferingFromSelection();
            },
            updateOfferingFromSelection() {
                if (!this.selectedCourseId || this.selectedYear === null || this.selectedYear === undefined || this.selectedYear === '') return;
                const offeringId = this.resolveOfferingId(this.selectedCourseId, this.selectedYear);
                if (offeringId === null) return;
                this.selectedOfferingId = offeringId;
            },
        },
    };
})();
