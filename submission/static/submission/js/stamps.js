const parseJsonScript = (id, fallback) => {
  const el = document.getElementById(id);
  if (!el) return fallback;
  try {
    return JSON.parse(el.textContent);
  } catch (err) {
    return fallback;
  }
};

new Vue({
  el: '#stamp-app',
  data: {
    stamps: parseJsonScript('stamps-data', []),
    sections: parseJsonScript('stamp-case-sections-data', []),
    csrfToken: parseJsonScript('csrf-token', ''),
    newStamp: '',
    layoutText: '',
    previousNewStamp: '',
    stampFilter: '',
    newSectionLabel: '',
    targetSectionIndex: 0,
    savingStamp: false,
    savingCase: false,
    draggedStamp: null,
    statusMessage: '',
    statusLevel: 'success',
    editingStamp: null,
    editingLayoutText: '',
    savingStampLayout: false,
  },
  computed: {
    filteredStamps() {
      const keyword = (this.stampFilter || '').trim().toLowerCase();
      if (!keyword) return this.stamps;
      return this.stamps.filter(stamp => {
        const text = `${stamp.text || ''}\n${stamp.layout_text || ''}`.toLowerCase();
        return text.includes(keyword);
      });
    },
  },
  created() {
    if (!Array.isArray(this.sections) || this.sections.length === 0) {
      this.sections = [{ label: 'よく使う', stamps: [] }];
    }
  },
  methods: {
    resolvePreviewElement(refName) {
      const ref = this.$refs[refName];
      return Array.isArray(ref) ? ref[0] : ref;
    },
    normalizeLayoutForPreview(text, refName) {
      const source = String(text || '').trim();
      if (!source) return '';
      const preview = this.resolvePreviewElement(refName);
      if (!preview) return source;
      const style = window.getComputedStyle(preview);
      const horizontalPadding =
        (parseFloat(style.paddingLeft) || 0) + (parseFloat(style.paddingRight) || 0);
      const width = Math.max(40, preview.clientWidth - horizontalPadding);
      const probe = document.createElement('canvas').getContext('2d');
      probe.font = `${style.fontWeight || '700'} ${style.fontSize || '16px'} ${style.fontFamily || 'sans-serif'}`;
      return source.split(/\r?\n/).flatMap(paragraph => {
        let line = '';
        const lines = [];
        Array.from(paragraph).forEach(char => {
          const next = line + char;
          if (line && probe.measureText(next).width > width) {
            lines.push(line);
            line = char;
          } else {
            line = next;
          }
        });
        lines.push(line);
        return lines;
      }).join('\n');
    },
    syncLayoutText() {
      if (!this.layoutText || this.layoutText === this.previousNewStamp) {
        this.layoutText = this.newStamp;
      }
      this.previousNewStamp = this.newStamp;
    },
    addStamp() {
      const text = (this.newStamp || '').trim();
      const layoutText = this.normalizeLayoutForPreview(this.layoutText || text, 'newStampPreview');
      if (!text || !layoutText) return;
      this.savingStamp = true;
      this.statusMessage = '';
      fetch('', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'X-CSRFToken': this.csrfToken,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text, layout_text: layoutText }),
      })
        .then(async res => {
          const data = await res.json().catch(() => ({}));
          if (!res.ok) {
            throw new Error(data.message || `登録失敗 (${res.status})`);
          }
          return data;
        })
        .then(data => {
          if (data.status === 'ok' && data.stamp) {
            this.stamps.push(data.stamp);
            this.newStamp = '';
            this.layoutText = '';
            this.previousNewStamp = '';
            this.stampFilter = '';
            this.statusLevel = 'success';
            this.statusMessage = 'スタンプを登録しました。';
            this.$nextTick(() => {
              const list = this.$refs.stampList;
              if (list) list.scrollTop = list.scrollHeight;
            });
          } else {
            throw new Error(data.message || '登録失敗');
          }
        })
        .catch(err => {
          this.statusLevel = 'error';
          this.statusMessage = err.message || '登録失敗';
        })
        .finally(() => {
          this.savingStamp = false;
        });
    },
    ensureTargetSection() {
      if (!this.sections.length) {
        this.sections.push({ label: 'よく使う', stamps: [] });
      }
      if (this.targetSectionIndex < 0 || this.targetSectionIndex >= this.sections.length) {
        this.targetSectionIndex = 0;
      }
      return this.sections[this.targetSectionIndex];
    },
    addStampToCase(stamp) {
      const section = this.ensureTargetSection();
      section.stamps.push({ ...stamp });
    },
    addSection() {
      const label = (this.newSectionLabel || '').trim();
      if (!label) return;
      this.sections.push({ label, stamps: [] });
      this.newSectionLabel = '';
    },
    startEditStamp(stamp) {
      this.editingStamp = stamp;
      this.editingLayoutText = stamp.layout_text || stamp.text || '';
      this.statusMessage = '';
    },
    cancelEditStamp() {
      this.editingStamp = null;
      this.editingLayoutText = '';
    },
    replaceStampEverywhere(updatedStamp) {
      const replace = stamp => (stamp.id === updatedStamp.id ? { ...stamp, ...updatedStamp } : stamp);
      this.stamps = this.stamps.map(replace);
      this.sections.forEach(section => {
        section.stamps = section.stamps.map(replace);
      });
    },
    saveStampLayout() {
      if (!this.editingStamp) return;
      const layoutText = this.normalizeLayoutForPreview(this.editingLayoutText || '', 'editStampPreview');
      if (!layoutText) return;
      this.savingStampLayout = true;
      this.statusMessage = '';
      fetch(`/submission/update_stamp_api/${this.editingStamp.id}/`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'X-CSRFToken': this.csrfToken,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ layout_text: layoutText }),
      })
        .then(async res => {
          const data = await res.json().catch(() => ({}));
          if (!res.ok) {
            throw new Error(data.message || `保存失敗 (${res.status})`);
          }
          return data;
        })
        .then(data => {
          if (data.status === 'ok' && data.stamp) {
            this.replaceStampEverywhere(data.stamp);
            this.cancelEditStamp();
            this.statusLevel = 'success';
            this.statusMessage = 'スタンプレイアウトを更新しました。';
          } else {
            throw new Error(data.message || '保存失敗');
          }
        })
        .catch(err => {
          this.statusLevel = 'error';
          this.statusMessage = err.message || '保存失敗';
        })
        .finally(() => {
          this.savingStampLayout = false;
        });
    },
    removeSection(index) {
      if (this.sections.length <= 1) return;
      this.sections.splice(index, 1);
      if (this.targetSectionIndex >= this.sections.length) {
        this.targetSectionIndex = this.sections.length - 1;
      }
    },
    moveSection(index, delta) {
      const nextIndex = index + delta;
      if (nextIndex < 0 || nextIndex >= this.sections.length) return;
      const [section] = this.sections.splice(index, 1);
      this.sections.splice(nextIndex, 0, section);
      this.targetSectionIndex = nextIndex;
    },
    removeStampFromCase(sectionIndex, stampIndex) {
      this.sections[sectionIndex].stamps.splice(stampIndex, 1);
    },
    moveStamp(sectionIndex, stampIndex, delta) {
      const stamps = this.sections[sectionIndex].stamps;
      const nextIndex = stampIndex + delta;
      if (nextIndex < 0 || nextIndex >= stamps.length) return;
      const [stamp] = stamps.splice(stampIndex, 1);
      stamps.splice(nextIndex, 0, stamp);
    },
    startCaseStampDrag(sectionIndex, stampIndex) {
      this.draggedStamp = {
        sourceSectionIndex: sectionIndex,
        sourceStampIndex: stampIndex,
      };
    },
    clearCaseStampDrag() {
      this.draggedStamp = null;
    },
    dropCaseStamp(targetSectionIndex, targetStampIndex = null) {
      if (!this.draggedStamp) return;
      const sourceSection = this.sections[this.draggedStamp.sourceSectionIndex];
      const targetSection = this.sections[targetSectionIndex];
      if (!sourceSection || !targetSection) {
        this.clearCaseStampDrag();
        return;
      }
      const [stamp] = sourceSection.stamps.splice(this.draggedStamp.sourceStampIndex, 1);
      if (!stamp) {
        this.clearCaseStampDrag();
        return;
      }
      let insertIndex = targetStampIndex;
      if (insertIndex === null || insertIndex === undefined) {
        insertIndex = targetSection.stamps.length;
      }
      if (
        this.draggedStamp.sourceSectionIndex === targetSectionIndex &&
        this.draggedStamp.sourceStampIndex < insertIndex
      ) {
        insertIndex -= 1;
      }
      insertIndex = Math.max(0, Math.min(insertIndex, targetSection.stamps.length));
      targetSection.stamps.splice(insertIndex, 0, stamp);
      this.clearCaseStampDrag();
    },
    saveCase() {
      const sections = this.sections
        .map(section => ({
          label: (section.label || '').trim(),
          stamp_ids: (section.stamps || []).map(stamp => stamp.id),
        }))
        .filter(section => section.label && section.stamp_ids.length > 0);
      this.savingCase = true;
      fetch('/submission/stamp_case_api/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'X-CSRFToken': this.csrfToken,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ sections }),
      })
        .then(res => res.json())
        .then(data => {
          if (data.status === 'ok') {
            this.sections = data.sections && data.sections.length
              ? data.sections
              : [{ label: 'よく使う', stamps: [] }];
            this.targetSectionIndex = 0;
          } else {
            alert(data.message || '保存失敗');
          }
        })
        .catch(() => {
          alert('保存失敗');
        })
        .finally(() => {
          this.savingCase = false;
        });
    },
    deleteStamp(id) {
      if (!confirm('このスタンプを削除しますか？')) return;
      fetch(`/submission/delete_stamp_api/${id}/`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'X-CSRFToken': this.csrfToken,
        },
      })
        .then(res => res.json())
        .then(data => {
          if (data.status === 'success') {
            this.stamps = this.stamps.filter(stamp => stamp.id !== id);
            this.sections.forEach(section => {
              section.stamps = section.stamps.filter(stamp => stamp.id !== id);
            });
          } else {
            alert('削除失敗: ' + (data.message || ''));
          }
        })
        .catch(() => {
          alert('削除失敗');
        });
    },
  },
});
