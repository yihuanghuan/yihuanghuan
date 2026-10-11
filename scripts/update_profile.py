"""Update repository stars and published releases; no third-party dependencies.

Run from anywhere: python scripts/update_profile.py
GITHUB_TOKEN is optional. HTTP errors deliberately propagate without publishing.
"""

from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

USER = 'yihuanghuan'
PROJECT_LABELS = {
    'arm-platform': 'arm-platform',
    'D435i_Apriltag': 'camera experiments',
    'LLM-UAVswarm-performance': 'LATE-Swarm',
    'Distributed-Multi-UAV-Formation-and-Obstacle-Avoidance-System': 'formation & obstacle avoidance',
}
START = '<!-- REPO-PULSE:START -->'
END = '<!-- REPO-PULSE:END -->'


def github_fetch(path):
    headers = {'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28',
               'User-Agent': 'yihuanghuan-profile-pulse'}
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = Request('https://api.github.com' + path, headers=headers)
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def collect(fetch, checked_at):
    repos = []
    page = 1
    while True:
        batch = fetch(f'/users/{USER}/repos?per_page=100&page={page}&sort=full_name')
        if not isinstance(batch, list):
            raise ValueError('GitHub repository response must be a list')
        for r in batch:
            # Missing fields fail the run rather than silently changing the baseline.
            if r['private'] is not False or r['fork'] is not False:
                continue
            if r['name'].casefold() == USER.casefold():
                continue
            stars = r['stargazers_count']
            if isinstance(stars, bool) or not isinstance(stars, int) or stars < 0:
                raise ValueError('Invalid stargazers_count')
            repos.append({'name': r['name'], 'stargazers_count': stars})
        if len(batch) < 100:
            break
        page += 1
    repos.sort(key=lambda r: r['name'].casefold())
    releases = []
    for r in repos:
        path = f'/repos/{USER}/{quote(r["name"], safe="")}/releases?per_page=5'
        batch = fetch(path)
        if not isinstance(batch, list):
            raise ValueError('GitHub release response must be a list')
        for release in batch:
            if release['draft']:
                continue
            published = release['published_at']
            if not published:
                raise ValueError('Published release has no publication timestamp')
            # Validate the timestamp and link before any output files are touched.
            datetime.fromisoformat(published.replace('Z', '+00:00'))
            link = release['html_url']
            if urlparse(link).scheme != 'https' or urlparse(link).netloc != 'github.com':
                raise ValueError('Unexpected release URL')
            releases.append({'repo': r['name'], 'tag': release['tag_name'],
                             'published_at': published, 'url': link,
                             'prerelease': bool(release['prerelease'])})
    releases.sort(key=lambda r: datetime.fromisoformat(r['published_at'].replace('Z', '+00:00')),
                  reverse=True)
    return {'checked_at': checked_at, 'repos': repos, 'releases': releases[:4]}


def escape(text):
    text = html.escape(str(text), quote=False).replace('\n', ' ').replace('\r', ' ')
    for char, entity in [('|', '&#124;'), ('[', '&#91;'), (']', '&#93;'),
                         ('*', '&#42;'), ('_', '&#95;'), ('`', '&#96;'), ('\\', '&#92;')]:
        text = text.replace(char, entity)
    return text


def plural(count, noun):
    return f'{count} {noun}' + ('' if count == 1 else 's')


