document.addEventListener('DOMContentLoaded', function(){
    const form = document.getElementById('submit-form');
    if (!form) return;
    form.addEventListener('submit', function(e){
        e.preventDefault();
        const formData = new FormData(form);

        fetch("", {
            method: "POST",
            body: formData,
            headers: {
                "X-Requested-With": "XMLHttpRequest"
            }
        })
        .then(res => res.json())
        .then(data => {
            if(data.status === 'success'){
                // モーダル本文をセット
                document.getElementById('submitSuccessBody').innerHTML = `
                  <ul class="list-group list-group-flush mb-3">
                    <li class="list-group-item">ファイル名: <b>${data.filename}</b></li>
                    <li class="list-group-item">提出日時: <b>${data.submitted_at}</b></li>
                    <li class="list-group-item">学生番号: <b>${data.student_id}</b></li>
                  </ul>
                `;
                // Bootstrapモーダルを表示
                var modal = new bootstrap.Modal(document.getElementById('submitSuccessModal'));
                modal.show();
                form.reset();
            }else{
                alert(data.message || 'エラーが発生しました');
            }
        }).catch(() => alert('通信エラーが発生しました'));
    });
});