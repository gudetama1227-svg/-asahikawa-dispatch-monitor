#!/usr/bin/env python3
"""AgentReach方式（twitter-cli）で上川管内のX公開投稿を補助監視する。"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone


QUERIES = [
    "(旭川 OR 鷹栖 OR 東神楽 OR 東川 OR 当麻 OR 比布 OR 愛別 OR 上川町 OR 美瑛) (火事 OR 火災 OR 煙 OR サイレン OR パトカー OR 規制線 OR 事故 OR 事件 OR 停電 OR 断水 OR 通行止め OR クマ)",
    "(士別 OR 名寄 OR 和寒 OR 剣淵 OR 下川 OR 美深 OR 音威子府 OR 中川 OR 幌加内) (火事 OR 火災 OR 煙 OR サイレン OR パトカー OR 規制線 OR 事故 OR 事件 OR 停電 OR 断水 OR 通行止め OR クマ)",
    "(富良野 OR 上富良野 OR 中富良野 OR 南富良野 OR 占冠) (火事 OR 火災 OR 煙 OR サイレン OR パトカー OR 規制線 OR 事故 OR 事件 OR 停電 OR 断水 OR 通行止め OR クマ)",
]

AREA_TERMS = [
    ("南富良野", "南富良野町"), ("中富良野", "中富良野町"), ("上富良野", "上富良野町"),
    ("音威子府", "音威子府村"), ("東神楽", "東神楽町"), ("幌加内", "幌加内町"),
    ("旭川", "旭川市"), ("士別", "士別市"), ("名寄", "名寄市"), ("富良野", "富良野市"),
    ("鷹栖", "鷹栖町"), ("当麻", "当麻町"), ("比布", "比布町"), ("愛別", "愛別町"),
    ("上川", "上川町"), ("東川", "東川町"), ("美瑛", "美瑛町"), ("占冠", "占冠村"),
    ("和寒", "和寒町"), ("剣淵", "剣淵町"), ("下川", "下川町"), ("美深", "美深町"),
    ("中川", "中川町"),
]


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def area_for(text: str) -> str:
    for term, area in AREA_TERMS:
        if term in text:
            return area
    return "上川管内"


def recent(created_at: str) -> bool:
    if not created_at:
        return True
    try:
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return parsed >= datetime.now(timezone.utc) - timedelta(hours=6)
    except ValueError:
        return True


def main() -> None:
    if not os.environ.get("TWITTER_AUTH_TOKEN") or not os.environ.get("TWITTER_CT0"):
        emit({"connected": False, "status": "not_configured", "checked": 0, "detections": [], "error": None})
        return

    detections: dict[str, dict] = {}
    errors: list[str] = []
    for query in QUERIES:
        command = [
            "twitter", "search", query, "--type", "Latest", "--max", "20",
            "--exclude", "retweets", "--full-text", "--json",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
        if result.returncode != 0:
            errors.append((result.stderr or "twitter search failed").strip().splitlines()[-1][:180])
            continue
        try:
            payload = json.loads(result.stdout)
            rows = payload.get("data", []) if isinstance(payload, dict) else payload
        except (json.JSONDecodeError, AttributeError):
            errors.append("twitter-cli returned invalid JSON")
            continue
        for row in rows if isinstance(rows, list) else []:
            tweet_id = str(row.get("id") or "")
            text = " ".join(str(row.get("text") or "").split())
            created_at = str(row.get("createdAtISO") or row.get("createdAt") or "")
            author = row.get("author") if isinstance(row.get("author"), dict) else {}
            handle = str(author.get("screenName") or "i")
            if not tweet_id or not text or not recent(created_at):
                continue
            detections[tweet_id] = {
                "id": f"x:{tweet_id}",
                "sourceId": f"x:{tweet_id}",
                "sourceName": f"X公開投稿 @{handle}",
                "area": area_for(text),
                "url": f"https://x.com/{handle}/status/{tweet_id}",
                "signal": text[:1200],
                "lane": "now",
                "createdAt": created_at or datetime.now(timezone.utc).isoformat(),
            }

    status = "ok" if not errors else ("partial" if detections else "error")
    emit({
        "connected": True,
        "status": status,
        "checked": len(detections),
        "detections": list(detections.values()),
        "error": " / ".join(errors[:2]) if errors else None,
    })


if __name__ == "__main__":
    main()
