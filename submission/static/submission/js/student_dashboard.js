new Vue({
    el: "#student-dashboard",
    data: {
      tab: 'status',
      statusList: STATUS_LIST,
      scheduleList: SCHEDULE_LIST,
      experimentDay: EXPERIMENT_DAY, // 例: '火' or '木'
    },
    computed: {
      filteredScheduleList() {
        // experimentDayが指定されていればその曜日のみ抽出
        return this.scheduleList.filter(item => item.day_of_week === this.experimentDay);
      }
    },
    methods: {
      isPast(dateStr) {
        const today = new Date();
        const target = new Date(dateStr);
        return target < new Date(today.getFullYear(), today.getMonth(), today.getDate());
      },
      goToSubmit(item) {
        window.location.href = `/submission/submit/?date=${item.date}`;
      }
    }
  });