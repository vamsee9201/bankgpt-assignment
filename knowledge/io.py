"""Read local participant datasets without persisting or networking website data."""
from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


@dataclass(frozen=True)
class Page:
    url: str
    title: str
    markdown: str
    fetched_at: str


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    taken_on: str
    pages: list[Page]


def _relative(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name:
        raise ValueError(f'Unsafe dataset path: {name!r}')
    return str(path)


def _from_zip(zf):
    manifests = sorted(n for n in zf.namelist() if n.endswith('/manifest.json') or n == 'manifest.json')
    for name in manifests:
        manifest = json.loads(zf.read(_relative(name)))
        parent = str(PurePosixPath(name).parent)
        def read(relative):
            return zf.read(str(PurePosixPath(parent) / _relative(relative))).decode('utf-8')
        yield _snapshot(manifest, read)


def _snapshot(m, read):
    return Snapshot(m['snapshot_id'], m['taken_on'],
                    [Page(p['url'], p.get('title', ''), read(p['file']),
                          p.get('fetched_at', m['taken_on'])) for p in m['pages']])


def load_snapshots(path):
    """Accept a participant ZIP, individual snapshot ZIP, kit folder or snapshots folder."""
    root = Path(path)
    snapshots = []
    if root.is_file():
        with ZipFile(root) as outer:
            nested = [n for n in outer.namelist() if '/snapshots_zip/' in n and n.endswith('.zip')]
            if nested:
                for name in sorted(nested):
                    with ZipFile(BytesIO(outer.read(name))) as inner:
                        snapshots.extend(_from_zip(inner))
            else:
                snapshots.extend(_from_zip(outer))
    else:
        data = root / 'snapshots' if (root / 'snapshots').exists() else root
        manifests = sorted(data.glob('*/manifest.json'))
        if (data / 'manifest.json').exists():
            manifests.append(data / 'manifest.json')
        if manifests:
            for path in manifests:
                m = json.loads(path.read_text())
                def read(name):
                    target = (path.parent / _relative(name)).resolve()
                    if not target.is_relative_to(path.parent.resolve()):
                        raise ValueError('Dataset file resolves outside its snapshot')
                    return target.read_text(encoding='utf-8')
                snapshots.append(_snapshot(m, read))
        else:
            zips = root / 'snapshots_zip' if (root / 'snapshots_zip').exists() else root
            for z in sorted(zips.glob('*.zip')):
                snapshots.extend(load_snapshots(z))
    if not snapshots:
        raise ValueError(f'No snapshots found in {root}')
    return sorted(snapshots, key=lambda s: (s.taken_on, s.snapshot_id))
