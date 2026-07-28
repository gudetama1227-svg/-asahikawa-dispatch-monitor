#!/usr/bin/env python3
"""旭川市消防本部の出動情報を確認し、新規出動をGitHub Issueで通知する。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser

SOURCE_URL = "https://www1.city.asahikawa.hokkaido.jp/bousai/syutsudou.htm"
ASSIGNEE = "gudetama1227-svg"
USER_AGENT = "AsahikawaDispatchMonitor/1.0 (+GitHub Actions)"


class DispatchTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.all_text: list[str] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.all_text.append(text)
            if self._cell is not None:
                self._cell.append(text)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            value = " ".join(self._cell)
            value = re.sub(r"\s+", " ", value).strip()
            self._row.append(value)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell = None


def fetch_page() -> str:
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        declared = response.headers.get_content_charset()

    encodings = [declared, "utf-8", "cp932", "shift_jis", "euc_jp"]
    for encoding in encodings:
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def extract_events(html: str) -> list[dict[str, str]]:
    parser = DispatchTableParser()
    parser.feed(html)
    events: list[dict[str, str]] = []
    seen: set[str] = set()

    date_pattern = re.compile(r"(?P<date>\d{4}[/-]\d{2}[/-]\d{2})")
    time_pattern = re.compile(r"(?P<time>\d{2}:\d{2})")

    for cells in parser.rows:
        date_index = next((i for i, cell in enumerate(cells) if date_pattern.search(cell)), None)
        if date_index is None:
            continue

        date_match = date_pattern.search(cells[date_index])
        time_match = time_pattern.search(cells[date_index])
        after_datetime = date_index + 1

        if time_match is None and date_index + 1 < len(cells):
            time_match = time_pattern.search(cells[date_index + 1])
            if time_match:
                after_datetime = date_index + 2

        if not date_match or not time_match or len(cells) - after_datetime < 2:
            continue

        location = " ".join(cells[after_datetime:-1]).strip()
        kind = cells[-1].strip()
        if not location or not kind or kind == "種別":
            continue

        date = date_match.group("date").replace("-", "/")
        time = time_match.group("time")
        raw_key = f"{date}|{time}|{location}|{kind}"
        key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:20]
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "key": key,
            "date": date,
            "time": time,
            "location": location,
            "kind": kind,
        })

    page_text = " ".join(parser.all_text)
    page_text = re.sub(r"\s+", " ", page_text)
    count_match = re.search(r"現在進行中の災害は\s*(\d+)\s*件", page_text)
    expected_count = int(count_match.group(1)) if count_match else None

    if expected_count and len(events) < expected_count:
        raise RuntimeError(
            f"ページは{expected_count}件と表示していますが、{len(events)}件しか読み取れませんでした。"
        )

    return events


def github_request(method: str, endpoint: str, payload: dict | None = None):
    token = os.environ["GITHUB_TOKEN"]
    repository = os.environ["GITHUB_REPOSITORY"]
    url = f"https://api.github.com/repos/{repository}{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
        return json.loads(body) if body else None


def existing_keys() -> set[str]:
    keys: set[str] = set()
    page = 1
    while page <= 20:
        issues = github_request("GET", f"/issues?state=all&per_page=100&page={page}")
        if not issues:
            break
        for issue in issues:
            body = issue.get("body") or ""
            match = re.search(r"<!-- dispatch-key:([0-9a-f]{20}) -->", body)
            if match:
                keys.add(match.group(1))
        if len(issues) < 100:
            break
        page += 1
    return keys


def create_notification(event: dict[str, str]) -> None:
    title = f"🚒 {event['kind']}｜{event['location']}"
    body = (
        f"@{ASSIGNEE}\n\n"
        f"旭川市消防本部の出動情報に新しい情報が掲載されました。\n\n"
        f"- 日時：{event['date']} {event['time']}\n"
        f"- 場所：{event['location']}\n"
        f"- 種別：{event['kind']}\n\n"
        f"[旭川市消防本部の出動情報を開く]({SOURCE_URL})\n\n"
        f"<!-- dispatch-key:{event['key']} -->"
    )
    github_request(
        "POST",
        "/issues",
        {"title": title, "body": body, "assignees": [ASSIGNEE]},
    )


def main() -> int:
    try:
        events = extract_events(fetch_page())
        known = existing_keys()
        new_events = [event for event in events if event["key"] not in known]
        for event in new_events:
            create_notification(event)
        print(f"current={len(events)} new={len(new_events)}")
        return 0
    except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, KeyError) as error:
        print(f"monitor failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
