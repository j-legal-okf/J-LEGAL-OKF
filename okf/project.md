---
type: Project
title: J-LEGAL-OKF / JORI Engine
description: Source-preserving Japanese national-law knowledge tooling with JORI Engine as the public reference implementation.
resource: https://github.com/j-legal-okf/J-LEGAL-OKF
tags: [jlegal-okf, japanese-law, source-preservation, public-core]
status: draft
sources:
  - resource: ../README.md
    title: README.md
    last_modified: 2026-08-12
  - resource: ../ARCHITECTURE_BOUNDARY.md
    title: ARCHITECTURE_BOUNDARY.md
    last_modified: 2026-08-15
  - resource: ../docs/jlegal-okf-profile-0.1.0-draft.md
    title: J-LEGAL-OKF Profile 0.1.0-draft
    last_modified: 2026-08-12
  - resource: ../docs/oss-release/scope-inventory.md
    title: Public scope inventory
    last_modified: 2026-08-11
  - resource: ../CHANGELOG.md
    title: CHANGELOG.md
    last_modified: 2026-08-15
generated:
  by: anthropic/claude-opus-5
  at: 2026-08-16T08:30:41+09:00
verified: []
stale_after: 2026-10-31
---

# 現在地

公開候補の README、規範プロファイル、アーキテクチャ境界、scope inventory が、
J-LEGAL-OKF の公開コア契約と除外範囲を定義する。本バンドルはその概要だけを保持し、
実装仕様・手順・進捗を複製しない。CHANGELOG.md は「まだ何もタグ付け・リリースされて
いない」と記録し、README.md はこの初期スライスを「完全なリリースではない」と明記する。

# 何のためにあるか

J-LEGAL-OKF は、日本の国法令に対して、原典を保持し、構造と出典を追跡でき、
同じ入力から同じ正準成果物を再生成できる知識ツールの公開ドラフト・コアである。
JORI Engine はこの公開コアの参照実装であり、`jlegal_okf` パッケージと `jlegal` CLI
を提供する。

成功条件は、公開された入力・仕様・コード・合成fixtureだけで、正準コーパス、manifest、
検証診断、OKF v0.2-shaped exportを第三者が再現・検証できることである。

# スコープ境界

公開コアに含めるもの:

- `jori-corpus/v1` の正準モデル、決定論的ID・hash・manifest処理、crosswalkのシリアライズ、retrieval projection
- validator診断、generic JSON/XML/XHTML adapter
- 保存済みe-Gov国法令XMLの変換と明示的なfetch helper
- OKF v0.2-shaped export/validation
- `jlegal` CLI、合成fixture、offline回帰テスト

公開コアに含めないもの:

- LLM実行、audition、enrichment、provider統合
- OCR、自治体条例、判例、法解釈・法的助言
- Akoma Ntoso出力、index/search/evaluation、benchmark corpus
- 実法令スナップショット、非公開資料、運用設定、秘密値

J-LEGAL-OKFは非公式のプロジェクトであり、政府・e-Gov・OKFの公式承認、法的助言、
法的正確性の保証を主張しない。

# 全体の形

公開入力をadapterで読み込み、正準モデルへ決定論的に変換する。corpusとmanifestは
入力hash・構造・変換証跡を保持し、validatorは安定した診断として不正な入力を
fail-closedで報告する。exporterはsource、canonical、derivedの層を分離した
OKF v0.2-shaped bundleを生成する。

`jori-corpus/v1` をはじめとする `jori-*` スキーマ識別子は互換契約の一部であり、
改名は編集ではなく破壊的変更である。`JORI Engine` の名称が記録される場所は
[NOTICE](../NOTICE) が列挙し、実装・フォーマット識別子としての使用に留めて商標・
ブランドの主張はしない（[ARCHITECTURE_BOUNDARY.md](../ARCHITECTURE_BOUNDARY.md) の Naming）。

権利情報は取得経路から推定しない。e-Gov APIの受領証は `rights: null` を持ち、
権利表明は `jlegal compile --rights` で明示的に宣言した場合だけ記録される
（[README.md](../README.md)）。

公開コアは公開された仕様、コード、合成fixtureだけで検証できることを境界原則とする。
取得済みデータの再配布、利用者固有の設定、非決定的なモデル出力、運用情報、および
取得済みコーパスや顧客資料に由来する評価データは公開コアの対象外である。評価であること
自体は非公開の理由にならず、合成fixtureと固定期待値による決定論的な評価は他の成果物と
同じ基準で判断する。

# 流動情報の在り処

| 知りたいこと | 正本 |
|---|---|
| 公開コアの利用手順とoffline例 | [README.md](../README.md) |
| v0.1の規範プロファイル | [docs/jlegal-okf-profile-0.1.0-draft.md](../docs/jlegal-okf-profile-0.1.0-draft.md) |
| 公開／非公開の判定原則 | [ARCHITECTURE_BOUNDARY.md](../ARCHITECTURE_BOUNDARY.md) |
| 移植対象と除外対象 | [docs/oss-release/scope-inventory.md](../docs/oss-release/scope-inventory.md) |
| 変更履歴 | [CHANGELOG.md](../CHANGELOG.md) |

このバンドルは進捗、タスク、実行ログ、数値実績を管理しない。

# 関連

公開コアの仕様・コード・fixture・回帰テストは、このリポジトリを正本とする。
非公開入力、個別設定、秘密、個人情報は公開OKFの対象に含めない。