def render(snapshot, previous=None):
    repos = snapshot['repos']
    total = sum(r['stargazers_count'] for r in repos)
    lines = [f'{plural(len(repos), "public project")} · {plural(total, "received star")}', '']
    if previous is None:
        lines.append('Tracking starts today.')
    else:
        old = {r['name']: r['stargazers_count'] for r in previous['repos']}
        new = {r['name']: r['stargazers_count'] for r in repos}
        delta = sum(new[name] - old[name] for name in new.keys() & old.keys())
        lines.append(f'{delta:+d} stars since the previous check.')
        added, removed = len(new.keys() - old.keys()), len(old.keys() - new.keys())
        if added or removed:
            changes = []
            if added:
                changes.append(f'{plural(added, "new project")} added to the baseline')
            if removed:
                changes.append(f'{plural(removed, "project")} no longer tracked')
            lines += ['', '<details>', '<summary>Tracking changes</summary>', '',
                      '; '.join(changes) + '.', '', '</details>']
    featured = {'arm-platform': 'arm-platform', 'D435i_Apriltag': 'camera experiments',
                'LLM-UAVswarm-performance': 'LATE-Swarm'}
    by_name = {r['name']: r for r in repos}
    ranked = [by_name[name] for name in featured if name in by_name]
    others = sorted((r for r in repos if r['name'] not in featured and r['stargazers_count'] > 0),
                    key=lambda r: (-r['stargazers_count'], r['name'].casefold()))
    ranked += others[:4 - len(ranked)]
    if ranked:
        lines += ['', '| Project | Stars |', '| :-- | --: |']
        for r in ranked:
            url = f'https://github.com/{USER}/{quote(r["name"], safe="")}'
            label = featured.get(r['name'], r['name'])
            label = PROJECT_LABELS.get(r['name'], label)
            lines.append(f'| [{escape(label)}]({url}) | {r["stargazers_count"]} |')
    lines += ['', '<details>', '<summary>Latest releases</summary>', '']
    if not snapshot['releases']:
        lines.append('No published releases.')
    for r in snapshot['releases']:
        label = escape(PROJECT_LABELS.get(r['repo'], r['repo']) + ' / ' + r['tag'])
        # URL encode Markdown delimiters, even when returned by GitHub.
        url = quote(r['url'], safe=':/%?=&.-_~')
        pre = ' · prerelease' if r['prerelease'] else ''
        lines.append(f'- [{label}]({url}) · {escape(r["published_at"][:10])}{pre}')
    updated = snapshot['checked_at'][:16].replace('T', ' ')
    lines += ['', '</details>', '', f'<sub>Updated {escape(updated)} UTC · daily checks</sub>']
    return '\n'.join(lines)


def replace_region(readme, content):
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise ValueError('README needs exactly one REPO-PULSE marker pair')
    start, end = readme.index(START) + len(START), readme.index(END)
    if start > end:
        raise ValueError('REPO-PULSE markers are reversed')
    return readme[:start] + '\n' + content + '\n' + readme[end:]


def daily_history(history, snapshot):
    date = snapshot['checked_at'][:10]
    entries = {entry['date']: entry for entry in history}
    entries[date] = {'date': date, 'checked_at': snapshot['checked_at'],
                     'total_stars': sum(r['stargazers_count'] for r in snapshot['repos']),
                     'repo_count': len(snapshot['repos'])}
    return sorted(entries.values(), key=lambda e: e['date'])[-180:]


def load_json(path, fallback):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else fallback


def update(root, fetch=github_fetch, checked_at=None):
    root = Path(root)
    readme_path = root / 'README.md'
    readme = readme_path.read_text(encoding='utf-8')
    replace_region(readme, '')  # Validate markers before spending API calls.
    snapshot_path = root / 'data' / 'repo-pulse.json'
    history_path = root / 'data' / 'star-history.json'
    previous = load_json(snapshot_path, None)
    history = load_json(history_path, [])
    checked_at = checked_at or datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    snapshot = collect(fetch, checked_at)
    updated_readme = replace_region(readme, render(snapshot, previous))
    updated_history = daily_history(history, snapshot)
    payloads = {snapshot_path: json.dumps(snapshot, indent=2, ensure_ascii=False) + '\n',
                history_path: json.dumps(updated_history, indent=2, ensure_ascii=False) + '\n',
                readme_path: updated_readme}
    # Stage every file only after successful collection/rendering; individual
    # replacements are atomic. API/parse/marker failures leave all files intact.
    staged = []
    try:
        for target, content in payloads.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                             dir=target.parent, delete=False) as stream:
                staged.append((Path(stream.name), target))
                stream.write(content)
        for temporary, target in staged:
            temporary.replace(target)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
    return snapshot


if __name__ == '__main__':
    snapshot = update(Path(__file__).resolve().parents[1])
    print(f'Updated repo pulse: {len(snapshot["repos"])} projects at {snapshot["checked_at"]}')
