import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preview', ROOT / 'scripts/open_preview.py')
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


class PreviewTests(unittest.TestCase):
    def test_self_contained_and_safe(self):
        with tempfile.TemporaryDirectory(prefix='中文 space # & ') as tmp:
            tmp = Path(tmp)
            image = tmp / '图 # &.png'
            image.write_bytes((ROOT / 'examples/手绘视频生产线/scene-01.hd.png').read_bytes())
            anno = tmp / '标注.json'
            anno.write_text(json.dumps({'elements': [], 'subtitle': '</script><script>alert(1)</script>\u2028'}))
            out = preview.generate_preview_html(image, anno, tmp / 'preview.html')
            html = out.read_text()
            self.assertNotIn('./drawing-hand.png', html)
            self.assertNotIn('</script><script>alert', html)
            self.assertIn('\\u003c/script', html)
            self.assertIn('new Option', html)
            self.assertGreater(html.count('data:image/png;base64,'), 1)
            self.assertIn('%23', out.as_uri())

    def test_cli_from_other_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            image = tmp / '图.png'
            image.write_bytes((ROOT / 'examples/手绘视频生产线/scene-01.hd.png').read_bytes())
            anno = ROOT / 'examples/手绘视频生产线/scene-01.hd.annotation.json'
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/open_preview.py'), '--artwork', str(image), '--annotation', str(anno), '--no-open'], cwd=tmp, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((tmp / 'preview-图.html').is_file())

    def test_missing_template(self):
        with patch.object(preview, 'PREVIEW_HTML', Path('/missing/template')), patch.object(sys, 'argv', ['preview', '--artwork', 'x', '--annotation', 'y']):
            self.assertEqual(preview.main(), 1)

    def test_bad_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'x.png').write_bytes(b'x')
            (p / 'x.json').write_text('{')
            with self.assertRaises(ValueError):
                preview.generate_preview_html(p / 'x.png', p / 'x.json', p / 'out.html')

    def test_browser_platform_dispatch(self):
        for platform in ('win32', 'linux'):
            with self.subTest(platform=platform), patch.object(preview.sys, 'platform', platform), patch.object(preview.webbrowser, 'open', return_value=True) as opened, patch.object(preview.subprocess, 'run') as run:
                self.assertTrue(preview.open_url('file:///a%20b.html', 'default'))
                opened.assert_called_once_with('file:///a%20b.html')
                run.assert_not_called()
        with patch.object(preview.sys, 'platform', 'darwin'), patch.object(preview.subprocess, 'run') as run:
            self.assertTrue(preview.open_url('file:///a%20b.html', 'chrome'))
            run.assert_called_once_with(['open', '-a', 'Google Chrome', 'file:///a%20b.html'], check=True)

    def test_main_browser_fallback_and_manual_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            image = tmp / '图.png'
            image.write_bytes((ROOT / 'examples/手绘视频生产线/scene-01.hd.png').read_bytes())
            anno = ROOT / 'examples/手绘视频生产线/scene-01.hd.annotation.json'
            with patch.object(sys, 'argv', ['preview', '--artwork', str(image), '--annotation', str(anno)]), patch.object(preview, 'open_url', return_value=False) as opened, patch('builtins.print') as printed:
                self.assertEqual(preview.main(), 0)
                self.assertEqual([call.args[1] for call in opened.call_args_list], ['chrome', 'default'])
                self.assertTrue(any('待手动打开' in str(call) for call in printed.call_args_list))

    def test_windows_uri_encoding(self):
        from pathlib import PureWindowsPath
        uri = PureWindowsPath('C:/中文 space/a # &.html').as_uri()
        self.assertTrue(uri.startswith('file:///C:/'))
        self.assertIn('%20', uri)
        self.assertIn('%23', uri)
        self.assertNotIn('中文', uri)

    def test_browser_failure(self):
        with patch.object(preview.sys, 'platform', 'win32'), patch.object(preview.webbrowser, 'get', side_effect=preview.webbrowser.Error()):
            self.assertFalse(preview.open_url('file:///x', 'chrome'))


if __name__ == '__main__':
    unittest.main()
