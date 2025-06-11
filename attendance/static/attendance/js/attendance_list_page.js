function updateTime() {
    const el = document.getElementById('current-time');
    if (!el) return;
    const now = new Date();
    el.textContent = now.toLocaleTimeString('ja-JP', { hour12: false });
}

document.addEventListener('DOMContentLoaded', function () {
    updateTime();
    setInterval(updateTime, 1000);

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
});
