#!/usr/bin/env python3
"""Persist Japanese speaking sessions and serve the local review workbench."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import threading
import webbrowser
from collections import defaultdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

VERSION = 1
ALLOWED_STATUS = {"mastered", "developing", "needs_review", "not_observed"}
ALLOWED_SUPPORT = {"independent", "intent_hint", "keyword_hint", "model", "none"}
DEFAULT_DATA_DIR = Path("G:/AI/OpenAI/Workspaces/jpkouyu-data")


def empty_state() -> dict:
    """构造空的日语复习台状态，不预置任何虚构学习记录。"""
    return {
        "version": VERSION,
        "language": "ja",
        "preferences": {"level": "beginner", "hint_mode": "guided", "reading_mode": "kana", "register": "polite"},
        "sessions": [],
    }


def atomic_json(path: Path, payload: dict) -> None:
    """在目标目录创建临时文件并原子替换 JSON，避免读取到半写入内容。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def load_state(data_dir: Path, create: bool = True) -> dict:
    """读取并验证旧版课程汇总；只读请求通过 create=False 禁止自动建档。"""
    path = data_dir / "workbench-data.json"
    if not path.exists():
        state = empty_state()
        if create:
            atomic_json(path, state)
        return state
    with path.open(encoding="utf-8-sig") as handle:
        state = json.load(handle)
    validate_state(state)
    return state


def require(value: object, expected: type, label: str) -> None:
    """检查字段类型，异常时报告具体字段名称以便修正归档输入。"""
    if not isinstance(value, expected):
        raise ValueError(f"{label} must be {expected.__name__}")


