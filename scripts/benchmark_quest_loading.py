"""Offscreen quest loading benchmark; all progression fixtures are temporary.

Use --cache-root with a new directory for a cold reconstructible cache, then
repeat with the same directory for warm results. No game/UI automation runs.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--disable-gpu'
for name in ('dofus_atlas_runtime', 'dofus_atlas_pyside'):
    logging.getLogger(name).addHandler(logging.NullHandler())

import psutil
from PySide6.QtWidgets import QApplication, QWidget
from app.pages.lazy_quests_page import LazyQuestsPage
from app.quest_catalog import QuestCatalog, RAW_QUEST_DATA_DIR
from app.quest_catalog_details import load_lazy_catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-root', type=Path)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    process = psutil.Process()

    def state():
        io, cpu = process.io_counters(), process.cpu_times()
        return dict(rss_mb=process.memory_info().rss / 1048576,
                    cpu_s=cpu.user + cpu.system, read_bytes=io.read_bytes,
                    read_ops=io.read_count, threads=process.num_threads())

    result = {'python': sys.version.split()[0], 'before': state()}
    start = time.perf_counter()
    catalog = (load_lazy_catalog(RAW_QUEST_DATA_DIR, cache_root=args.cache_root)
               if args.cache_root else QuestCatalog.load())
    result.update(catalog_s=time.perf_counter() - start, after_catalog=state(), quests=len(catalog.quests))
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        start = time.perf_counter()
        page = LazyQuestsPage(lambda _: None, catalog=catalog,
            progress_path=root/'quests.json', achievement_progress_path=root/'success.json',
            profile_path=root/'profiles.json', client_index_path=root/'clients.json',
            owned_items_path=root/'owned.json')
        result.update(left_s=time.perf_counter()-start, widgets_left=len(page.findChildren(QWidget)),
                      after_left=state(), cache_after_left=catalog.detail_cache_info())
        result['selections'] = []
        for quest_id in (catalog.quests[0].id, catalog.quests[1].id, catalog.quests[0].id):
            start = time.perf_counter()
            page.select_quest(quest_id, persist=False)
            previous, max_gap = time.perf_counter(), 0
            while page._detail_pending:
                app.processEvents()
                now = time.perf_counter()
                max_gap = max(max_gap, now-previous)
                previous = now
                if now-start > 90:
                    raise TimeoutError('Quest detail benchmark exceeded 90 seconds')
                time.sleep(.005)
            if page.quest_detail_view.current_quest_id != quest_id:
                raise AssertionError('Requested detail was not displayed')
            result['selections'].append(dict(id=quest_id, seconds=time.perf_counter()-start,
                event_loop_max_gap_s=max_gap, widgets=len(page.findChildren(QWidget)), **state()))
        result['cache'] = catalog.detail_cache_info()
        page.close()
        page.deleteLater()
        app.processEvents()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
