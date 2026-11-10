import ipaddress
import os
import re
import socket
from urllib.parse import unquote, urlsplit

import fitz


REFERENCE_HEADING = re.compile(r'^(?:(?:(?:[IVX]+-)?\d+(?:[.．]\d+)*[.．、:]?|[IVX]+[.．])\s*)?[\[【(（]?\s*(?:参考文献|引用文献|参考資料|references|bibliography)\s*[\]】)）]?\s*[:：]?$', re.I)
NEXT_HEADING = re.compile(r'^(?:\d+(?:\.\d+)*[.．、]?\s*)?(?:付録(?:\s*[A-Z0-9])?|謝辞|まとめ|結論|考察|appendix(?:\s+[A-Z0-9])?|acknowledg(?:e)?ments?|conclusions?|discussion)\s*[:：]?$', re.I)
URL_PATTERN = re.compile(r'(?:https?\s*:\s*/?\s*/?|[a-zA-Z][a-zA-Z0-9+.-]{1,20}://|(?:javascript|data|vbscript):|www\.)[^\s<>"\u3000]*', re.I)
EXTRACTOR_VERSION = 'v2'
REFERENCE_ENTRY = re.compile(r'^\s*(?:[\[［【]\s*\d+\s*[\]］】]|\d+[.)．、]\s)')
CITATION_SUFFIX = re.compile(r'^(?:[,，;；]|(?:\(?\d{4}\s*(?:年|[/.-]))|(?:\(?\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b)|(?:\d{1,2}\s*月)|(?:閲覧|参照|アクセス|最終|accessed\b|retrieved\b|visited\b|doi\s*:))', re.I)
SPLIT_SCHEME = re.compile(r'\b(?:h|ht|htt|http|https)\s*$', re.I)


def _url_fragment(text):
    match = re.match(r'[^\s<>"\u3000，、。]+', text)
    if not match:
        return '', 0
    fragment = match.group(0)
    while fragment.endswith((')', ']', '}', '）', '］')):
        closing = fragment[-1]
        opening = {')': '(', ']': '[', '}': '{', '）': '（', '］': '［'}[closing]
        if fragment.count(closing) <= fragment.count(opening):
            break
        fragment = fragment[:-1]
    fragment = fragment.rstrip('.,;；')
    return fragment, match.end()


def _next_url_line(lines, current, origin):
    rect = current['rect']
    tolerance = max(44, origin['font_size'] * 9)
    candidates = [line for line in lines
                  if line['page'] == current['page']
                  and line['rect'].y0 > rect.y0 + rect.height * 0.4
                  and line['rect'].y0 - rect.y1 <= max(rect.height * 2, current['font_size'] * 3)
                  and abs(line['rect'].x0 - origin['rect'].x0) <= tolerance]
    if candidates:
        return min(candidates, key=lambda line: (round(line['rect'].y0, 1), abs(line['rect'].x0 - origin['rect'].x0)))
    if rect.y1 < current['page_height'] * 0.72:
        return None
    candidates = [line for line in lines if line['page'] == current['page'] + 1
                  and current['page_height'] * 0.04 <= line['rect'].y0 < line['page_height'] * 0.3
                  and abs(line['rect'].x0 - origin['rect'].x0) <= tolerance]
    return min(candidates, key=lambda line: (line['rect'].y0, line['rect'].x0)) if candidates else None


