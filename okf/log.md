## 2026-08-04

**Creation** — バンドル（`OKF.md`、`okf/project.md`、`okf/index.md`）を Codex 側エージェント（`generated.by: openai/luna`）が作成。`status: draft`、`verified: []` で着地。この時点では未コミット。

## 2026-08-05

**Update** — Claude Code によるレビューで `OKF.md` と `okf/project.md` を2ラウンドにわたり修正。各ラウンドは別の Claude Code エージェントによる独立監査を経た。

- Round 1: `OKF.md` の薄いポインタ記述を補強（作業開始時に OKF.md/project.md を読むこと、OKFが進捗・タスクの正本ではないこと、OKF変更は `okf-knowledge` スキル経由であること、`okf/index.md` は機械生成であり手編集しないことを追記）。`project.md` から未裏付けの記述を削除。
- Round 2（Round 1の監査で問題を検出後）: Round 1 が誤って削除したスコープ項目を復元。`CHANGELOG.md`（「Nothing has been tagged or released yet.」）と `README.md`（「It is not a complete release.」）を出所として、`project.md` の「現在地」に Private-staging / pre-release の状態記述を追加し、`CHANGELOG.md` を `sources:` に追加。スコープ境界「含めるもの」に欠落していた `crosswalkのシリアライズ`、`retrieval projection` を追加。「全体の形」の過度に狭いスコープ主張（「このバンドルの対象外」→「公開コアの対象外」）を修正。`project.md` の `generated.by` / `generated.at` を `anthropic/claude-sonnet-5` とRound 2編集時刻に更新（本文の実際の作成者を反映。Aug-4原稿の作成者についての推測ではない）。

`okflint validate` / `okflint audit` は両ラウンド後とも0エラー。`status: draft`、`verified: []` は変更なし（人間による確認は未了）。

- 追加ラウンド: `AGENTS.md` に公開側OKF（`OKF.md`/`okf/project.md`）への導線を追加（作業開始時に読む、進捗・タスクの正本ではない、`okf-knowledge` スキルを使う、`index.md` は手編集しない）。`okf/log.md` をこの回で新規作成。`OKF.md` のカテゴリ一覧をリンク化（規範プロファイル・利用手順・セキュリティ・ライセンス／NOTICE・変更履歴）。`okf/project.md` と `okf/index.md` は変更していない。

## 2026-08-11

**Update** — `ARCHITECTURE_BOUNDARY.md` の非公開判定から「evaluative」という機能名ベースの語を外し、
非公開の理由が評価であること自体ではなく入力（取得済み・顧客コーパス、再現できないモデル出力）に
あることを明記した。合成fixtureと固定期待値による決定論的な評価は、他の成果物と同じ公開コア原則で
判断する。`docs/oss-release/scope-inventory.md` には、index・search・検索品質benchmarkがv0.1の
Out of scopeである理由が「囲い込み」ではなく責務の違いであり、OKFバンドルと本プロジェクトの
retrieval projectionを入力に取る別の公開プロジェクトが担うことを追記した。

`okf/project.md` の「全体の形」にある「運用・評価情報は公開コアの対象外」という要約は、上記の
明確化と食い違うため同じ場で書き直し、`ARCHITECTURE_BOUNDARY.md` と `scope-inventory.md` の
`last_modified` を 2026-08-11 に合わせ、`generated` を実際の改訂者と改訂時刻へ更新した。
`status: draft` / `verified: []` は変更していない。

あわせて、本改訂以前から残っていた `README.md`・規範プロファイル・`CHANGELOG.md` の
`SOURCE-DRIFT` を解消した。3件とも参照元を読み直し、`project.md` が依拠する記述
（README「It is not a complete release.」、CHANGELOG「Nothing has been tagged or released yet.」、
プロファイルが `0.1.0-draft` のv0.1契約であり公開コアの構成要素が変わっていないこと）が
現行の参照元でも成立することを確認したうえで `last_modified` を実ファイルへ合わせた。

## 2026-08-16

**Update** — `okf_freshness.py` が `project.md` に4件の `SOURCE-DRIFT`
（`README.md` 2026-08-06→08-12、`ARCHITECTURE_BOUNDARY.md` 08-11→08-15、
規範プロファイル 08-10→08-12、`CHANGELOG.md` 08-10→08-15）を検出したため、
4件とも参照元を読み直してから `last_modified` を合わせた。

読み直しで、`project.md` が依拠する既存の記述は現行の参照元でも成立することを確認した
（README「It is not a complete release.」、CHANGELOG「Nothing has been tagged or released yet.」、
公開/非公開の scope 列挙、非公式であることの明示）。一方、参照元が2026-08-12以降に
獲得した事実のうち2件は要約に反映が必要だったため「全体の形」に追記した。

- `jori-*` スキーマ識別子が互換契約の一部であり改名が破壊的変更であること、名称の
  記録先を `NOTICE` が列挙すること（出所: `ARCHITECTURE_BOUNDARY.md` の Naming、2026-08-15改訂）
- 権利情報を取得経路から推定せず、`jlegal compile --rights` の明示宣言時だけ記録すること
  （出所: `README.md` の e-Gov acquisition provenance、2026-08-12改訂）

`generated` を実際の改訂者・改訂時刻へ更新した。`status: draft` / `verified: []` は
変更していない（人間による確認は未了）。`okflint validate` は0エラー。

**Update** — 版表記・リリース状態の再掲解消（`sprightly-hatching-token.md` 変更セットA）に伴い、
`README.md`（`## Versioning` 節を新設）と `CHANGELOG.md`（バージョニング規約の明確化、
「タグ／リリース無し」の再掲文3箇所の恒久表現への書き換え、`--version`/`__version__` の
`### Added` 記録）を編集した。`project.md` の「現在地」も、`CHANGELOG.md` の文言を引用する形を
やめ、リリース状態の正本が `CHANGELOG.md` であることを指すだけの記述へ書き直した
（引用の再掲そのものが `okf-knowledge` の複製禁止に触れるため）。

`okf_freshness.py` が検出した `SOURCE-DRIFT` 2件（`README.md` 08-12→08-16、
`CHANGELOG.md` 08-15→08-16）は、両ファイルを読み直し、`project.md` の要約が現行の内容と
矛盾しないことを確認したうえで `last_modified` を実ファイルへ合わせた。`generated` を
実際の改訂者・改訂時刻へ更新した。`status: draft` / `verified: []` は変更していない。
`okflint validate` / `audit` は0エラー、`okf_freshness.py` は本バンドルの新規 `SOURCE-DRIFT` 0件。
