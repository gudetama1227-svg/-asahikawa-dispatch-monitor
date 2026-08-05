# 旭川・函館 消防出動通知

次の公式情報を約5分ごとに確認し、新しい出動情報が掲載された場合にGitHub Issueを作成します。

- 旭川市消防本部の[消防隊出動情報](https://www1.city.asahikawa.hokkaido.jp/bousai/syutsudou.htm)
- 函館市消防本部の[災害情報案内](https://www.city.hakodate.hokkaido.jp/docs/2016050900014/)

## 通知内容

- 日時
- 場所
- 種別
- 旭川市公式ページへのリンク

同じ出動は一度だけ通知します。函館の通知タイトルには「函館」と表示されます。監視はGitHub Actions上で行うため、iPhoneの電池を継続的に消費しません。

## iPhoneでバナー通知を受ける設定

GitHubアプリで `Profile` → 歯車 → `Notifications` を開き、`Assignments` のプッシュ通知をオンにします。出動情報のIssueにはリポジトリ所有者が担当者として設定されます。

## 実行間隔

通常は5分ごとです。GitHub Actionsの混雑時には実行が数分遅れる場合があります。
