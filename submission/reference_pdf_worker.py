import json
import resource
import sys


def main():
    options = json.loads(sys.stdin.read())
    resource.setrlimit(resource.RLIMIT_AS, (options['memory_bytes'], options['memory_bytes']))
    resource.setrlimit(resource.RLIMIT_CPU, (options['cpu_seconds'], options['cpu_seconds']))
    import fitz
    from submission.reference_pdf import extract_reference_urls

    fitz.TOOLS.mupdf_display_errors(False)
    fitz.TOOLS.mupdf_display_warnings(False)
    with open(options['path'], 'rb') as source:
        content = source.read(options['max_bytes'] + 1)
    if len(content) > options['max_bytes']:
        result = {'status': 'failed', 'urls': [], 'extraction_scope': '', 'error_code': 'file_size_limit'}
    else:
        result = extract_reference_urls(content, options['limits'])
    sys.stdout.write(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