def validate_session(session: dict) -> None:
    """校验旧版课程的标识、类型、掌握证据和发音观察边界。"""
    require(session, dict, "session")
    for key in ("id", "created_at", "topic", "duration_minutes", "level", "hint_mode", "targets"):
        if key not in session:
            raise ValueError(f"missing required field: {key}")
    if session.get("language") != "ja":
        raise ValueError("language must be ja; use a separate archive for other languages")
    if session["level"] not in {"zero", "beginner", "intermediate", "advanced"}:
        raise ValueError("invalid level")
    if session["hint_mode"] not in {"immersion", "guided", "learning"}:
        raise ValueError("invalid hint_mode")
    require(session["created_at"], str, "created_at")
    created_at = datetime.fromisoformat(session["created_at"])
    if created_at.tzinfo is None:
        raise ValueError("created_at must include timezone")
    pronunciation = session.get("pronunciation", {"status": "not_observed", "notes": []})
    require(pronunciation, dict, "pronunciation")
    if pronunciation.get("status") not in {"observed", "not_observed"}:
        raise ValueError("invalid pronunciation.status")
    require(pronunciation.get("notes"), list, "pronunciation.notes")
    if not all(isinstance(note, str) for note in pronunciation["notes"]):
        raise ValueError("pronunciation.notes must contain strings")
    if pronunciation["status"] == "not_observed" and pronunciation["notes"]:
        raise ValueError("unobserved pronunciation cannot have findings")
    if not isinstance(session["id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", session["id"]):
        raise ValueError("id must start with a letter or digit and contain at most 80 safe characters")
    if session["id"].split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        raise ValueError("reserved Windows filename")
    require(session["topic"], dict, "topic")
    require(session["topic"].get("id"), str, "topic.id")
    require(session["topic"].get("label"), str, "topic.label")
    if not isinstance(session["duration_minutes"], (int, float)) or not 1 <= session["duration_minutes"] <= 240:
        raise ValueError("duration_minutes must be between 1 and 240")
    require(session["targets"], list, "targets")
    for index, target in enumerate(session["targets"]):
        require(target, dict, f"targets[{index}]")
        require(target.get("expression"), str, f"targets[{index}].expression")
        if target.get("status") not in ALLOWED_STATUS:
            raise ValueError(f"targets[{index}].status is invalid")
        if target.get("support", "none") not in ALLOWED_SUPPORT:
            raise ValueError(f"targets[{index}].support is invalid")
        for field in ("reading", "meaning_zh", "evidence"):
            if field in target:
                require(target[field], str, f"targets[{index}].{field}")
        if target["status"] == "mastered" and target.get("support") != "independent":
            raise ValueError("mastered targets must have independent support")
    repairs = session.get("repairs", [])
    require(repairs, list, "repairs")
    for index, repair in enumerate(repairs):
        require(repair, dict, f"repairs[{index}]")
        require(repair.get("learner"), str, f"repairs[{index}].learner")
        require(repair.get("natural"), str, f"repairs[{index}].natural")
        require(repair.get("reason_zh"), str, f"repairs[{index}].reason_zh")
        if repair.get("kind", "repair") not in {"keep", "repair", "alternative"}:
            raise ValueError("invalid repair.kind")
        if "natural_reading" in repair:
            require(repair["natural_reading"], str, f"repairs[{index}].natural_reading")
    focus_next = session.get("focus_next", [])
    require(focus_next, list, "focus_next")
    if not all(isinstance(item, str) and item.strip() for item in focus_next):
        raise ValueError("focus_next must contain non-empty strings")
    if len(focus_next) > 3:
        raise ValueError("focus_next allows at most three items")
    if "next_drill" in session:
        require(session["next_drill"], str, "next_drill")


def validate_state(state: dict) -> None:
    """校验旧版汇总的日语标记和全部课程，防止混入其他格式。"""
    require(state, dict, "state")
    if state.get("language") != "ja":
        raise ValueError("not a Japanese workbench; choose a separate --data-dir")
    require(state.get("sessions"), list, "sessions")
    for session in state["sessions"]:
        validate_session(session)


def latest_targets(items: list[dict]) -> list[dict]:
    """输入按时间倒序的课程，保留每个表达的最近一次状态。"""
    latest: dict[str, dict] = {}
    for session in items:
        for target in session.get("targets", []):
            expression = target.get("expression", "").strip()
            if expression and expression not in latest:
                latest[expression] = target
    return list(latest.values())


def recent_repairs(items: list[dict], limit: int = 3) -> list[dict]:
    """按最新优先取不重复的原句与改法，最多返回指定条数。"""
    seen: set[tuple[str, str]] = set()
    result: list[dict] = []
    for session in items:
        for repair in session.get("repairs", []):
            key = (repair.get("learner", ""), repair.get("natural", ""))
            if key not in seen:
                seen.add(key)
                result.append(repair)
                if len(result) == limit:
                    return result
    return result


def render_dashboard(state: dict) -> str:
    """把旧版真实课程汇总为中文 Markdown 复习台，不更改历史数据。"""
    sessions = sorted(state["sessions"], key=lambda item: item.get("created_at", ""), reverse=True)  # 回调：按课程日期倒序整理最近记录。
    grouped: dict[str, list[dict]] = defaultdict(list)
    for session in sessions:
        grouped[session["topic"]["label"]].append(session)

    lines = ["# 日语口语复习台", "", f"> 已归档 {len(sessions)} 次练习。", ""]
    if not sessions:
        lines += ["还没有练习记录。完成第一次场景对话后，这里会自动生成复习内容。", ""]
    for topic, items in grouped.items():
        targets = latest_targets(items)
        mastered = sum(target.get("status") == "mastered" for target in targets)
        review = [target.get("expression", "") for target in targets if target.get("status") in {"developing", "needs_review"}]
        repairs = recent_repairs(items)
        latest = items[0]
        lines += [f"## {items[0]['topic'].get('emoji', '💬')} {topic}", ""]
        lines += [f"- 练习次数：{len(items)}", f"- 已掌握表达：{mastered}/{len(targets)}", f"- 最近练习：{items[0].get('created_at', '')}"]
        if review:
            unique = list(dict.fromkeys(filter(None, review)))[:5]
            lines.append(f"- 下次复习：{'、'.join(unique)}")
        focus_next = [item for item in latest.get("focus_next", []) if item][:3]
        if focus_next:
            lines.append(f"- 下次重点：{'、'.join(focus_next)}")
        if latest.get("next_drill"):
            lines.append(f"- 迁移练习：{latest['next_drill']}")
        if targets:
            lines += ["", "### 日语表达", ""]
            for target in targets:
                reading = f"（{target['reading']}）" if target.get("reading") else ""
                lines.append(f"- {target['expression']}{reading}：{target.get('meaning_zh', '')} [{target['status']}]")
        if repairs:
            lines += ["", "### 表达复盘", ""]
            for repair in repairs:
                label = {"keep": "保留", "repair": "纠正", "alternative": "可选说法"}[repair.get("kind", "repair")]
                lines.append(f"- [{label}] `{repair['learner']}` → `{repair['natural']}`：{repair['reason_zh']}")
                if repair.get("natural_reading"):
                    lines.append(f"  - 读音：{repair['natural_reading']}")
        lines.append("")
    lines += ["---", "", f"更新时间：{datetime.now().astimezone().isoformat(timespec='seconds')}", ""]
    return "\n".join(lines)


def save_state(data_dir: Path, state: dict) -> None:
    """校验后保存旧版 JSON 汇总与可读的 Markdown 复习记录。"""
    validate_state(state)
    state["version"] = VERSION
    atomic_json(data_dir / "workbench-data.json", state)
    (data_dir / "复习台.md").write_text(render_dashboard(state), encoding="utf-8")


def init_workbench(data_dir: Path) -> None:
    """初始化显式数据目录，保留现有课程并生成旧版复习文件。"""
    data_dir.mkdir(parents=True, exist_ok=True)
    state = load_state(data_dir)
    save_state(data_dir, state)
    print(f"Workbench ready: {data_dir.resolve()}")


def archive_session(data_dir: Path, input_path: Path) -> None:
    """校验输入并合并旧版单课记录，拒绝已有同 ID 的不同内容。"""
    with input_path.open(encoding="utf-8-sig") as handle:
        session = json.load(handle)
    validate_session(session)
    state = load_state(data_dir)
    existing = next((item for item in state["sessions"] if item["id"] == session["id"]), None)
    if existing is not None and existing != session:
        raise ValueError(f"session id already exists with different data: {session['id']}")
    if existing is None:
        state["sessions"].append(session)
    sessions_dir = data_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(sessions_dir / f"{session['id']}.json", session)
    save_state(data_dir, state)
    print(f"Archived: {session['id']}")


def make_handler(data_dir: Path, static_dir: Path):
    """创建绑定私有数据目录和固定静态目录的只读 HTTP 处理类。"""
    class WorkbenchHandler(BaseHTTPRequestHandler):
        """只读本机复习台；不继承任意静态目录与符号链接访问能力。"""

        server_version = "JPKouyu"
        sys_version = ""

        def reply(self, body: bytes, content_type: str, status: int = 200) -> None:
            """统一返回安全响应头；HEAD 与 GET 共享头部但不发送正文。"""
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; font-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            if status == 405:
                self.send_header("Allow", "GET, HEAD")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def send_json(self, payload: dict, status: int = 200) -> None:
            """序列化有限的公开错误或课程数据，不暴露磁盘路径与异常详情。"""
            self.reply(json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status)

        def trusted_request(self) -> bool:
            """检查 Host、Origin 和浏览器站点上下文，阻断 DNS 重绑定及跨站读取。"""
            port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            host = self.headers.get("Host", "").lower()
            origins = {f"http://{value}" for value in hosts}
            origin = self.headers.get("Origin")
            if host not in hosts or (origin is not None and origin not in origins) or self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.send_json({"error": "request not allowed"}, 403)
                return False
            return True

        def do_GET(self):
            """仅开放课程只读接口和四个固定页面资源，其他路径统一拒绝。"""
            if not self.trusted_request():
                return
            path = urlparse(self.path).path
            if path == "/api/state":
                try:
                    self.send_json(load_state(data_dir, create=False))
                except (ValueError, OSError, TypeError, KeyError):
                    self.send_json({"error": "local archive unavailable"}, 500)
                return
            assets = {"/": ("index.html", "text/html; charset=utf-8"), "/index.html": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/daily-quotes.js": ("daily-quotes.js", "text/javascript; charset=utf-8"), "/styles.css": ("styles.css", "text/css; charset=utf-8")}
            if path not in assets:
                self.send_json({"error": "not found"}, 404)
                return
            name, content_type = assets[path]
            candidate = static_dir / name
            try:
                if candidate.is_symlink() or candidate.resolve().parent != static_dir.resolve():
                    self.send_json({"error": "not found"}, 404)
                    return
                self.reply(candidate.read_bytes(), content_type)
            except OSError:
                self.send_json({"error": "asset unavailable"}, 404)

        def do_HEAD(self):
            """复用只读路由与请求校验，供浏览器探测资源元数据。"""
            self.do_GET()

        def reject_write(self):
            """拒绝所有写入与调试方法，不读取请求体、不触碰学习记录。"""
            self.close_connection = True
            self.send_json({"error": "method not allowed"}, 405)

        do_PUT = do_POST = do_PATCH = do_DELETE = do_OPTIONS = do_TRACE = reject_write

        def log_message(self, format_string, *args):
            """仅记录方法与状态事件，不打印可能包含隐私或控制字符的原始路径。"""
            print(f"[{self.log_date_time_string()}] local request handled")

    return WorkbenchHandler


def serve(data_dir: Path, host: str, port: int, open_browser: bool) -> None:
    """仅在回环地址提供只读复习台；拒绝通过命令行暴露到局域网或公网。"""
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("workbench supports loopback hosts only")
    init_workbench(data_dir)
    static_dir = Path(__file__).resolve().parent.parent / "assets" / "workbench"
    if not (static_dir / "index.html").exists():
        raise FileNotFoundError(f"workbench UI missing: {static_dir}")
    server = ThreadingHTTPServer((host, port), make_handler(data_dir, static_dir))
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}/"
    print(f"Listening on {url}")
    if open_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()  # 回调：延迟打开本地复习台页面。
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def build_parser() -> argparse.ArgumentParser:
    """定义初始化、归档及只读服务参数，限制服务只能绑定回环地址。"""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "archive"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
        if command == "archive":
            sub.add_argument("--input", type=Path, required=True)
    sub = subparsers.add_parser("serve")
    sub.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    sub.add_argument("--host", choices=("127.0.0.1", "localhost"), default="127.0.0.1")
    sub.add_argument("--port", type=int, default=8766)
    sub.add_argument("--no-open", action="store_true")
    return parser


def main() -> None:
    """检查默认 G 盘和绝对路径，再执行用户明确选择的本地命令。"""
    args = build_parser().parse_args()
    if args.data_dir == DEFAULT_DATA_DIR and (os.name != "nt" or not Path("G:/").is_dir()):
        raise SystemExit("No G: drive available. Supply --data-dir with an absolute writable directory.")
    if not args.data_dir.is_absolute():
        raise SystemExit("--data-dir must be an absolute path")
    if args.command == "init":
        init_workbench(args.data_dir)
    elif args.command == "archive":
        archive_session(args.data_dir, args.input)
    else:
        serve(args.data_dir, args.host, args.port, not args.no_open)


if __name__ == "__main__":
    main()
