#!/usr/bin/env python3
"""函館市消防本部の出動情報を確認し、新規出動をGitHub Issueで通知する。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from html.parser import HTMLParser

SOURCE_URL = "http://fc23371220232011.web4.blks.jp/html/index.html"
OFFICIAL_URL = "https://www.city.hakodate.hokkaido.jp/docs/2016050900014/"
RECIPIENTS = ("abe0800",)
USER_AGENT = "HakodateDispatchMonitor/1.0 (+GitHub Actions)"
KEY_MARKER = "hakodate-dispatch-key"


class DisasterInfoParser(HTMLParser):
    """SGINFOテーブルの行ごとに、画面へ表示される文字列を集める。"""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[str] = []
        self._table_depth = 0
        self._in_disaster_table = False
        self._row_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        attributes = {name.lower(): value or "" for name, value in attrs}
        if tag == "table":
            classes = attributes.get("class", "").lower().split()
            if self._in_disaster_table:
                self._table_depth += 1
            elif "sginfo" in classes:
                self._in_disaster_table = True
                self._table_depth = 1
        elif tag == "tr" and self._in_disaster_table:
            self._row_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_disaster_table and self._row_parts is not None:
            text = re.sub(r"\s+", " ", data).strip()
            if text:
                self._row_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "tr" and self._in_disaster_table and self._row_parts is not None:
            row = normalize_text(" ".join(self._row_parts))
            if row:
                self.rows.append(row)
            self._row_parts = None
        elif tag == "table" and self._in_disaster_table:
            self._table_depth -= 1
            if self._table_depth == 0:
                self._in_disaster_table = False


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("，", "、").replace(",", "、")
    return re.sub(r"\s+", " ", value).strip()


def fetch_page() -> str:
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        declared = response.headers.get_content_charset()

    for encoding in (declared, "cp932", "shift_jis", "utf-8", "euc_jp"):
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("cp932", errors="replace")


def event_from_row(row: str) -> dict[str, str] | None:
    if "現在、消防車の出動はありません" in row:
        return None
    if "消防車" not in row or "出動" not in row:
        return None

    datetime_match = re.search(
        r"(?:(?P<year>\d{4})年)?(?P<month>\d{1,2})月(?P<day>\d{1,2})日"
        r"\s*(?P<hour>\d{1,2})時(?P<minute>\d{1,2})分",
        row,
    )
    if not datetime_match:
        raise RuntimeError(f"出動らしい行から日時を読み取れませんでした: {row}")

    date = f"{int(datetime_match.group('month')):02d}/{int(datetime_match.group('day')):02d}"
    if datetime_match.group("year"):
        date = f"{datetime_match.group('year')}/{date}"
    time = f"{int(datetime_match.group('hour')):02d}:{int(datetime_match.group('minute')):02d}"
    detail = normalize_text(row[datetime_match.end():]).lstrip(" :・【】")

    location_match = re.search(r"(?P<location>函館市.+?付近)(?:で|において)", detail)
    location = location_match.group("location") if location_match else "函館市内"

    kind = "消防出動"
    if location_match:
        remainder = detail[location_match.end():]
        kind_match = re.match(
            r"(?P<kind>.+?)(?:発生)?(?:のため|により)[、 ]*消防車(?:が|を)",
            remainder,
        )
        if kind_match:
            kind = normalize_text(kind_match.group("kind")).rstrip("、。 ")

    canonical = f"{date}|{time}|{location}|{kind}|{detail}"
    key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
    return {
        "key": key,
        "date": date,
        "time": time,
        "location": location,
        "kind": kind,
        "detail": detail,
    }


def extract_events(html: str) -> list[dict[str, str]]:
    parser = DisasterInfoParser()
    parser.feed(html)
    events: list[dict[str, str]] = []
    seen: set[str] = set()

    for row in parser.rows:
        event = event_from_row(row)
        if event is None or event["key"] in seen:
            continue
        seen.add(event["key"])
        events.append(event)

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
            match = re.search(rf"<!-- {KEY_MARKER}:([0-9a-f]{{20}}) -->", body)
            if match:
                keys.add(match.group(1))
        if len(issues) < 100:
            break
        page += 1
    return keys


def create_notification(event: dict[str, str]) -> None:
    title = f"🚒 函館｜{event['kind']}｜{event['location']}"
    mentions = " ".join(f"@{username}" for username in RECIPIENTS)
    body = (
        f"{mentions}\n\n"
        "函館市消防本部の災害情報に新しい出動が掲載されました。\n\n"
        f"- 日時：{event['date']} {event['time']}\n"
        f"- 場所：{event['location']}\n"
        f"- 種別：{event['kind']}\n"
        f"- 発表内容：{event['detail']}\n\n"
        f"[函館市消防本部の災害情報案内を開く]({OFFICIAL_URL})\n\n"
        "※函館市の公開情報を監視プログラムで確認・加工した通知です。\n\n"
        f"<!-- {KEY_MARKER}:{event['key']} -->"
    )
    github_request("POST", "/issues", {"title": title, "body": body})


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
