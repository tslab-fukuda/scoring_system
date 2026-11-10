from collections import Counter
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from submission.reference_urls import run_pdf_reader


class Command(BaseCommand):
    help = 'Read-only reference URL extraction audit of uploaded PDFs. Does not update reports or extraction results.'

    def add_arguments(self, parser):
        parser.add_argument('--submission-id', type=int, action='append', default=[])
        parser.add_argument('--output', required=True)

    def handle(self, *args, **options):
        database = settings.DATABASES['default']
        if database['ENGINE'] != 'django.db.backends.sqlite3':
            raise CommandError('This read-only audit command requires SQLite.')
        database_path = Path(database['NAME']).resolve()
        query = "SELECT id, file FROM submission_submission WHERE report_type = 'main'"
        identifiers = options['submission_id']
        if identifiers:
            query += ' AND id IN (' + ','.join('?' for _ in identifiers) + ')'
        with sqlite3.connect(database_path.as_uri() + '?mode=ro', uri=True) as connection:
            rows = connection.execute(query + ' ORDER BY id', identifiers).fetchall()
        counts = Counter()
        files = []
        media_root = Path(settings.MEDIA_ROOT).resolve()
        for index, (identifier, name) in enumerate(rows, 1):
            path = (media_root / name).resolve()
            if not path.is_relative_to(media_root) or not path.is_file():
                record = {'submission_id': identifier, 'status': 'missing_file'}
            else:
                source = SimpleNamespace(file=SimpleNamespace(path=str(path), size=path.stat().st_size))
                result = run_pdf_reader(source)
                urls = result.get('urls', [])
                record = {
                    'submission_id': identifier, 'status': result['status'],
                    'scope': result.get('extraction_scope', ''), 'error_code': result.get('error_code', ''),
                    'url_count': len(urls),
                    'wrapped': sum('\n' in row.get('original_text', '') for row in urls),
                    'uncertain': sum(bool(row.get('uncertain')) for row in urls),
                }
            files.append(record)
            counts[record['status']] += 1
            for key in ('url_count', 'wrapped', 'uncertain'):
                counts[key] += record.get(key, 0)
            if index % 200 == 0:
                self.stdout.write(f'processed {index}/{len(rows)}')
                self.stdout.flush()
        output = Path(options['output'])
        if output.resolve().is_relative_to(media_root) or output.resolve() == database_path:
            raise CommandError('The audit output must be outside MEDIA_ROOT and must not replace the database.')
        output.write_text(json.dumps({'summary': dict(counts), 'files': files}, ensure_ascii=False, indent=2))
        self.stdout.write(json.dumps({'files': len(rows), **counts}, ensure_ascii=False))
