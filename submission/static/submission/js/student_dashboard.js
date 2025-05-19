new Vue({
    el: "#student-dashboard",
    data: {
        tab: 'status',
        statusList: typeof STATUS_LIST !== "undefined" ? STATUS_LIST : [],
        scheduleList: typeof SCHEDULE_LIST !== "undefined" ? SCHEDULE_LIST : [],
    },
    methods: {
        isPast(dateStr) {
            // "YYYY-MM-DD" 形式前提
            const today = new Date();
            const date = new Date(dateStr);
            today.setHours(0, 0, 0, 0);
            return date < today;
        }
    }
});