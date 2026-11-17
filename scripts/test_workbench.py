"""Isolated archive and HTTP regression checks; never touches learner history."""

import copy
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

import workbench as wb


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        """为每项测试创建独立临时目录和模拟日语课程，隔离真实学习资料。"""
        scratch = Path(__file__).resolve().parents[2]
        self.temp = tempfile.TemporaryDirectory(prefix="jpkouyu-check-", dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data_dir = self.root / "data"
        self.session = {
            "id": "test-ja-001", "language": "ja",
            "created_at": "2026-09-15T12:00:00+08:00",
            "topic": {"id": "store", "label": "便利店结账"},
            "duration_minutes": 10, "level": "beginner", "hint_mode": "guided",
            "targets": [{"expression": "袋は要りません。", "reading": "ふくろはいりません。",
                         "meaning_zh": "不需要袋子", "status": "mastered",
                         "support": "independent", "evidence": "袋は要りません。"}],
            "repairs": [{"kind": "repair", "learner": "袋がください。",
                         "natural": "袋をください。", "natural_reading": "ふくろをください。",
                         "reason_zh": "请求物品用を"}],
            "focus_next": ["请求物品时的助词"], "next_drill": "改在咖啡店请求两杯咖啡",
            "pronunciation": {"status": "not_observed", "notes": []},
        }
        self.input_path = self.root / "input.json"

    def archive(self, payload=None):
        """将当前模拟课程写入测试输入，再调用真实旧版归档流程。"""
        wb.atomic_json(self.input_path, payload or self.session)
        wb.archive_session(self.data_dir, self.input_path)

    def test_unicode_archive_roundtrip_and_repeat(self):
        """验证中文与假名正确往返保存，重复导入不增加课程。"""
        self.archive()
        self.archive()
        state = wb.load_state(self.data_dir)
        self.assertEqual(state["sessions"], [self.session])
        session_file = self.data_dir / "sessions/test-ja-001.json"
        self.assertEqual(json.loads(session_file.read_text(encoding="utf-8")), self.session)
        markdown = (self.data_dir / "复习台.md").read_text(encoding="utf-8")
        self.assertIn("ふくろはいりません。", markdown)
        self.assertIn("ふくろをください。", markdown)

    def test_conflicting_id_does_not_overwrite(self):
        """验证同 ID 不同课程被拒绝，原汇总文件字节保持不变。"""
        self.archive()
        original = (self.data_dir / "workbench-data.json").read_bytes()
        changed = copy.deepcopy(self.session)
        changed["duration_minutes"] = 20
        with self.assertRaises(ValueError):
            self.archive(changed)
        self.assertEqual((self.data_dir / "workbench-data.json").read_bytes(), original)

    def test_other_language_is_rejected(self):
        """验证英语或缺少日语标记的记录不会写入日语数据目录。"""
        payload = copy.deepcopy(self.session)
        payload["language"] = "en"
        with self.assertRaises(ValueError):
            self.archive(payload)
        self.assertFalse(self.data_dir.exists())
        wb.atomic_json(self.data_dir / "workbench-data.json", {"version": 1, "sessions": []})
        with self.assertRaises(ValueError):
            wb.load_state(self.data_dir)

    def test_imitation_and_text_pronunciation_are_not_mastery(self):
        """验证模仿不能算掌握，纯文字不能生成发音结论。"""
        payload = copy.deepcopy(self.session)
        payload["targets"][0]["support"] = "model"
        with self.assertRaises(ValueError):
            wb.validate_session(payload)
        payload = copy.deepcopy(self.session)
        payload["pronunciation"]["notes"] = ["伪造的发音判断"]
        with self.assertRaises(ValueError):
            wb.validate_session(payload)

    def test_default_paths_and_port(self):
        """核对各命令共享数据目录，服务默认端口保持兼容。"""
        parser = wb.build_parser()
        for command in (["init"], ["archive", "--input", "example.json"], ["serve"]):
            self.assertEqual(parser.parse_args(command).data_dir, wb.DEFAULT_DATA_DIR)
        self.assertEqual(parser.parse_args(["serve"]).port, 8766)

    def test_http_ui_and_state(self):
        """在本机临时端口验证真实只读课程接口、静态资源与安全响应头。"""
        self.archive()
        static_dir = Path(wb.__file__).resolve().parent.parent / "assets/workbench"
        server = ThreadingHTTPServer(("127.0.0.1", 0), wb.make_handler(self.data_dir, static_dir))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/api/state", timeout=5) as response:
                self.assertEqual(json.load(response)["sessions"][0], self.session)
            with urlopen(base + "/", timeout=5) as response:
                self.assertIn("日语口语复习台", response.read().decode("utf-8"))
            for path in ("/app.js", "/styles.css", "/daily-quotes.js"):
                with urlopen(base + path, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                    self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_readonly_routes_block_cross_site_and_private_files(self):
        """实测废弃接口、写方法、非白名单文件及跨站请求全部被拒绝且不修改存档。"""
        self.archive()
        original = (self.data_dir / "workbench-data.json").read_bytes()
        static_dir = self.root / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("safe page", encoding="utf-8")
        (static_dir / "private.txt").write_text("private sentinel", encoding="utf-8")
        server = ThreadingHTTPServer(("127.0.0.1", 0), wb.make_handler(self.data_dir, static_dir))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            cases = [("GET", path, {}, 404) for path in ("/api/health", "/api/preferences", "/private.txt", "/../input.json", "/%2e%2e/input.json", "/.git/config")]
            cases += [(method, "/api/preferences", {}, 405) for method in ("PUT", "POST", "DELETE", "PATCH", "OPTIONS", "TRACE")]
            cases += [("GET", "/api/state", headers, 403) for headers in ({"Host": "evil.example"}, {"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"})]
            for method, path, headers, expected in cases:
                with self.subTest(method=method, path=path, headers=headers):
                    connection = HTTPConnection("127.0.0.1", port, timeout=5)
                    try:
                        connection.request(method, path, headers=headers)
                        response = connection.getresponse()
                        self.assertEqual(response.status, expected)
                        self.assertNotIn(b"private sentinel", response.read())
                    finally:
                        connection.close()
            connection = HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request("HEAD", "/")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"")
            connection.close()
            self.assertEqual((self.data_dir / "workbench-data.json").read_bytes(), original)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_http_errors_hide_paths_and_reads_do_not_create_data(self):
        """验证只读请求不初始化磁盘，坏存档的错误信息也不包含本机路径。"""
        static_dir = self.root / "static"
        server = ThreadingHTTPServer(("127.0.0.1", 0), wb.make_handler(self.data_dir, static_dir))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            connection.request("GET", "/api/state")
            response = connection.getresponse()
            self.assertEqual(json.loads(response.read())["sessions"], [])
            self.assertFalse(self.data_dir.exists())
            self.data_dir.mkdir()
            (self.data_dir / "workbench-data.json").write_text("invalid", encoding="utf-8")
            connection.request("GET", "/api/state")
            response = connection.getresponse()
            self.assertEqual(response.status, 500)
            self.assertEqual(json.loads(response.read()), {"error": "local archive unavailable"})
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_public_bind_and_reserved_ids_rejected(self):
        """验证公网绑定在写盘前被拒绝，并拒绝 Windows 设备名与路径式 ID。"""
        with self.assertRaises(ValueError):
            wb.serve(self.data_dir, "0.0.0.0", 0, False)
        self.assertFalse(self.data_dir.exists())
        for sid in ("..", "CON", "NUL.txt", "LPT1", "../escape"):
            payload = copy.deepcopy(self.session)
            payload["id"] = sid
            with self.subTest(sid=sid), self.assertRaises(ValueError):
                wb.validate_session(payload)


if __name__ == "__main__":
    unittest.main()
