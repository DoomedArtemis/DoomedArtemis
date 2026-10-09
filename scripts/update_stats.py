#!/usr/bin/env python3
"""Refresh README statistics with public endpoints, keeping old data on failure."""
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'stats.json'
PROJECTS = [
    ('artemis-laboratory-blocks', 737135),
    ('baobab-tree', 1595551),
    ('omni-wheel', 1645840),
    ('artemis-thin-logs', 863021),
    ('climbing-claws', 1601880),
    ('flora-expansion', 1492133),
    ('coupon-codes', 1658411),
]


def fetch_json(url):
    for attempt in range(3):
        try:
            req = Request(url, headers={'User-Agent': 'DoomedArtemis-readme-stats/1.1 (GitHub profile badge updater)', 'Accept': 'application/json'})
            with urlopen(req, timeout=22) as res:
                return json.load(res)
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            logging.warning('%s (attempt %s/3): %s', url, attempt + 1, exc)
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f'Could not fetch {url}')


def nonnegative_int(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f'Invalid {name}: {value!r}')
    return value


def cf_downloads(payload):
    downloads = payload.get('downloads')
    if isinstance(downloads, dict):
        downloads = downloads.get('total')
    return nonnegative_int(downloads, 'CurseForge downloads')


def compact(n):
    if n >= 1_000_000_000:
        return f'{n/1_000_000_000:.1f}'.rstrip('0').rstrip('.') + 'B'
    if n >= 1_000_000:
        return f'{n/1_000_000:.1f}'.rstrip('0').rstrip('.') + 'M'
    if n >= 1_000:
        return f'{n/1_000:.1f}'.rstrip('0').rstrip('.') + 'K'
    return str(n)


def main():
    previous = json.loads(OUTPUT.read_text(encoding='utf8')) if OUTPUT.exists() else {}
    old = {p['modrinth_slug']: p for p in previous.get('projects', [])}
    results = []
    failures = []
    for slug, cf_id in PROJECTS:
        cached = old.get(slug, {})
        entry = {'modrinth_slug': slug, 'curseforge_id': cf_id}
        for provider, url in [
            ('modrinth', f'https://api.modrinth.com/v2/project/{slug}'),
            ('curseforge', f'https://api.cfwidget.com/{cf_id}'),
        ]:
            try:
                response = fetch_json(url)
                if provider == 'modrinth':
                    entry['modrinth_downloads'] = nonnegative_int(response.get('downloads'), f'{slug} downloads')
                    entry['modrinth_followers'] = nonnegative_int(response.get('followers'), f'{slug} followers')
                else:
                    entry['curseforge_downloads'] = cf_downloads(response)
            except (RuntimeError, ValueError, AttributeError) as exc:
                failures.append(f'{slug}/{provider}: {exc}')
                logging.warning('Using previously saved data for %s/%s', slug, provider)
                for key in (['modrinth_downloads', 'modrinth_followers'] if provider == 'modrinth' else ['curseforge_downloads']):
                    if key in cached:
                        entry[key] = cached[key]
        results.append(entry)

    required = ('modrinth_downloads', 'modrinth_followers', 'curseforge_downloads')
    missing = [f'{p["modrinth_slug"]}/{field}' for p in results for field in required if field not in p]
    if missing:
        logging.error('Incomplete data, leaving stats.json unchanged: %s', ', '.join(missing))
        raise SystemExit(1)

    modrinth = sum(p['modrinth_downloads'] for p in results)
    curseforge = sum(p['curseforge_downloads'] for p in results)
    followers = sum(p['modrinth_followers'] for p in results)
    stats = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'total_downloads': modrinth + curseforge,
        'total_downloads_display': compact(modrinth + curseforge),
        'modrinth_followers': followers,
        'modrinth_followers_display': compact(followers),
        'published_mods': len(PROJECTS),
        'curseforge_downloads': curseforge,
        'curseforge_downloads_display': compact(curseforge),
        'modrinth_downloads': modrinth,
        'modrinth_downloads_display': compact(modrinth),
        'projects': results,
    }
    if failures:
        logging.warning('Some values used cached data: %s', '; '.join(failures))
    # Avoid committing an unchanged value set every day.
    comparable = dict(stats)
    comparable.pop('updated_at')
    prior = dict(previous)
    prior.pop('updated_at', None)
    if comparable != prior:
        OUTPUT.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
        logging.info('Updated stats.json; downloads: %s', stats['total_downloads_display'])
    else:
        logging.info('Statistics unchanged, no commit required')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    main()
