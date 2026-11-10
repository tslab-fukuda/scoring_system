import argparse
import json
from pathlib import Path
import unittest
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]


class ReferenceURLBrowserTests(unittest.TestCase):
    def exercise(self, engine, vue_source, executable_path=None):
        with sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch(headless=True, executable_path=executable_path)
            self.addCleanup(browser.close)
            page = browser.new_page(viewport={'width': 1024, 'height': 768})
            errors = []
            requests = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            rows = [
                dict(url='https://example.com/ref', key='safe', pages=[2], first_seen=1, host='example.com',
                     occurrences=[], can_open=True, open_url='https://example.com/ref', corrected=False, reason='syntax_only'),
                dict(url='<img src=x onerror="window.injected=true">', key='html', pages=[2], first_seen=1, host='',
                     occurrences=[], can_open=False, open_url='', corrected=True, reason='invalid_url', original_text='<img src=x>\n/continuation'),
                dict(url='javascript:alert(1)', key='script', pages=[2], first_seen=1, host='',
                     occurrences=[], can_open=True, open_url='javascript:alert(1)', corrected=False, reason='unsupported_scheme'),
            ]
            state = {'started': False}

            def payload():
                status = 'done' if state['started'] else 'pending'
                current = dict(submission_id=1, ordinal=1, status=status, scope='references', source_kind='submitted', error_code='', urls=rows if state['started'] else [])
                current['extractor_version'] = 'v2'
                current['revisions'] = [dict(extractor_version='v1', extracted_at='2026-11-10T00:00:00Z',
                                             urls=[dict(rows[0], can_open=False, open_url='', reason='archived_result')])]
                return dict(status=status, comparison='first' if state['started'] else 'pending', current=current,
                            added=current['urls'], removed=[], history=[current], busy=not state['started'])

            def route_request(route):
                request = route.request
                path = urlsplit(request.url).path
                requests.append((request.method, path))
                if path == '/':
                    route.fulfill(content_type='text/html; charset=utf-8', body='''<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/grading.css"></head><body>
                        <div id="app"><button id="controls" @click="shown = !shown">操作欄切替</button>
                        <reference-url-panel v-if="shown" data-url="/data" extract-url="/extract"></reference-url-panel>
                        <textarea id="annotation">添削内容</textarea></div>
                        <script>window.csrfToken="test-token";</script>
                        <script src="/vue.js"></script><script src="/reference.js"></script>
                        <script>window.app = new Vue({el:'#app',data:{shown:true}});</script></body></html>''')
                elif path == '/vue.js':
                    route.fulfill(content_type='application/javascript; charset=utf-8', body=vue_source)
                elif path == '/reference.js':
                    route.fulfill(content_type='application/javascript; charset=utf-8', body=(ROOT / 'submission/static/submission/js/reference_urls.js').read_text())
                elif path == '/grading.css':
                    route.fulfill(content_type='text/css', body=(ROOT / 'submission/static/submission/css/grading_form.css').read_text())
                elif path == '/data':
                    route.fulfill(content_type='application/json', body=json.dumps(payload()))
                elif path == '/extract':
                    self.assertEqual(request.method, 'POST')
                    self.assertEqual(request.headers.get('x-csrftoken'), 'test-token')
                    state['started'] = True
                    route.fulfill(status=202, content_type='application/json', body=json.dumps(payload()))
                else:
                    errors.append('Unexpected request: ' + request.url)
                    route.abort()

            page.route('**/*', route_request)
            page.goto('https://grading.test/')
            page.wait_for_selector('.reference-url-row')
            self.assertEqual(page.locator('.reference-url-row').count(), 3)
            self.assertEqual(page.locator('.reference-url-row a').count(), 1)
            link = page.locator('.reference-url-row a')
            self.assertEqual(link.get_attribute('rel'), 'noopener noreferrer')
            self.assertEqual(link.get_attribute('target'), '_blank')
            self.assertEqual(page.locator('.reference-url-list img').count(), 0)
            self.assertEqual(page.locator('.reference-url-original').first.evaluate('element => getComputedStyle(element).whiteSpace'), 'pre-wrap')
            self.assertIsNone(page.evaluate('window.injected'))
            page.evaluate('''Object.defineProperty(navigator, 'clipboard', {configurable:true, value:{writeText: async value => {window.copied = value;}}})''')
            page.locator('.reference-url-row button').first.click()
            page.wait_for_function("window.copied === 'https://example.com/ref'")
            self.assertIn('コピーしました', page.locator('[role=status]').first.inner_text())
            page.evaluate("Object.defineProperty(navigator, 'clipboard', {configurable:true, value:{writeText: async () => {throw new Error('permission denied');}}})")
            page.locator('.reference-url-row button').first.click()
            page.wait_for_function("window.getSelection().toString() === 'https://example.com/ref'")
            page.evaluate("Object.defineProperty(navigator, 'clipboard', {configurable:true, value:undefined})")
            page.locator('.reference-url-row button').first.click()
            page.wait_for_function("window.getSelection().toString() === 'https://example.com/ref'")
            page.get_by_role('button', name='現在の全URL', exact=True).click()
            self.assertEqual(page.locator('.reference-url-row').count(), 3)
            page.get_by_role('button', name='過去の履歴', exact=True).click()
            self.assertIn('1回目', page.locator('.reference-url-history').inner_text())
            page.locator('.reference-url-history details > summary').click()
            self.assertEqual(page.locator('.reference-url-history details a').count(), 0)
            self.assertEqual(page.locator('.reference-url-history details .reference-url-text').inner_text(), 'https://example.com/ref')
            page.locator('.reference-url-panel > summary').click()
            self.assertFalse(page.locator('.reference-url-panel').evaluate('element => element.open'))
            page.locator('#controls').click()
            page.locator('#controls').click()
            page.wait_for_selector('.reference-url-row')
            self.assertEqual(sum(method == 'POST' for method, path in requests), 1)
            page.get_by_role('button', name='URLを再抽出', exact=True).click()
            page.wait_for_function("!window.app.$children[0].loading")
            self.assertEqual(sum(method == 'POST' for method, path in requests), 2)
            self.assertEqual(page.locator('#annotation').input_value(), '添削内容')
            self.assertEqual(errors, [])
            self.assertTrue(all(path in ('/', '/vue.js', '/reference.js', '/grading.css', '/data', '/extract') for method, path in requests))
            page.set_viewport_size({'width': 390, 'height': 844})
            page.get_by_role('button', name='現在の全URL', exact=True).click()
            self.assertEqual(page.locator('.reference-url-row').count(), 3)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--vue-file', required=True)
    parser.add_argument('--engine', choices=['chromium', 'webkit'], default='chromium')
    parser.add_argument('--executable-path')
    options = parser.parse_args()
    test = ReferenceURLBrowserTests()
    test.exercise(options.engine, Path(options.vue_file).read_text(), options.executable_path)
    test.doCleanups()
    print(f'{options.engine}: reference URL browser tests passed')
