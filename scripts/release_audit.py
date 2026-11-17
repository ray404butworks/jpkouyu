#!/usr/bin/env python3
"""检查本仓库的依赖、字体资源、Python 中文注释和遗留危险模式，输出审计清单。"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path


def has_chinese(value):
    """判断注释是否包含中文，避免只统计空注释或英文占位。"""
    return bool(re.search(r"[\u4e00-\u9fff]", value or ""))


def scan(root):
    """扫描自有源文件并返回可复核的事实；不把自动结果当成人工或法律结论。"""
    files = sorted(path for path in root.rglob("*") if path.is_file() and not any(part in {".git", "__pycache__", "node_modules", ".pytest_cache"} for part in path.relative_to(root).parts))
    python_files = [path for path in files if path.suffix == ".py"]
    local_modules = {path.stem for path in python_files}
    external = set()
    functions = 0
    callbacks = 0
    missing = []
    for path in python_files:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                external.update(alias.name.split(".")[0] for alias in node.names if alias.name.split(".")[0] not in sys.stdlib_module_names | local_modules)
            elif isinstance(node, ast.ImportFrom) and node.module:
                name = node.module.split(".")[0]
                if name not in sys.stdlib_module_names | local_modules:
                    external.add(name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions += 1
                if not has_chinese(ast.get_docstring(node)):
                    missing.append(f"{path.relative_to(root).as_posix()}:{node.lineno}:{node.name}")
            elif isinstance(node, ast.Lambda):
                callbacks += 1
                if not has_chinese(lines[node.lineno - 1].split("#", 1)[-1]) or "#" not in lines[node.lineno - 1]:
                    missing.append(f"{path.relative_to(root).as_posix()}:{node.lineno}:lambda")
    css = (root / "assets/workbench/styles.css").read_text(encoding="utf-8")
    font_files = [path.relative_to(root).as_posix() for path in files if path.suffix.lower() in {".woff", ".woff2", ".ttf", ".otf", ".eot"}]
    declarations = set(re.findall(r"(--[a-z-]+)\s*:", css))
    uses = set(re.findall(r"var\((--[a-z-]+)", css))
    requirements = [line.strip() for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    return {
        "scope": "repository source; excludes interpreter, OS, browser and audit-only tools",
        "python_functions": functions,
        "python_callbacks": callbacks,
        "missing_chinese_comments": missing,
        "external_python_imports": sorted(external),
        "declared_python_requirements": requirements,
        "npm_manifests": [path.relative_to(root).as_posix() for path in files if path.name in {"package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"}],
        "font_files": font_files,
        "font_file_bytes": sum((root / name).stat().st_size for name in font_files),
        "remote_font_or_css_import": bool(re.search(r"@font-face|@import|url\(", css, re.I)),
        "unused_css_variables": sorted(declarations - uses),
        "public_review_required": ["14 literary excerpts: territory, commercial use and attribution", "real human review has not been signed off"],
    }


def main():
    """定位技能仓库并打印 JSON；发现注释或依赖漂移时返回非零退出码。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    result = scan(args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if any(result[key] for key in ("missing_chinese_comments", "external_python_imports", "declared_python_requirements", "npm_manifests", "font_files", "remote_font_or_css_import", "unused_css_variables")):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
