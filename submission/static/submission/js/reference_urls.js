(function () {
    const statusLabels = {
        pending: '抽出待ち', running: '抽出中', done: '抽出完了',
        partial: '一部のみ抽出（上限に達しました）', no_text: 'コピー可能な文字情報がありません', failed: '抽出に失敗しました'
    };
    const reasonLabels = {
        unsupported_scheme: 'この形式のURLは開けません', invalid_url: 'URL形式を確認してください',
        internal_address: '内部アドレスのため開けません', internal_host: '内部用ホスト名のため開けません',
        unsupported_port: '対応外のポートのため開けません',
        outdated_extraction: '旧方式の抽出結果です。「URLを再抽出」で更新してください。',
        archived_result: '以前の抽出結果です。原文との照合用にコピーできます。',
        link_mismatch: 'PDFの表示文字と埋め込みリンク先が異なります。リンク先の行を確認してください。',
        uncertain_url: 'URLの続きか判定が曖昧な箇所があります。原文を確認してください。'
    };
    Vue.component('reference-url-panel', {
        props: ['dataUrl', 'extractUrl'],
        data() {
            return { result: null, loading: false, error: '', notice: '', tab: 'added', pollTimer: null, polls: 0, disposed: false };
        },
        computed: {
            statusLabel() { return this.result ? statusLabels[this.result.status] || this.result.status : '読み込み中'; },
            errorDetail() {
                if (!this.result) return '';
                return {
                    missing_file: '提出ファイルが見つかりません。', encrypted_pdf: '暗号化されたPDFは解析できません。',
                    invalid_pdf: 'PDFの解析に失敗しました。', timeout: '解析時間の上限に達しました。',
                    file_size_limit: 'PDFの容量が解析上限を超えています。', page_limit: 'ページ数の上限に達しました。',
                    url_count_limit: 'URL件数の上限に達しました。', url_length_limit: '文字数の上限を超えたURLがあります。',
                    text_limit: '抽出文字数の上限に達しました。', occurrence_limit: '掲載箇所の上限に達しました。'
                }[this.result.current.error_code] || '';
            },
            rows() {
                if (!this.result) return [];
                return this.tab === 'added' ? this.result.added : this.result.current.urls;
            },
            comparisonMessage() {
                if (!this.result) return '';
                return {
                    first: '初回提出のURLを表示しています。', ready: '前回提出と比較しています。',
                    pending: '抽出完了後に差分を表示します。失敗した提出があれば、履歴から再試行してください。',
                    missing_offering: '科目・年度が未設定のため、提出間の比較はできません。',
                    version_mismatch: '前回と今回の抽出方式が異なります。「URLを再抽出」で比較元も更新してください。',
                    history_limit: '提出履歴の件数が上限を超えたため、差分比較は行いません。'
                }[this.result.comparison] || '';
            }
        },
        methods: {
            async request(url, options) {
                const response = await fetch(url, Object.assign({ credentials: 'same-origin', cache: 'no-store' }, options || {}));
                if (!response.ok || !(response.headers.get('content-type') || '').includes('application/json')) {
                    throw new Error('参考文献URLを取得できません。ログイン状態と閲覧権限を確認してください。');
                }
                return response.json();
            },
            schedulePoll() {
                window.clearTimeout(this.pollTimer);
                if (!this.disposed && this.result && this.result.busy && this.polls < 60) {
                    this.pollTimer = window.setTimeout(() => { this.polls += 1; this.load(false); }, 2000);
                }
            },
            async load(startIfNeeded) {
                try {
                    this.error = '';
                    const result = await this.request(this.dataUrl);
                    if (this.disposed) return;
                    this.result = result;
                    if (startIfNeeded && result.busy) await this.extract(false);
                    else this.schedulePoll();
                } catch (error) {
                    if (!this.disposed) this.error = error.message;
                }
            },
            async extract(retry, url) {
                if (this.loading) return;
                this.loading = true;
                this.error = '';
                this.polls = 0;
                try {
                    await this.request(url || this.extractUrl, {
                        method: 'POST',
                        headers: { 'X-CSRFToken': window.csrfToken || '', 'Content-Type': 'application/x-www-form-urlencoded' },
                        body: retry ? 'retry=1' : ''
                    });
                    if (!this.disposed) { this.result = await this.request(this.dataUrl); this.schedulePoll(); }
                } catch (error) {
                    if (!this.disposed) this.error = error.message;
                } finally {
                    this.loading = false;
                }
            },
            retryHistory(item) {
                const url = new URL(this.extractUrl, window.location.href);
                url.pathname = url.pathname.replace(/\/\d+\/extract\/$/, '/' + item.submission_id + '/extract/');
                this.extract(true, url.href);
            },
            canOpen(row) {
                if (!row.can_open || row.corrected || !row.open_url) return false;
                try {
                    const url = new URL(row.open_url);
                    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password
                        && !/[\s\x00-\x1f\x7f\\<>"\u200b-\u200f\u202a-\u202e\u2066-\u2069]/.test(row.open_url);
                } catch (error) { return false; }
            },
            async copy(row, event) {
                this.notice = '';
                const text = event.currentTarget.closest('.reference-url-row').querySelector('.reference-url-text');
                try {
                    if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error('clipboard unavailable');
                    await navigator.clipboard.writeText(row.url);
                    if (!this.disposed) this.notice = 'URLをコピーしました。';
                } catch (error) {
                    if (this.disposed) return;
                    const range = document.createRange();
                    range.selectNodeContents(text);
                    const selection = window.getSelection();
                    selection.removeAllRanges();
                    selection.addRange(range);
                    this.notice = 'URLを選択しました。コピー操作を行ってください。';
                }
            },
            scopeLabel(scope) {
                return { references: '参考文献部分から抽出', whole_pdf_candidates: 'PDF全体から抽出した候補' }[scope] || '';
            },
            statusText(status) { return statusLabels[status] || status; },
            reason(row) { return reasonLabels[row.reason] || (row.corrected ? '改行等を復元した候補です。原文を確認してください。' : ''); }
        },
        mounted() { this.load(true); },
        beforeDestroy() { this.disposed = true; window.clearTimeout(this.pollTimer); },
        template: `
          <details class="reference-url-panel mb-2" open>
            <summary>参考文献URL <span class="small" v-text="statusLabel"></span></summary>
            <div class="reference-url-panel-body">
              <p class="small mb-1">リンク先への自動アクセスは行いません。「開く」は外部サイトへ移動します。安全性を保証する表示ではありません。</p>
              <p class="small mb-1" v-text="comparisonMessage"></p>
              <p v-if="errorDetail" class="small" role="status" v-text="errorDetail"></p>
              <p v-if="result && result.busy && polls >= 60" class="small">抽出が続いています。「URLを再抽出」で状態を更新できます。</p>
              <p v-if="error" class="text-danger" role="alert" v-text="error"></p>
              <p v-if="notice" class="small" role="status" v-text="notice"></p>
              <p v-if="result && result.current.outdated && !result.busy" class="small">旧方式の保存結果です。改行されたURLを修正するには再抽出してください。以前の結果は履歴に残ります。</p>
              <button type="button" class="btn btn-sm btn-outline-secondary" :disabled="loading" @click="extract(true)">URLを再抽出</button>
              <p class="small mb-1">添削済みPDFを再抽出する場合は、教員の追記も含む可能性があります。</p>
              <template v-if="result">
                <div class="reference-url-tabs" role="group" aria-label="参考文献URLの表示切替">
                  <button v-for="choice in [{key:'added',label:'追加URL'},{key:'all',label:'現在の全URL'},{key:'history',label:'過去の履歴'}]" :key="choice.key"
                    type="button" class="btn btn-sm btn-outline-primary" :aria-pressed="tab === choice.key" :class="{active:tab === choice.key}" @click="tab = choice.key" v-text="choice.label"></button>
                </div>
                <p class="small mb-1" v-text="scopeLabel(result.current.scope)"></p>
                <p v-if="result.current.source_kind === 'legacy_graded'" class="small">添削済みPDFから後日抽出した結果です。教員の追記を含む可能性があります。</p>
                <div class="reference-url-list">
                  <template v-if="tab !== 'history'">
                    <p v-if="!rows.length" class="small" v-text="tab === 'added' && ['ready','first'].includes(result.comparison) ? '追加URLはありません。' : (tab === 'all' && result.status === 'done' ? '抽出されたURLはありません。' : '表示できる結果がありません。')"></p>
                    <reference-url-row v-for="row in rows" :key="row.key" :row="row" :can-open="canOpen(row)" :reason="reason(row)" @copy="copy"></reference-url-row>
                  </template>
                  <template v-else>
                    <section v-for="item in result.history" :key="item.submission_id" class="reference-url-history">
                      <h5 class="h6">{{ item.ordinal }}回目 <span v-text="statusText(item.status)"></span></h5>
                      <p v-if="item.source_kind === 'legacy_graded'" class="small">添削済みPDFから後日抽出</p>
                      <button type="button" class="btn btn-sm btn-outline-secondary" :disabled="loading" @click="retryHistory(item)">この提出のURLを再抽出</button>
                      <reference-url-row v-for="row in item.urls" :key="row.key" :row="row" :can-open="canOpen(row)" :reason="reason(row)" @copy="copy"></reference-url-row>
                      <details v-if="item.revisions && item.revisions.length" class="mt-2">
                        <summary>以前の抽出結果</summary>
                        <section v-for="(revision,index) in item.revisions" :key="index">
                          <div class="small">抽出方式: {{ revision.extractor_version || '旧方式' }} / {{ revision.extracted_at || '-' }}</div>
                          <reference-url-row v-for="row in revision.urls" :key="row.key" :row="row" :can-open="false" :reason="reason(row)" @copy="copy"></reference-url-row>
                        </section>
                      </details>
                    </section>
                    <section v-if="result.removed.length"><h5 class="h6">今回削除されたURL</h5>
                      <reference-url-row v-for="row in result.removed" :key="row.key" :row="row" :can-open="canOpen(row)" :reason="reason(row)" @copy="copy"></reference-url-row>
                    </section>
                  </template>
                </div>
              </template>
            </div>
          </details>`
    });
    Vue.component('reference-url-row', {
        props: ['row', 'canOpen', 'reason'],
        template: `<div class="reference-url-row">
          <span class="reference-url-text" v-text="row.url"></span>
          <span class="small" v-if="row.change" v-text="{first:'初回',added:'追加',retained:'継続',unknown:'差分未確定'}[row.change]"></span>
          <div class="small">掲載ページ: {{ row.pages.join(', ') }} / 初出: {{ row.first_seen }}回目 <span v-if="row.host"> / 接続先: <span v-text="row.host"></span></span></div>
          <div v-if="row.corrected" class="small">PDFの原文: <span class="reference-url-original" v-text="row.original_text"></span></div>
          <div v-for="(item,index) in row.occurrences.filter(item => item.source === 'link' && item.display_text && item.display_text !== row.url)" :key="index" class="small">PDFの表示文字: <span v-text="item.display_text"></span></div>
          <button type="button" class="btn btn-sm btn-outline-secondary" @click="$emit('copy', row, $event)">コピー</button>
          <a v-if="canOpen" class="btn btn-sm btn-outline-primary" :href="row.open_url" target="_blank" rel="noopener noreferrer">別タブで開く</a>
          <span v-else class="small" v-text="reason"></span>
        </div>`
    });
})();
