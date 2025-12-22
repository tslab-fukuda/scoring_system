new Vue({
    el: "#scoring-items-app",
    data: {
      pre: (window.initialPre || []).map(item => ({
        label: item.label || '',
        weight: item.weight ?? 1,
        code: item.code || '',
        is_system: !!item.is_system,
        show_in_grading_form: item.show_in_grading_form !== false,
      })),
      main: (window.initialMain || []).map(item => ({
        label: item.label || '',
        weight: item.weight ?? 1,
        code: item.code || '',
        is_system: !!item.is_system,
        show_in_grading_form: item.show_in_grading_form !== false,
      })),
      courses: window.courses || [],
      selectedCourseId: window.selectedCourseId || '',
      selectedScope: window.selectedScope || 'common'
    },
    computed: {
      currentCourse() {
        return this.courses.find(c => String(c.id) === String(this.selectedCourseId));
      },
      currentOfferings() {
        if (!this.currentCourse || !Array.isArray(this.currentCourse.offerings)) return [];
        return this.currentCourse.offerings.slice().sort((a, b) => b.year - a.year);
      }
    },
    methods: {
      changeCourse() {
        if (!this.selectedCourseId) return;
        this.selectedScope = 'common';
        this.applySelection();
      },
      changeScope() {
        this.applySelection();
      },
      applySelection() {
        const params = new URLSearchParams(window.location.search);
        if (this.selectedCourseId) params.set('course_id', this.selectedCourseId);
        if (this.selectedScope) params.set('offering_id', this.selectedScope);
        window.location.search = params.toString();
      },
      save() {
        console.log("保存ボタン押下");
        console.log("pre:", this.pre);
        console.log("main:", this.main);
        fetch("", {
          method: "POST",
          headers: {
            "X-CSRFToken": window.csrfToken,
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            course_id: this.selectedCourseId,
            offering_id: this.selectedScope,
            pre: this.pre.filter(x => x.label.trim().length).map(x => ({
              label: x.label,
              weight: x.weight,
              code: x.code,
              is_system: !!x.is_system,
              show_in_grading_form: !!x.show_in_grading_form,
            })),
            main: this.main.filter(x => x.label.trim().length).map(x => ({
              label: x.label,
              weight: x.weight,
              code: x.code,
              is_system: !!x.is_system,
              show_in_grading_form: !!x.show_in_grading_form,
            }))
          })
        })
        .then(res => res.json().then(data => ({ ok: res.ok, data })))
        .then(({ ok, data }) => {
          if (ok) {
            location.reload();
            return;
          }
          alert((data && data.message) ? data.message : "登録失敗");
        })
        .catch(err => {
          console.error("fetch失敗:", err);
        });
      }
    },
    mounted() {
      if (!this.selectedCourseId && this.courses.length) {
        this.selectedCourseId = String(this.courses[0].id);
      }
      const validScope = this.selectedScope === 'common'
        || this.currentOfferings.some(o => String(o.id) === String(this.selectedScope));
      if (!validScope) {
        this.selectedScope = 'common';
      }
    }
  });
  
