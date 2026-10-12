"""Optional facts/posters follow playable-card publication; cache no live URLs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import zlib
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBVideoPickerLibrary as picker


def png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 320, 180, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\x00' + bytes(320 * 3)) * 180)) + chunk(b'IEND', b''))


with tempfile.TemporaryDirectory(prefix='hmb_video_media_cache_') as temporary:
    folder = Path(temporary)
    source = folder / 'source.mp4'
    source.write_bytes(b'fixture-video')
    facts = {'width': 1920, 'height': 1080, 'frame_rate': 29.97, 'duration_seconds': 5.0}
    with patch.dict(os.environ, HMB_VIDEO_MEDIA_CACHE_DIR=str(folder / 'cache')):
        signature = picker._video_thumbnail_signature(source)
        with patch.object(picker, '_probe_local_video_player_metadata', return_value=facts) as probe:
            assert picker._local_video_player_metadata(source) == facts
            picker._VIDEO_METADATA_SOURCE_LOCKS.clear()  # simulate a fresh runtime
            assert picker._local_video_player_metadata(source) == facts
            assert probe.call_count == 1
        cache_file = picker._video_media_cache_path(signature, 'metadata')
        assert cache_file is not None
        assert 'source.mp4' not in cache_file.read_text() and 'http' not in cache_file.read_text()
        cache_file.write_text('{corrupt', encoding='utf-8')
        with patch.object(picker, '_probe_local_video_player_metadata', return_value=facts) as probe:
            assert picker._local_video_player_metadata(source) == facts and probe.call_count == 1
        source.write_bytes(b'changed-video-with-different-size')
        assert picker._video_thumbnail_signature(source) != signature
        with patch.object(picker, '_probe_local_video_player_metadata', return_value=facts) as probe:
            assert picker._local_video_player_metadata(source) == facts and probe.call_count == 1
        # Preserve size and timestamp while replacing pixels/container bytes.
        # Bounded content sampling must invalidate the otherwise identical key.
        old_stat = source.stat(); same_size_signature = picker._video_thumbnail_signature(source)
        source.write_bytes(b'X' * old_stat.st_size)
        os.utime(source, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
        assert picker._video_thumbnail_signature(source) != same_size_signature
        large = folder / 'large.mp4'
        large.write_bytes(b'A' * (picker.VIDEO_MEDIA_SOURCE_SAMPLE_BYTES * 4))
        large_stat = large.stat(); large_signature = picker._video_thumbnail_signature(large)
        with large.open('r+b') as handle:
            handle.seek(-1, 2); handle.write(b'B')
        os.utime(large, ns=(large_stat.st_atime_ns, large_stat.st_mtime_ns))
        assert picker._video_thumbnail_signature(large) != large_signature

        # A file changed while being probed must not publish/cache stale facts.
        def replace_source(_path):
            source.write_bytes(b'replaced-during-probe')
            return facts
        before = picker._video_thumbnail_signature(source)
        picker._video_media_cache_path(before, 'metadata').unlink(missing_ok=True)
        with patch.object(picker, '_probe_local_video_player_metadata', side_effect=replace_source):
            assert picker._local_video_player_metadata(source) == {}
        assert picker._read_video_media_cache(before, 'metadata') is None

        # Two consumers of identical bytes/signature probe once.
        start, release = threading.Event(), threading.Event()
        results = []
        def blocked_probe(_path):
            start.set()
            assert release.wait(3)
            return facts
        with patch.object(picker, '_probe_local_video_player_metadata', side_effect=blocked_probe) as probe:
            workers = [threading.Thread(target=lambda: results.append(picker._local_video_player_metadata(source))) for _ in range(2)]
            for worker in workers: worker.start()
            assert start.wait(2)
            release.set()
            for worker in workers: worker.join(3)
            assert results == [facts, facts] and probe.call_count == 1

        # Decode once, persist bytes, then republish a different runtime URL
        # without FFmpeg. This exercises actual publication, not a fake cache.
        try:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        except ImportError:
            class GriptapeNodes:
                @staticmethod
                def StaticFilesManager():
                    raise AssertionError('Unmocked static publication')
            for module_name in ('griptape_nodes', 'griptape_nodes.retained_mode',
                                'griptape_nodes.retained_mode.griptape_nodes'):
                fake_module = ModuleType(module_name)
                fake_module.__path__ = []
                sys.modules[module_name] = fake_module
            sys.modules['griptape_nodes.retained_mode.griptape_nodes'].GriptapeNodes = GriptapeNodes
        publications = []
        def publish(data, name):
            assert data == png()
            publications.append(name)
            return f'http://runtime-{len(publications)}/poster.png'
        manager = SimpleNamespace(save_static_file=publish)
        picker._VIDEO_THUMBNAIL_URLS.clear()
        picker._VIDEO_THUMBNAIL_ATTEMPTED.clear()
        with patch.object(GriptapeNodes, 'StaticFilesManager', return_value=manager), \
                patch.object(picker, '_video_thumbnail_ffmpeg', return_value=Path('fixture-ffmpeg')), \
                patch.object(picker.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=png())) as decode:
            first, current_signature = picker._video_asset_thumbnail_url(source, 'first-owner')
            assert first and decode.call_count == 1
            picker._VIDEO_THUMBNAIL_URLS.clear()
            picker._VIDEO_THUMBNAIL_ATTEMPTED.clear()
            second, same_signature = picker._video_asset_thumbnail_url(source, 'second-owner')
            assert second != first and same_signature == current_signature and decode.call_count == 1
            picker._video_media_cache_path(current_signature, 'poster').write_bytes(png()[:-8])
            picker._VIDEO_THUMBNAIL_URLS.clear(); picker._VIDEO_THUMBNAIL_ATTEMPTED.clear()
            third, _ = picker._video_asset_thumbnail_url(source, 'third-owner')
            assert third and decode.call_count == 2, 'Truncated persistent PNG was reused'
        assert len(publications) == 3

        # Cache eviction stays bounded and never touches neighboring files.
        unrelated = folder / 'cache' / 'important-source.mp4'
        unrelated.write_bytes(b'preserve')
        with patch.object(picker, 'VIDEO_MEDIA_CACHE_MAX_ENTRIES', 2):
            for index in range(5):
                picker._write_video_media_cache(f'{index:024x}', 'metadata', facts)
        assert len(list((folder / 'cache').glob('*.json'))) <= 2
        assert unrelated.read_bytes() == b'preserve'

        # Real import path reaches card publication before any ffprobe facts.
        node = picker.HMBVideoPickerLibrary(name='Media enrichment regression')
        node._schedule_video_removal_output_sync = lambda: None
        shot = node._picker_state()['active_picker_shot_uuid']
        started, release = threading.Event(), threading.Event()
        def metadata(_path):
            assert not node._hmb_catalog_commit_lock._is_owned()
            assert not node._hmb_state_write_lock._is_owned()
            started.set()
            assert release.wait(3)
            return facts
        def project_copy(_node, path, _slot, **kwargs):
            assert kwargs['defer_metadata'] is True
            return SimpleNamespace(meta={}), str(path)
        with patch.object(picker, '_is_structurally_valid_mp4', return_value=True), \
                patch.object(picker, '_request_parameter_value', return_value=True), \
                patch.object(picker, '_copy_video_to_griptape_project', side_effect=project_copy), \
                patch.object(picker, '_external_media_url', return_value='http://fixture/video.mp4'), \
                patch.object(picker, '_local_video_player_metadata', side_effect=metadata), \
                patch.object(picker, '_video_asset_thumbnail_url', return_value=('', picker._video_thumbnail_signature(source))):
            node._commit_video_import_sources([{'source_path': str(source)}],
                captured_picker_shot_uuid=shot, action_id='metadata-after-card')
            try:
                assert started.wait(2)
                state = node._picker_state()
                assert len(state['videos']) == 1 and state['videos'][0]['video_url']
                assert not state['videos'][0].get('video_metadata')
                assert not state.get('video_imports')
            finally:
                release.set()
                node._hmb_video_import_poster_worker.join(3)
            enriched = node._picker_state()['videos'][0]
            assert enriched['video_metadata'] == facts
            assert enriched['video_metadata_source_signature'] == picker._video_thumbnail_signature(source)
            assert enriched['picker_shot_uuid'] == shot

print('PASS: deferred import metadata; source-signature durable facts/posters; restart URLs; corrupt/stale/bounded caches')