def _join_url_lines(lines, origin, match):
    prefix = match.group(0).rstrip()
    scheme = re.match(r'(https?)\s*:\s*/\s*/', prefix, re.I)
    if scheme:
        normalized_prefix = scheme.group(1) + '://' + prefix[scheme.end():]
    else:
        normalized_prefix = prefix
    normalized_prefix = normalized_prefix.replace('\u00ad', '-').replace('\u200b', '')
    value, consumed = _url_fragment(normalized_prefix)
    original = prefix
    locations = [origin]
    corrected = value != prefix
    uncertain = '\u00ad' in prefix
    current = origin
    tail = origin['text'][match.end():].strip()
    if not tail and normalized_prefix.endswith(('.', ',', ';')):
        value = normalized_prefix
        uncertain = True
    if value != normalized_prefix or tail:
        return value, original, locations, corrected, uncertain
    for _ in range(15):
        following = _next_url_line(lines, current, origin)
        if not following or following in locations:
            break
        text = following['text'].strip()
        if REFERENCE_HEADING.fullmatch(text) and following['page'] > current['page']:
            current = following
            continue
        scheme_continuation = value.lower() in ('h', 'ht', 'htt', 'http', 'https', 'http:', 'https:') and (
            (value + text).lower().startswith(('http://', 'https://'))
            or any(scheme.startswith((value + text).lower()) for scheme in ('http://', 'https://'))
        )
        if (REFERENCE_ENTRY.match(text) or REFERENCE_HEADING.fullmatch(text)
                or NEXT_HEADING.fullmatch(text) or CITATION_SUFFIX.match(text)
                or (URL_PATTERN.match(text) and not scheme_continuation)):
            break
        fragment, consumed = _url_fragment(text)
        if not fragment:
            break
        remainder = text[consumed:].strip()
        if remainder and not CITATION_SUFFIX.match(remainder) and not re.match(r'^[)）\]］]', remainder):
            uncertain = bool(re.search(r'[/_.%?&=+#()\-]', fragment) or value.endswith(('/', '-', '?', '&', '=')))
            break
        strong = bool(re.search(r'[/_.%?&=+#()\-]', fragment) or fragment.isdecimal()
                      or value.endswith(('/', '?', '&', '=', '-', '%', '#')))
        if not strong and (not fragment.isascii() or not fragment.isalnum()):
            break
        if len(value) + len(fragment) > 4096:
            uncertain = True
            break
        value += fragment.replace('\u00ad', '-').replace('\u200b', '')
        original += '\n' + text[:consumed]
        corrected = True
        uncertain = uncertain or not strong or '\u00ad' in fragment
        locations.append(following)
        current = following
        if remainder or text[:consumed] != fragment:
            break
    else:
        uncertain = True
    return value, original, locations, corrected, uncertain


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

    def add_url(raw, locations, source, label='', corrected=False, original_text='', uncertain=False, mismatch=False):
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
                'in_references': any(line['in_references'] for line in locations),
                'original_text': original_text or raw, 'uncertain': uncertain, 'link_mismatch': mismatch,
            }
        row = rows[key]
        row['in_references'] = row['in_references'] or any(line['in_references'] for line in locations)
        if source == 'link' and inspect_url(raw)['can_open']:
            row.update(corrected=False, uncertain=False, link_mismatch=False)
        for location in locations:
            occurrence = {'page': location['page'], 'source': source,
                          'display_text': label[:limits['url_length']], 'in_references': location['in_references']}
            if occurrence not in row['occurrences']:
                if occurrence_count >= 2000:
                    partial = 'occurrence_limit'
                    return
                row['occurrences'].append(occurrence)
                occurrence_count += 1

    if isinstance(pdf_bytes, (str, os.PathLike)):
        document = fitz.open(filename=os.fspath(pdf_bytes), filetype='pdf')
    else:
        document = fitz.open(stream=pdf_bytes, filetype='pdf')
    with document:
        if document.needs_pass:
            return {'status': 'failed', 'urls': [], 'extraction_scope': '', 'error_code': 'encrypted_pdf'}
        if document.page_count > limits['pages']:
            partial = 'page_limit'
        lines = []
        native_links = []
        for page_index in range(min(document.page_count, limits['pages'])):
            page = document[page_index]
            blocks = page.get_text('dict', flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES).get('blocks', [])
            page_lines = []
            for block in blocks:
                for line in block.get('lines', []):
                    text = ''.join(span.get('text', '') for span in line.get('spans', [])).strip()
                    if text:
                        rect = fitz.Rect(line['bbox'])
                        if rect.y0 >= page.rect.height * 0.92 and re.fullmatch(r'[-–]?\s*\d+\s*[-–]?', text):
                            continue
                        page_lines.append({'rect': rect, 'text': text, 'page': page_index + 1,
                                           'page_height': page.rect.height,
                                           'font_size': max(span.get('size', 10) for span in line.get('spans', []))})
            page_lines.sort(key=lambda item: (round(item['rect'].y0, 1), item['rect'].x0))
            for line in page_lines:
                text = line['text']
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
                line['in_references'] = in_references
                lines.append(line)
            links = page.get_links()
            if len(links) > limits['url_count']:
                partial = 'url_count_limit'
            for link in links[:limits['url_count']]:
                uri = link.get('uri')
                if not uri:
                    continue
                area = fitz.Rect(link['from'])
                matching = [line for line in page_lines if 'in_references' in line and area.intersects(line['rect'])]
                if not matching:
                    matching = [{'page': page_index + 1, 'rect': area, 'in_references': False, 'text': ''}]
                native_links.append({'url': uri, 'locations': matching, 'label': ' '.join(line['text'] for line in matching),
                                     'area': area, 'page': page_index + 1})
            if links:
                textpage = page.get_textpage(flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)
                for line in page_lines:
                    line['url_rects'] = {}
                    for match in URL_PATTERN.finditer(line['text']):
                        hits = [rect for rect in page.search_for(match.group(0), textpage=textpage) if rect.intersects(line['rect'])]
                        hits.sort(key=lambda rect: rect.x0)
                        occurrence = len(re.findall(re.escape(match.group(0)), line['text'][:match.start()], re.I))
                        if hits:
                            line['url_rects'][match.start()] = hits[min(occurrence, len(hits) - 1)]
            if partial == 'text_limit':
                break
        consumed_prefixes = {}
        for line in lines:
            matches = list(URL_PATTERN.finditer(line['text']))
            matches.extend(SPLIT_SCHEME.finditer(line['text']))
            for match in matches:
                if match.start() < consumed_prefixes.get(id(line), 0):
                    continue
                raw, original, locations, corrected, uncertain = _join_url_lines(lines, line, match)
                if not raw:
                    continue
                if SPLIT_SCHEME.fullmatch(match.group(0)) and not raw.lower().startswith(('http://', 'https://')):
                    continue
                for location in locations[1:]:
                    consumed_prefixes[id(location)] = _url_fragment(location['text'])[1]
                linked = [link for link in native_links if
                          (link['page'] == line['page']
                           and link['area'].intersects(line.get('url_rects', {}).get(match.start(), line['rect'])))
                          or any(link['page'] == location['page'] and link['area'].intersects(location['rect'])
                                 for location in locations[1:])]
                displayed = inspect_url(raw)
                covered = any(
                    inspect_url(link['url'])['key'].startswith(displayed['key'])
                    and (not displayed['can_open'] or inspect_url(link['url'])['host'] == displayed['host'])
                    for link in linked)
                if covered:
                    continue
                add_url(raw, locations, 'text', corrected=corrected, original_text=original,
                        uncertain=uncertain, mismatch=bool(linked))
        for link in native_links:
            add_url(link['url'], link['locations'], 'link', label=link['label'])
    urls = list(rows.values())
    if found_heading:
        urls = [row for row in urls if row['in_references']]
    return {
        'status': 'partial' if partial else ('done' if has_text or urls else 'no_text'),
        'urls': urls,
        'extraction_scope': 'references' if found_heading else 'whole_pdf_candidates',
        'error_code': partial,
    }
