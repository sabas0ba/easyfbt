# easyfbt

Webカメラ(1台以上)で全身の姿勢と表情をトラッキングし、SteamVR/OpenVR 用の仮想トラッカーと
VRCFT (VRCFaceTracking) 方式の表情パラメータを送出するツールです。

- **姿勢トラッキング**: MediaPipe Pose(33ランドマーク)→ 腰・胸・膝・足・肘の仮想トラッカー(位置+回転クォータニオン)
- **表情トラッキング**: MediaPipe Face Landmarker の ARKit 系 52 blendshapes → Unified Expressions へ変換
- **マルチカメラ**: 複数の `[[camera]]` を設定すると、ランドマークごとの可視性で重み付け融合
- **デバッグ画面**: スケルトンオーバーレイ・表情バー・トラッカー座標・FPS を表示(`q` で終了)
- **出力先**(同時併用可):

  | 出力 | プロトコル | 用途 |
  |---|---|---|
  | `output.vmt` | OSC `/VMT/Room/Unity`(port 39570) | [VMT (Virtual Motion Tracker)](https://github.com/gpsnmeajp/VirtualMotionTracker) ドライバ経由で **SteamVR/OpenVR に仮想トラッカーを追加** |
  | `output.vrchat` | OSC `/tracking/trackers/{1..8}/…`(port 9000) | VRChat ネイティブOSCトラッカー(SteamVR不要) |
  | `output.vrcft` | OSC `/avatar/parameters/v2/<Shape>` + `/tracking/eye/CenterPitchYaw` | **VRCFT方式**の Unified Expressions パラメータ送出(プレフィックス/ポート変更で VRCFT モジュールへの給餌にも) |
  | `output.udp_json` | UDP JSON(1データグラム=1フレーム) | 任意の外部プログラム向け汎用データインターフェース |

## アーキテクチャ

```
カメラ(スレッド) ──> 最新フレーム ──> Pose/Face バックエンド (MediaPipe Tasks)
      │ (台数分)                          │
      └──────────────> 部屋座標系へ変換 ──> マルチカメラ融合 (可視性重み付け)
                                           │
                            One Euro フィルタで平滑化
                                           │
              ┌────────────────────────────┼───────────────────────┐
        スケルトン→トラッカー変換    ARKit→Unified Expressions   デバッグ画面
              │                            │
      VMT / VRChat OSC 出力         VRCFT 方式 OSC 出力        UDP JSON 出力
```

- 座標系: 部屋空間は SteamVR 準拠(右手系・+Y上・メートル)。VMT/VRChat 送出時に Unity 左手系へ変換。
- v0.1 では腰位置を `user_height * 0.53` の高さに固定アンカーします(単眼カメラでは絶対深度が
  取れないため)。VRChat / VMT 側のキャリブレーションで吸収されます。ルームスケール移動の推定は今後の課題です。
- 重い CV 依存(mediapipe / opencv)は `backends/` と `capture.py` に隔離してあり、
  コアロジックは numpy と標準ライブラリのみで動作・テストできます(OSC エンコーダも自前実装で依存を削減)。

## セットアップ

Python 3.11 以上。

```bash
# 1) 依存関係をハッシュ検証付きでインストール
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install --require-hashes -r requirements/runtime.lock

# 2) モデルを取得(SHA-256 検証付き・バージョン固定URL)
python tools/fetch_models.py

# 3) 設定を作成して実行
cp config.example.toml config.toml
python -m easyfbt --config config.toml
```

カメラ列挙: `python -m easyfbt --list-cameras` / デバッグ画面なし: `--no-window`

### SteamVR に仮想トラッカーを出すには (VMT)

1. [VMT](https://github.com/gpsnmeajp/VirtualMotionTracker) を SteamVR にインストールし、ルームキャリブレーションを実施
2. `config.toml` で `[output.vmt] enabled = true`
3. easyfbt を起動すると、トラッカー index 1〜8(腰=1、左右足=2/3、左右膝=4/5、胸=6、左右肘=7/8)が VMT 経由で SteamVR に現れます

### VRChat だけで使う場合(SteamVR不要)

`[output.vrchat] enabled = true`(既定)。VRChat 内の OSC Trackers キャリブレーションを実行してください。
表情は `[output.vrcft]` が `/avatar/parameters/v2/<UnifiedExpressions名>` の float を直接送ります
(アバターが UE の float パラメータを持つ場合に動作。VRCFT 本体のモジュールに食わせたい場合は
`address_prefix` と `port` を受信側に合わせてください。バイナリパック化パラメータや
アバターOSC設定のネゴシエーションは対象外です)。

### 複数カメラ

`config.example.toml` の 2 台目の例を参照。各カメラの部屋内位置 `position` と向き `yaw_deg` を
設定すると、ランドマーク単位の可視性重みで融合され、オクルージョンに強くなります。

## UDP JSON データインターフェース

`[output.udp_json] enabled = true` で 1 フレームごとに以下の JSON が届きます:

```json
{"v": 1, "t": 12.5, "fps": 29.7,
 "trackers": [{"role": "hip", "index": 1, "pos": [0.0, 0.9, 0.0], "rot": [0.0, 0.0, 0.0, 1.0]}],
 "expressions": {"JawOpen": 0.12},
 "eyes": {"pitch": 0.0, "yaw": 0.0}}
```

`pos` は部屋空間(右手系, +Y上, m)、`rot` はクォータニオン `[x, y, z, w]` です。

## 開発・テスト

```bash
pip install --require-hashes -r requirements/ci.lock
python -m pytest --cov          # 純ロジック単体テスト + ループバックUDP統合テスト
ruff check . && ruff format --check .
```

- カメラや mediapipe を使わずに全パイプラインをテストできるよう、フレームソース・バックエンド・
  出力・クロックをすべて注入可能にしています(`tests/test_app_integration.py` 参照)。
- OSC はエンコード結果をゴールデンバイト列とデコーダで検証、Unity 座標変換・オイラー角は往復テストで検証。
- CI (GitHub Actions) は lint + Python 3.11/3.12 のテストマトリクス + 実モデル e2e を実行し、カバレッジ 85% 未満で失敗します。

### ゴールデンサンプルテスト

台本化した決定論的なセッション(体のヨー回転+腕上げ+表情変化、固定クロック)を実パイプラインに流し、
**4出力すべての全パケット**(VMT / VRChat / VRCFT の OSC をデコードしたもの + UDP JSON)を
`tests/golden/scripted_session.json` と照合します。出力仕様を意図的に変えた場合は:

```bash
pytest tests/test_golden_outputs.py --update-goldens   # ゴールデンを再生成して差分をレビュー
```

### e2e テスト(実モデル・実画像)

実際の MediaPipe モデルとハッシュ検証済みのテスト画像で、システムとしての機能性を検証します:

```bash
pip install --require-hashes -r requirements/runtime.lock
python tools/fetch_models.py        # モデル(SHA-256 検証)
python tools/fetch_test_assets.py   # テスト画像(SHA-256 検証)
pytest -m e2e                       # 通常の pytest 実行からは除外されています
```

検証内容: 笑顔のポートレートから `MouthCornerPull* > 0.5` 等のもっともらしい表情パラメータが出ること、
上半身のみの画像で脚のトラッカーが可視性ゲーティングで正しく除外されること(hip/chest/肘のみ出力)、
OSC パケットの整形式性、および最終フレームの UDP JSON を許容誤差付きゴールデン
`tests/e2e/golden/portrait_session.json` と照合(モデル推論は CPU により微差が出るため tol=0.05)。
再生成は `pytest -m e2e --update-goldens`。

## セキュリティ / サプライチェーン

- **依存関係は最小限**: 実行時は `mediapipe` / `opencv-python` / `numpy` のみ(OSC・設定・UDP は標準ライブラリで自前実装)。開発用も `pytest` / `pytest-cov` / `ruff` のみ。
- **SHA ピン留めを必須化**:
  - Python 依存は `requirements/*.lock` に全配布ファイルの SHA-256 を記録し、`pip --require-hashes` でのみインストール(ロックは `tools/gen_lock.py` で再生成)
  - GitHub Actions は**フルコミットSHA**でピン留め(Dependabot が SHA ごと更新)
  - ML モデルはバージョン固定 URL + SHA-256 検証付きダウンロード(`tools/fetch_models.py`)。実行時の暗黙ダウンロードなし
- CI の `GITHUB_TOKEN` は `contents: read` のみ、checkout は `persist-credentials: false`
- ネットワーク送信は既定で `127.0.0.1` 宛の UDP のみ

## 既知の制限 / ロードマップ

- ルームスケール移動(体全体の平行移動)は未推定(腰アンカー固定)
- マルチカメラは向きの融合のみで、外部パラメータの自動キャリブレーションは未実装
- VRCFT のバイナリパックパラメータ / アバターOSC設定ネゴシエーションは未対応
- 手指トラッキングは未対応

## ライセンス

[Apache License 2.0](LICENSE)
