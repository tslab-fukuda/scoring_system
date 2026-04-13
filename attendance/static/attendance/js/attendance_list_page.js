function updateTime() {
    const el = document.getElementById('current-time');
    if (!el) return;
    const now = new Date();
    el.textContent = now.toLocaleTimeString('ja-JP', { hour12: false });
}

document.addEventListener('DOMContentLoaded', function () {
    updateTime();
    setInterval(updateTime, 1000);
    const columnToggleStorageKey = 'attendance-column-visibility';

    function applyColumnVisibility(columnName, visible) {
        document.querySelectorAll('[data-column="' + columnName + '"]').forEach(function (cell) {
            cell.classList.toggle('attendance-column-hidden', !visible);
            cell.hidden = !visible;
        });
    }

    function loadColumnVisibility() {
        try {
            const raw = window.localStorage.getItem(columnToggleStorageKey);
            return raw ? JSON.parse(raw) : {};
        } catch (err) {
            return {};
        }
    }

    function saveColumnVisibility(state) {
        try {
            window.localStorage.setItem(columnToggleStorageKey, JSON.stringify(state));
        } catch (err) {
            // ignore storage errors
        }
    }

    function makeSortable(table) {
        if (!table) return;
        const tbody = table.querySelector('tbody');
        table.querySelectorAll('th.sortable').forEach(function(th) {
            const index = Array.from(th.parentNode.children).indexOf(th);
            th.style.cursor = 'pointer';
            th.addEventListener('click', function() {
                const rows = Array.from(tbody.querySelectorAll('tr'));
                const asc = th.dataset.order !== 'asc';
                rows.sort(function(a, b) {
                    const ta = a.children[index].textContent.trim();
                    const tb = b.children[index].textContent.trim();
                    return asc ? ta.localeCompare(tb, 'ja') : tb.localeCompare(ta, 'ja');
                });
                rows.forEach(r => tbody.appendChild(r));
                table.querySelectorAll('th.sortable').forEach(x => x.dataset.order = '');
                th.dataset.order = asc ? 'asc' : 'desc';
            });
        });
    }

    makeSortable(document.getElementById('in-table'));
    makeSortable(document.getElementById('out-table'));

    const savedColumnVisibility = loadColumnVisibility();
    document.querySelectorAll('.attendance-column-toggle').forEach(function (checkbox) {
        const columnName = checkbox.dataset.column || '';
        if (!columnName) return;
        if (Object.prototype.hasOwnProperty.call(savedColumnVisibility, columnName)) {
            checkbox.checked = !!savedColumnVisibility[columnName];
        }
        applyColumnVisibility(columnName, checkbox.checked);
        checkbox.addEventListener('change', function () {
            const visible = checkbox.checked;
            savedColumnVisibility[columnName] = visible;
            applyColumnVisibility(columnName, visible);
            saveColumnVisibility(savedColumnVisibility);
        });
    });

    const overridePanel = document.getElementById('attendance-override-panel');
    const openOverrideBtn = document.getElementById('attendance-override-open-btn');
    const closeOverrideBtn = document.getElementById('attendance-override-close-btn');
    if (overridePanel && openOverrideBtn) {
        openOverrideBtn.addEventListener('click', function () {
            overridePanel.classList.add('is-open');
        });
    }
    if (overridePanel && closeOverrideBtn) {
        closeOverrideBtn.addEventListener('click', function () {
            overridePanel.classList.remove('is-open');
        });
    }

    if (window.CAN_MANAGE_ATTENDANCE_OVERRIDES && window.SELECTED_OFFERING_ID) {
        document.querySelectorAll('.attendance-override-checkbox').forEach(function (checkbox) {
            checkbox.addEventListener('change', function () {
                const userId = checkbox.dataset.userId || '';
                const field = checkbox.dataset.field || '';
                const enabled = checkbox.checked;
                checkbox.disabled = true;
                fetch('/attendance/overrides/update/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': window.CSRF_TOKEN,
                    },
                    body: JSON.stringify({
                        offering_id: window.SELECTED_OFFERING_ID,
                        user_id: userId || null,
                        field,
                        enabled,
                    }),
                })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    if (data.status !== 'ok') {
                        throw new Error(data.message || '更新に失敗しました');
                    }
                    window.location.reload();
                })
                .catch(function (err) {
                    checkbox.checked = !enabled;
                    checkbox.disabled = false;
                    alert(err.message || '更新に失敗しました');
                });
            });
        });
    }
});
