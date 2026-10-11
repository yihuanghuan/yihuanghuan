import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'update_profile.py'
spec = importlib.util.spec_from_file_location('update_profile', SCRIPT)
pulse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pulse)


def repo(name='arm', stars=2, **kw):
    return dict(name=name, private=False, fork=False, stargazers_count=stars, **kw)


def release(tag='v1', date='2026-10-11T00:00:00Z', **kw):
    return dict(tag_name=tag, published_at=date, draft=False, prerelease=False,
                html_url='https://github.com/yihuanghuan/arm/releases/tag/v1', **kw)


class PulseTests(unittest.TestCase):
    def fetch(self, path):
        if '/users/' in path:
            return [repo()]
        return []

    def test_first_snapshot(self):
        s = pulse.collect(self.fetch, '2026-10-11T01:02:03Z')
        text = pulse.render(s)
        self.assertIn('1 public project', text)
        self.assertIn('2 received stars', text)
        self.assertIn('Tracking starts today', text)
        self.assertIn('No published releases', text)
        self.assertEqual(s['checked_at'], '2026-10-11T01:02:03Z')

    def test_delta_common_repos_only(self):
        old = {'repos': [repo('arm', 2), repo('removed', 9)]}
        new = {'checked_at': '2026-10-11T00:00:00Z',
               'repos': [repo('arm', 5), repo('new', 40)], 'releases': []}
        text = pulse.render(new, old)
        self.assertIn('+3 stars', text)
        self.assertIn('since the previous check', text)
        self.assertIn('1 new project', text)
        self.assertIn('1 project no longer tracked', text)
        self.assertNotIn('+34', text)

    def test_deleted_repo_is_not_unstar(self):
        new = {'checked_at': '2026-10-11T00:00:00Z', 'repos': [], 'releases': []}
        text = pulse.render(new, {'repos': [repo('gone', 10)]})
        self.assertIn('0 stars', text)
        self.assertNotIn('-10 stars', text)

    def test_public_nonfork_and_profile_filter(self):
        def fetch(path):
            if '/users/' in path:
                a = repo('private'); a['private'] = True
                b = repo('fork'); b['fork'] = True
                return [repo(), a, b, repo('yihuanghuan')]
            return []
        self.assertEqual([r['name'] for r in pulse.collect(fetch, 'now')['repos']], ['arm'])

    def test_pagination(self):
        calls = []
        def fetch(path):
            calls.append(path)
            if '/users/' in path:
                return [repo(str(i), 0) for i in range(100)] if '&page=1&' in path else [repo('last')]
            return []
        self.assertEqual(len(pulse.collect(fetch, 'now')['repos']), 101)
        self.assertTrue(any('&page=2&' in c for c in calls))

    def test_releases_drafts_prerelease_sort_limit(self):
        def fetch(path):
            if '/users/' in path: return [repo()]
            draft = release('draft'); draft['draft'] = True
            pre = release('rc', '2026-10-12T00:00:00Z'); pre['prerelease'] = True
            return [draft, pre] + [release('v'+str(i), f'2026-10-0{i}T00:00:00Z') for i in range(1, 6)]
        s = pulse.collect(fetch, 'now')
        self.assertEqual(len(s['releases']), 4)
        self.assertEqual(s['releases'][0]['tag'], 'rc')
        text = pulse.render(s)
        self.assertIn('prerelease', text)
        self.assertNotIn('draft', text)

    def test_markdown_escape(self):
        s = {'checked_at': 'now', 'repos': [repo('x|[<script>\n', 1)], 'releases': []}
        text = pulse.render(s)
        self.assertNotIn('<script>', text)
        self.assertIn('&#124;', text)
        self.assertIn('%7C', text)

    def test_unique_markers(self):
        good = 'before\n<!-- REPO-PULSE:START -->old<!-- REPO-PULSE:END -->\nafter'
        self.assertEqual(pulse.replace_region(good, 'new'),
                         'before\n<!-- REPO-PULSE:START -->\nnew\n<!-- REPO-PULSE:END -->\nafter')
        for bad in ['missing', good + good, '<!-- REPO-PULSE:END --><!-- REPO-PULSE:START -->']:
            with self.assertRaises(ValueError): pulse.replace_region(bad, 'new')

    def test_failure_preserves_all_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'data').mkdir()
            (root/'README.md').write_text('<!-- REPO-PULSE:START -->old<!-- REPO-PULSE:END -->')
            (root/'data/repo-pulse.json').write_text('{"repos": []}')
            (root/'data/star-history.json').write_text('[]')
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            def fail(path):
                if '/users/' in path: return [repo()]
                raise RuntimeError('403 rate limit')
            with self.assertRaises(RuntimeError): pulse.update(root, fail, 'now')
            self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_invalid_markers_preserve_data(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'README.md').write_text('no markers')
            with self.assertRaises(ValueError): pulse.update(root, self.fetch, 'now')
            self.assertFalse((root/'data').exists())

    def test_daily_history_replace_and_repeat_delta(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'README.md').write_text('<!-- REPO-PULSE:START --><!-- REPO-PULSE:END -->')
            pulse.update(root, self.fetch, '2026-10-11T01:00:00Z')
            pulse.update(root, self.fetch, '2026-10-11T02:00:00Z')
            history = json.loads((root/'data/star-history.json').read_text())
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]['checked_at'], '2026-10-11T02:00:00Z')
            self.assertIn('0 stars', (root/'README.md').read_text())

    def test_history_limit(self):
        history = [{'date': f'{i:04}', 'total_stars': i} for i in range(200)]
        result = pulse.daily_history(history, {'checked_at': '2026-10-11T00:00:00Z', 'repos': []})
        self.assertEqual(len(result), 180)
        self.assertEqual(result[-1]['date'], '2026-10-11')

    def test_negative_delta_and_top_four(self):
        repos = [repo(str(i), i) for i in range(7)]
        s = {'checked_at': '2026-10-11T00:00:00Z', 'repos': repos, 'releases': []}
        text = pulse.render(s, {'repos': [repo('6', 8)]})
        self.assertIn('-2 stars', text)
        self.assertEqual(text.count('| ['), 4)
        self.assertNotIn('](https://github.com/yihuanghuan/0)', text)

    def test_featured_projects_come_first_even_without_stars(self):
        s = {'checked_at': '2026-10-11T01:02:03Z', 'releases': [],
             'repos': [repo('drone', 20), repo('another', 8), repo('arm-platform', 0),
                       repo('D435i_Apriltag', 0), repo('LLM-UAVswarm-performance', 1)]}
        text = pulse.render(s)
        self.assertEqual(text.count('| ['), 4)
        self.assertLess(text.index('[arm-platform]'), text.index('[camera experiments]'))
        self.assertLess(text.index('[camera experiments]'), text.index('[LATE-Swarm]'))
        self.assertLess(text.index('[LATE-Swarm]'), text.index('[drone]'))
        self.assertIn('| [arm-platform](https://github.com/yihuanghuan/arm-platform) | 0 |', text)
        self.assertNotIn('[another]', text)
        self.assertIn('<summary>Latest releases</summary>', text)
        self.assertIn('Updated 2026-10-11 01:02 UTC', text)
        self.assertNotIn('### Repo pulse', text)

    def test_http_rate_limit_does_not_become_empty_data(self):
        error = HTTPError('https://api.github.com', 403, 'rate limit', {}, None)
        with patch.object(pulse, 'urlopen', side_effect=error):
            with self.assertRaises(HTTPError):
                pulse.github_fetch('/users/yihuanghuan/repos')

    def test_malformed_api_response_fails(self):
        with self.assertRaises(ValueError):
            pulse.collect(lambda path: {'message': 'rate limit'}, 'now')
        bad = repo(); bad['stargazers_count'] = -1
        with self.assertRaises(ValueError):
            pulse.collect(lambda path: [bad], 'now')

    def test_private_visibility_cannot_leak(self):
        private = repo('secret'); private['private'] = True
        paths = []
        def fetch(path):
            paths.append(path)
            return [private] if '/users/' in path else []
        s = pulse.collect(fetch, 'now')
        self.assertEqual(s['repos'], [])
        self.assertNotIn('secret', pulse.render(s))
        self.assertEqual(len(paths), 1)


if __name__ == '__main__':
    unittest.main()
