# 旭川消防出動通知

旭川市消防本部の[消防隊出動情報](https://www1.city.asahikawa.hokkaido.jp/bousai/syutsudou.htm)を5分ごとに確認し、新しい出動情報が掲載された場合にGitHub Issueを作成します。

## 通知内容

- 日時
- 場所
- 種別
- 旭川市公式ページへのリンク

同じ「日時・場所・種別」は一度だけ通知します。監視はGitHub Actions上で行うため、iPhoneの電池を継続的に消費しません。

## iPhoneでバナー通知を受ける設定

GitHubアプリで `Profile` → 歯車 → `Notifications` を開き、`Assignments` のプッシュ通知をオンにします。出動情報のIssueにはリポジトリ所有者が担当者として設定されます。

## 実行間隔

通常は5分ごとです。GitHub Actionsの混雑時には実行が数分遅れる場合があります。
