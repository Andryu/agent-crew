# P1 maintenance実機canary（実設定適用前）

2026-09-21。P1修正8ファイル集合SHA-256 `64bf47ec06be57ae9d0582c01f74b8392ed9c7353eb89d1a0ee326791b4fd778`は親採用、仕様・品質ともAPPROVED。権限原本`config/codex/permissions.toml` SHA-256 `b6778934a2e620a4a2b1b7871b9a33f56202f418677894ffd83c0212badcf945`からmaintenance区画だけを起動時`-c`へ渡し、`codex sandbox -P maintenance`で検証した。従来の`--sandbox`は指定していない。外側sandboxでは`sandbox-exec`起動自体がos error 1になるため、外側の制約だけを外して内側のnamed profileを実機評価した。検査スクリプトは`/private/tmp/p1-maintenance-canary.py`、SHA-256 `ab23575e6986dde21fec729bddf127066342b4872bcb67534b1977fc1a26770b`。

| 項目 | 結果 |
|---|---|
| profile起動、無害な`true` | exit 0 |
| `~/.codex/config-composer`作成、`composer.lock`取得 | 成功 |
| private台帳dirで同内容の`atomic_write` | 成功 |
| private台帳dirと`~/.codex`のfilesystem | 同一 |
| composerが使う`~/.codex`直下の一時ファイル作成 | **errno 1で拒否**。置換前に停止 |
| global `config.toml` | before/after SHA-256とも`727e69a8c11a622173728c4c6168db6cfe747f8f36b8d82db4f4bfd220a1202b`。内容表示・置換なし |

副作用はprivate `~/.codex/config-composer/composer.lock`のみ。設定本文・秘密値は出力していない。この結果では現行composerのglobal更新経路は通らないため、**実global設定適用を停止**する。

親への限定案: global `config.toml`のatomic writeだけ、一時ファイル作成先を既にmaintenanceで許可されたprivate `~/.codex/config-composer`へ変更し、同一filesystemの`os.replace`を使う。既存の元bytes照合、mode、fsync、台帳pending/backup、symlink拒否を保持する。`~/.codex`親directory全体へのwrite追加は行わない。destinationへのrename権限はこの無置換canaryでは未検証なので、設計採用後に同一内容の限定検証を行う。P2新3イベントの実設定反映、fresh hooks/list、hook state、CLI E2Eもその後に進める。

[OpenAI DocsのPermissions](https://learn.chatgpt.com/docs/permissions)はnamed profileとlegacy sandbox設定の優先関係を説明する。実効結果は上記のローカルcanaryによる。

## 親採用版の同一bytes rename canaryと適用停止

2026-09-21。P1修正版8ファイル集合`74a2500030f3cbdc00e5ceb3c34c4ac8b594698d4788ef47277dbecc46fad79c`は仕様・品質ともAPPROVED。変更後のcomposer本体SHA-256は`7df9b053efc8c42af80ac9c51c2d37013518eabb1097d73ede84985bccace44a`。採用template SHA-256 `b6778934a2e620a4a2b1b7871b9a33f56202f418677894ffd83c0212badcf945`のmaintenance区画だけを起動限定の`-c`で渡し、`codex sandbox -P maintenance`を使用した。従来の`--sandbox`は指定しない。検査本体は`/private/tmp/p1-maintenance-rename-canary.py`（SHA-256 `350c2dc8441c6c308bb3d7df574a35cf88b3851cc75f8eb49d8b5c7790301af8`）。

外側sandbox内での起動はexit 71で止まり、実globalには到達しなかった。外側制約を外した同じ起動はexit 0。検査本体はcomposerの`_policy_temp_dir`で固定private tempを選び、`lock`下で元bytesを再照合して、変更した`atomic_write(target, locked, locked, temp_dir)`そのものを呼んだ。`atomic_write`は内部で書込直前bytes照合、元mode維持、temp fsync、atomic replaceを行う。private tempと対象親は同一filesystem。設定bytesの前後SHA-256はいずれも`4856f85e592d77d2323346e7b80e44481c8713a1a1b88c4de0909162da4dd70f`、modeは前後`0600`。親directory全体の権限追加、copy/直接上書きfallbackなし。設定本文は出力していない。

次のread-only previewは**停止**した。現在global設定には台帳なしの所有区画（top `approval_policy`、`approvals_reviewer`、`default_permissions`と`permissions.developer`）が既に存在し、composerは`台帳なしの所有権限区画があります`を返した。旧wealth markerなし、固定private台帳の対象ledgerなし、private JSON 0件。現在の所有区画は採用templateの所有区画と一致しない。global hashは上記canary時点から不変と再照合したが、**所有外保持を伴うpreviewは成立していない**。安全境界に従いglobal権限の実適用と後続の順次反映を停止し、親の所有権判断を待つ。

## 既存所有区画のread-only比較と判断案

現在のtop3は`approval_policy=on-request`、`approvals_reviewer=user`、`default_permissions=developer`で採用templateと一致。`permissions.developer`は`extends=:workspace`、workspace rootsの`.git`/`.agents`/`.codex` write、cache/npm/uv/Library Caches write、network enabledがtemplateと一致し、これら既存制約は保持可能。現在のdeveloperだけにあるwrite pathは`~/.codex/config.toml`、`~/.codex/AGENTS.md`、`~/.codex/rules`、`~/.codex/skills`、`~/.codex/agents`、`~/.agents/skills`、`~/.claude/settings.json`、`~/.claude/skills`、`~/.claude/agents`の9件。採用templateではこれらをdeveloperに置かず、明示保守のmaintenance側に置く。現在`permissions.maintenance`と`permissions.review`は不存在。既存developerの広いglobal writeとP1の役割分離が競合する。作成起源は不明として扱い、モデル/provider/MCP/認証の値は参照結果へ出さない。

親判断候補Aは**現在hash固定の明示adopt**。固定private台帳に元bytesを0600でbackupし、共通lock取得後の再読込・hash照合、台帳pending、所有区画だけの限定合成、所有外意味木一致、書込直前bytes照合、適用後確認を条件にする。既存9 writeのdeveloperからの除去は親が明示採用する差分であり、旧広権限を再導入する初回rollbackは拒否する設計が必要。独立反証では次の4点が追加条件となった: (1)保持する既存制約は次回通常applyでも維持し、未知keyの厳しさ推測やwrite和集合で自動採用しない。(2)markerなし初回adoptのrollback/recover方針を台帳へ独立記録し、before/after/不一致を検査して旧広権限を復活させない。(3)lock後に対象path、元hash、source hash、合成後区画hashを照合し、既存ledger/pendingがあればadopt拒否。hashを自動更新しない。(4)隔離fixtureの成功を実global完了と扱わない。現composerにadopt入口はなく、親設計判断・独立レビュー前に拡張実装しない。

候補Bは**isolated configでの起動限定適用**。別の設定領域またはCLI overrideで採用templateのprofileを使い、現在globalの所有区画を変更せず実効profileとhookの検証を進める。現在の個人global設定への恒久適用や単一composerの所有移管は完了しない。いずれも既存区画を無断で消す・上書きする回避策ではない。

cloneの共通hook manifestはCodexの`SessionStart`/`Stop`/`SubagentStop`の3件で、`.codex/hooks.json`は未作成。read-only合成は可能だが、installerの`--apply`はClaude設定と6件の互換shimにも変更を生成するため、今回は実生成を保留。新snapshotは3件生成後に新しいhooks/listを取得し、旧`UserPromptSubmit`や未知project hookを拒否する必要がある。global所有区画の判断前に行ったのはread-only準備確認のみ。
