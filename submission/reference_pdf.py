import ipaddress
import re
import socket
from urllib.parse import unquote, urlsplit

import fitz


REFERENCE_HEADING = re.compile(r'^(?:(?:\d+(?:\.\d+)*[.．、:]?|[IVX]+[.．])\s*)?(?:参考文献|引用文献|参考資料|references|bibliography)\s*[:：]?$', re.I)
NEXT_HEADING = re.compile(r'^(?:\d+(?:\.\d+)*[.．、]?\s*)?(?:付録(?:\s*[A-Z0-9])?|謝辞|まとめ|結論|考察|appendix(?:\s+[A-Z0-9])?|acknowledg(?:e)?ments?|conclusions?|discussion)\s*[:：]?$', re.I)
URL_PATTERN = re.compile(r'(?:[a-zA-Z][a-zA-Z0-9+.-]{1,20}://|(?:javascript|data|vbscript):|www\.)[^\s<>"\u3000]+', re.I)
EXTRACTOR_VERSION = 'v1'


def inspect_url(value):
    result = {'can_open': False, 'open_url': '', 'host': '', 'reason': 'invalid_url', 'key': value}
    if not value or re.search(r'[\s\x00-\x1f\x7f-\x9f\\<>"\u200b-\u200f\u202a-\u202e\u2066-\u2069]', value):
        return result
    if re.search(r'[\x00-\x20\x7f\\]', unquote(value)):
        return result
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
        if parsed.scheme.lower() not in ('http', 'https'):
            result['reason'] = 'unsupported_scheme'
            return result
        if not host or parsed.username is not None or parsed.password is not None:
            return result
        ascii_host = host.encode('idna').decode('ascii').lower().rstrip('.')
        if not ascii_host or '%' in ascii_host:
            return result
        result['host'] = ascii_host
        normalized_host = f'[{ascii_host}]' if ':' in ascii_host else ascii_host
        netloc = normalized_host + (f':{port}' if port is not None else '')
        normalized = parsed.scheme.lower() + '://' + netloc + parsed.path
        if '?' in value.split('#', 1)[0]:
            normalized += '?' + parsed.query
        if '#' in value:
            normalized += '#' + parsed.fragment
        result['key'] = normalized
        address = None
        try:
            address = ipaddress.ip_address(ascii_host)
        except ValueError:
            try:
                address = ipaddress.ip_address(socket.inet_aton(ascii_host))
            except (OSError, ValueError):
                pass
        if address is not None:
            if not address.is_global or (getattr(address, 'ipv4_mapped', None) and not address.ipv4_mapped.is_global):
                result['reason'] = 'internal_address'
                return result
        else:
            if ('.' not in ascii_host or ascii_host.endswith(('.localhost', '.local', '.internal', '.lan', '.home', '.test', '.invalid'))
                    or ascii_host == 'localhost'):
                result['reason'] = 'internal_host'
                return result
            if any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in ascii_host.split('.')):
                return result
            if ascii_host.split('.')[-1].isdigit() or ascii_host.split('.')[-1].startswith('0x'):
                return result
        if port not in (None, 80, 443):
            result['reason'] = 'unsupported_port'
            return result
        result.update(can_open=True, open_url=normalized, reason='syntax_only')
        return result
    except (ValueError, UnicodeError, OverflowError):
        return result


def extract_reference_urls(pdf_bytes, limits):
    rows = {}
    found_heading = False
    in_references = False
    has_text = False
    partial = ''
    text_size = 0
    occurrence_count = 0

    def add_url(raw, page_number, source, in_section, label='', corrected=False, original_text=''):
        nonlocal partial, occurrence_count
        if len(raw) > limits['url_length']:
            partial = 'url_length_limit'
            return
        validation = inspect_url(raw)
        key = validation['key']
        if key not in rows:
            if len(rows) >= limits['url_count']:
                partial = 'url_count_limit'
                return
            rows[key] = {
                'url': raw, 'key': key, 'occurrences': [], 'corrected': corrected,
                'in_references': in_section, 'original_text': original_text or raw,
            }
        row = rows[key]
        row['in_references'] = row['in_references'] or in_section
        occurrence = {'page': page_number, 'source': source, 'display_text': label[:limits['url_length']], 'in_references': in_section}
        if occurrence not in row['occurrences']:
            if occurrence_count >= 2000:
                partial = 'occurrence_limit'
                return
            row['occurrences'].append(occurrence)
            occurrence_count += 1

    with fitz.open(stream=pdf_bytes, filetype='pdf') as document:
        if document.needs_pass:
            return {'status': 'failed', 'urls': [], 'extraction_scope': '', 'error_code': 'encrypted_pdf'}
        if document.page_count > limits['pages']:
            partial = 'page_limit'
        for page_index in range(min(document.page_count, limits['pages'])):
            page = document[page_index]
            blocks = page.get_text('dict', flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES).get('blocks', [])
            lines = []
            for block in blocks:
                for line in block.get('lines', []):
                    text = ''.join(span.get('text', '') for span in line.get('spans', [])).strip()
                    if text:
                        lines.append((fitz.Rect(line['bbox']), text))
            lines.sort(key=lambda item: (item[0].y0, item[0].x0))
            section_lines = []
            for line_index, (rect, text) in enumerate(lines):
                has_text = True
                text_size += len(text)
                if text_size > limits['text_length']:
                    partial = 'text_limit'
                    break
                if REFERENCE_HEADING.fullmatch(text):
                    found_heading = True
                    in_references = True
                elif in_references and NEXT_HEADING.match(text) and not URL_PATTERN.search(text):
                    in_references = False
                section_lines.append((rect, text, in_references))
                for match in URL_PATTERN.finditer(text):
                    raw = match.group(0)
                    original_text = raw
                    corrected = False
                    if match.end() == len(text) and raw.endswith(('/', '?', '&', '=', '-', '%')) and line_index + 1 < len(lines):
                        next_rect, continuation = lines[line_index + 1]
                        if (0 <= next_rect.y0 - rect.y1 <= rect.height * 2
                                and abs(next_rect.x0 - rect.x0) < 40
                                and re.fullmatch(r'[A-Za-z0-9_~/%?&=+#.%-]+', continuation)
                                and not REFERENCE_HEADING.fullmatch(continuation)
                                and not NEXT_HEADING.match(continuation)
                                and not continuation.isdigit()):
                            raw += continuation
                            original_text += '\n' + continuation
                            corrected = True
                    add_url(raw, page_index + 1, 'text', in_references, corrected=corrected, original_text=original_text)
            links = page.get_links()
            if len(links) > limits['url_count']:
                partial = 'url_count_limit'
            for link in links[:limits['url_count']]:
                uri = link.get('uri')
                if not uri:
                    continue
                area = fitz.Rect(link['from'])
                matching = [item for item in section_lines if area.intersects(item[0])]
                label = ' '.join(item[1] for item in matching)
                add_url(uri, page_index + 1, 'link', any(item[2] for item in matching), label)
            if partial == 'text_limit':
                break
    urls = list(rows.values())
    if found_heading:
        urls = [row for row in urls if row['in_references']]
    return {
        'status': 'partial' if partial else ('done' if has_text or urls else 'no_text'),
        'urls': urls,
        'extraction_scope': 'references' if found_heading else 'whole_pdf_candidates',
        'error_code': partial,
    }
