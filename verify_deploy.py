"""Verify the exact approved Mock 1 release using the standard library."""
import collections
import hashlib
import html
import json
import re
import sys
from pathlib import Path

site = Path(sys.argv[1])
manifest = json.loads(Path(sys.argv[2]).read_text())
actual = {p.relative_to(site).as_posix(): p for p in site.rglob('*') if p.is_file()}
assert set(actual) == set(manifest['files']), 'Release file inventory mismatch'
for relative, p in actual.items():
    assert not p.is_symlink() and '..' not in Path(relative).parts
    assert not re.search(r'private|sqlite|__pycache__|node_modules|\.env', relative, re.I)
    expected = manifest['files'][relative]
    assert p.stat().st_size == expected['bytes'], relative + ': size mismatch'
    assert hashlib.sha256(p.read_bytes()).hexdigest() == expected['sha256'], relative + ': checksum mismatch'

reports = []
records = sorted((site / 'reports').glob('*.json'))
assert manifest['release'] == 'mock-20261030-score-rank'
assert len(records) == manifest['students']
for path in records:
    record = json.loads(path.read_text())
    assert record['schemaVersion'] == 3 and record['reportType'] == 'mk-mock-report'
    assert set(record) == {'schemaVersion', 'reportType', 'studentNumber', 'reports'}
    number = record['studentNumber']
    assert re.fullmatch(r'\d{12}', number)
    token = hashlib.sha256(('mk-mock1:' + number).encode()).hexdigest()[:32]
    assert path.stem == token
    levels = set()
    for report in record['reports']:
        assert set(report) == {'level', 'score', 'maximum', 'rank', 'percentile', 'cohortSize', 'htmlPath', 'pdfPath'}
        level = report['level']
        assert level in {'1-2', '3-4', '5-6'} and level not in levels
        levels.add(level)
        assert report['htmlPath'] == token + '-' + level + '.html'
        assert report['pdfPath'] == 'pdfs/' + token + '-' + level + '.pdf'
        assert report['htmlPath'] in actual and report['pdfPath'] in actual
        assert actual[report['pdfPath']].read_bytes().startswith(b'%PDF-')
        reports.append(report)
assert len(reports) == manifest['reports']
counts = collections.Counter(r['level'] for r in reports)
assert counts == manifest['reportsByLevel']
routes = {(p.stem, r['level']) for p in records for r in json.loads(p.read_text())['reports']}
assert {tuple(r) for r in manifest['legacyRoutes']} <= routes, 'Previously published routes disappeared'
assert len(list((site / 'pdfs').glob('*.pdf'))) == manifest['reports']
for report in reports:
    cohort = [r for r in reports if r['level'] == report['level']]
    expected_rank = 1 + len({r['score'] for r in cohort if r['score'] > report['score']})
    expected_pr = 100 * sum(r['score'] < report['score'] for r in cohort) / len(cohort)
    assert report['cohortSize'] == len(cohort) and report['rank'] == expected_rank
    assert abs(report['percentile'] - expected_pr) < 1e-10
    source = actual[report['htmlPath']].read_text()
    overview = re.search(r'<section id="overview".*?</section>', source, re.S).group()
    cells = re.findall(r'<td>(.*?)</td>', overview, re.S)
    cells = [html.unescape(re.sub(r'<[^>]*>', '', c)).strip() for c in cells]
    assert cells[-2:] == [str(expected_rank), f'{expected_pr:.1f}']
    assert f'{len(cohort)} participants' in overview
    assert 'same Level and grade' not in overview
    assert report['pdfPath'] in source
    assert 'OFFLINE BASELINE DEMO' not in source, 'Offline fixture must never be published'
assert 'report-catalog' not in actual['index.html'].read_text(), 'Admin catalog must not replace the parent lookup'
assert 'student-number' in actual['index.html'].read_text()
assert 'report/index.html' in actual
print(json.dumps({'passed': True, 'students': len(records), 'reports': len(reports), 'pdfs': len(reports),
                  'cohorts': dict(counts), 'rankingBasis': 'same Level, all school grades',
                  'files': len(actual)}))
