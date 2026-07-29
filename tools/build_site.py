#!/usr/bin/env python3
"""papers/ 配下のMarkdownから docs/papers.json と INDEX.md を生成する。

外部ライブラリに依存しない。リポジトリのルートで以下を実行する。

    python3 tools/build_site.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAPERS_DIR = ROOT / "papers"
DOCS_DIR = ROOT / "docs"
INDEX_MD = ROOT / "INDEX.md"

# 公開サイトのURL（INDEX.md の冒頭に載る。リポジトリ名を変えたらここも直す）
# 空文字にすると INDEX.md にURL行を出力しない。
# 注意: 公開サイト側（docs/index.html）にはリポジトリへのリンクを置かない方針。
SITE_URL = "https://miki0902.github.io/TestT/"

# ---------------------------------------------------------------------------
# タグ定義（このリポジトリで唯一の正）
#
# タグを追加するときは、ここに「タグ名: [バッジ背景色, 文字色/帯の色]」を足すだけでよい。
# docs/index.html は docs/papers.json 経由でこの定義を読むため、編集不要。
# 追加後は README.md のタグ表にも1行足しておくこと（説明用）。
# 色は、淡い背景色と、その上で読める鮮やかな文字色の組で指定する。
# ---------------------------------------------------------------------------
TAGS = {
    "アーキテクチャ提案":         ["#d6e6ff", "#0b63e5"],
    "学習・最適化手法":           ["#d2f5da", "#00963f"],
    "モデル圧縮・効率化":         ["#ffeec2", "#c47800"],
    "データ構築・フィルタリング": ["#c6f5ec", "#009486"],
    "推論時フレームワーク":       ["#e6d9ff", "#7326ee"],
    "検索拡張・記憶":             ["#ffd9ea", "#e0116e"],
    "評価・解析フレームワーク":   ["#dae4f0", "#3d6a99"],
    "基盤モデル":                 ["#dcdcff", "#3a34e0"],
    "世界モデル・具現化AI":       ["#e6f7ae", "#6ba300"],
    "マルチモーダル・生成":       ["#ffdec4", "#f26100"],
    "コード・科学応用":           ["#c9edff", "#0092d6"],
    "安全性・アラインメント":     ["#ffd9d1", "#ec3214"],
    "理論研究":                   ["#e4e0d6", "#7a6a4f"],
}

VALID_TAGS = list(TAGS)

REQUIRED_KEYS = [
    "arxiv_id",
    "title_ja",
    "title_en",
    "authors_org",
    "year",
    "venue",
    "venue_type",
    "tags",
    "summary_line",
    "arxiv_url",
    "code_url",
    "project_url",
    "added_at",
]


def parse_scalar(raw: str):
    """YAMLのスカラー値（引用符付き文字列・数値・配列）を解釈する。"""
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"').strip("'") for item in inner.split(",")]
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw


def split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        raise ValueError("frontmatter が見つかりません")
    end = text.index("\n---", 3)
    head = text[3:end].strip("\n")
    body = text[end + 4 :].lstrip("\n")

    meta: dict = {}
    for line in head.split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = parse_scalar(value)
    return meta, body


def split_sections(body: str) -> dict:
    """本文を '## 見出し' 単位に分割する。"""
    sections: dict = {}
    current = None
    buffer: list[str] = []
    for line in body.split("\n"):
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buffer).strip()
            current = line[3:].strip()
            buffer = []
        else:
            buffer.append(line)
    if current is not None:
        sections[current] = "\n".join(buffer).strip()
    return sections


def parse_summary(section: str) -> dict:
    """研究サマリーを 課題・手法・成果 に分解する。"""
    result = {"課題": "", "手法": "", "成果": ""}
    for label in result:
        match = re.search(rf"\*\*{label}\*\*\s*[—-]\s*(.+?)(?=\n\n\*\*|\Z)", section, re.S)
        if match:
            result[label] = match.group(1).strip()
    return result


def parse_points(section: str) -> list[str]:
    return [line[2:].strip() for line in section.split("\n") if line.startswith("- ")]


def collect() -> tuple[list[dict], list[str]]:
    papers: list[dict] = []
    warnings: list[str] = []
    seen_ids: dict[str, str] = {}

    for path in sorted(PAPERS_DIR.rglob("*.md")):
        rel = path.relative_to(ROOT).as_posix()
        try:
            meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            warnings.append(f"{rel}: {exc}")
            continue

        for key in REQUIRED_KEYS:
            if key not in meta:
                warnings.append(f"{rel}: frontmatter に {key} がありません")

        tags = meta.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        for tag in tags:
            if tag not in VALID_TAGS:
                warnings.append(f"{rel}: 未定義のタグ '{tag}'")

        arxiv_id = str(meta.get("arxiv_id", ""))
        if arxiv_id in seen_ids:
            warnings.append(f"{rel}: arxiv_id {arxiv_id} が {seen_ids[arxiv_id]} と重複")
        else:
            seen_ids[arxiv_id] = rel

        sections = split_sections(body)
        papers.append(
            {
                "arxiv_id": arxiv_id,
                "title_ja": meta.get("title_ja", ""),
                "title_en": meta.get("title_en", ""),
                "authors_org": meta.get("authors_org", ""),
                "year": meta.get("year", 0),
                "venue": meta.get("venue", ""),
                "venue_type": meta.get("venue_type", ""),
                "tags": tags,
                "summary_line": meta.get("summary_line", ""),
                "arxiv_url": meta.get("arxiv_url", ""),
                "code_url": meta.get("code_url", ""),
                "project_url": meta.get("project_url", ""),
                "added_at": meta.get("added_at", ""),
                "path": rel,
                "summary": parse_summary(sections.get("研究サマリー", "")),
                "points": parse_points(sections.get("ポイント", "")),
            }
        )

    papers.sort(key=lambda p: (-int(p["year"] or 0), str(p["venue"]), str(p["title_ja"])))
    return papers, warnings


def write_json(papers: list[dict]) -> None:
    DOCS_DIR.mkdir(exist_ok=True)
    payload = {
        "generated_at": date.today().isoformat(),
        "count": len(papers),
        "tags": VALID_TAGS,
        "tag_colors": TAGS,
        "papers": papers,
    }
    (DOCS_DIR / "papers.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_index(papers: list[dict]) -> None:
    lines = [
        "# 収録論文インデックス",
        "",
        f"収録件数: {len(papers)} 件 / 最終更新: {date.today().isoformat()}",
        "",
    ]
    if SITE_URL:
        lines += [f"公開サイト: {SITE_URL}", ""]

    current_venue = None
    for paper in papers:
        if paper["venue"] != current_venue:
            if current_venue is not None:
                lines.append("")
            current_venue = paper["venue"]
            lines += [
                f"## {current_venue}",
                "",
                "| タイトル（日本語） | 一行要約 | 年 | 形式 | タグ | リンク |",
                "|---|---|---|---|---|---|",
            ]
        tags = " / ".join(paper["tags"])
        links = f"[md]({paper['path']}) ・ [arXiv]({paper['arxiv_url']})"
        lines.append(
            f"| {paper['title_ja']} | {paper['summary_line']} | {paper['year']} | "
            f"{paper['venue_type']} | {tags} | {links} |"
        )
    lines.append("")
    INDEX_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    if not PAPERS_DIR.exists():
        print(f"papers/ が見つかりません: {PAPERS_DIR}", file=sys.stderr)
        return 1

    papers, warnings = collect()
    write_json(papers)
    write_index(papers)

    print(f"収録 {len(papers)} 件 → docs/papers.json, INDEX.md を更新しました")
    if warnings:
        print("\n警告:")
        for warning in warnings:
            print(f"  - {warning}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
