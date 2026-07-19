# プロパティ定義ガイド（PropertyType / RPGPropertyType）

このドキュメントは、RPG-Cobo のプロパティ定義テーブルの書き方をまとめたものです。

RPG-Cobo のプロパティ定義は、`PropertyType` または `RPGPropertyType` の型を使って、各プロパティの保存キー、ラベル、型、デフォルト値などを定義するテーブルです。
（*定数値については、 [list_constants.md](list_constants.md) を参照してください。*）

プロパティ定義は、 キャラのステータス、スキル、アイテム、システム設定、更にイベントコマンドのパラメータ定義、プラグインのオプション設定に至るまで、さまざまなデータ構造に利用される、非常に重要な仕組みです。  
基本的には配列で複数のプロパティ定義が定義されています。


## 1. プロパティ定義テーブルの書き方

RPG-Cobo のプロパティは、`table` で 1 項目ずつ定義します。  
基本的には以下の形です。

```sk
import PropertyType;		//	定数を省略して使う場合はimport。
import RPGPropertyType;

local someprop = {
	pid = "keyname",		// 保存キー
	lbl = "$T.some_label",	// エディタ表示ラベル
	type = SCALAR,			// PropertyType / RPGPropertyType
	defval = 1,				// デフォルト値
};
```

複数項目を使う場合は、まず選択肢などの共通データを定義し、その後に各プロパティを定義します。  
LIST と SCALAR の典型例は次のとおりです。

```sk
local valtypes = (
);

// リスト選択のプロパティ定義例
local valtypeprop = {
	pid = "valtype",
	lbl = "$T.lbl_type",
	type = LIST,
	list = [	//	list要素は 文字列配列、{lbl,val,{icon}} 配列、またはクロージャで定義可能
		{ val:"base", lbl:"$T.val_base" },
		{ val:"baserate", lbl:"$T.val_baserate" },
		{ val:"supply", lbl:"$T.val_supply" },
		{ val:"totalrate", lbl:"$T.val_totalrate" },
	],
	defval = "supply",	//	list内の val に対応した値
};

// 数値指定のプロパティ定義例
local valprop = {
	pid = "val",
	lbl = "$T.lbl_amount",
	type = SCALAR,
	range = (-9999,9999),
	defval = 5,
};
```

この例のポイント:

- `LIST` の場合
	- `list` に候補を渡します（`{lbl,val}` の配列/tuple が基本）。
	- `defval` は候補の `val` と同じ型で指定します（ここでは文字列）。

- `SCALAR` の場合
	- `range` で入力範囲を制限します。
	- `defval` は数値で指定します。

- 共通
	- `pid` は保存キーなので重複しない名前にします。
	- `lbl` は翻訳キーを使うのが基本です。 `{ja:"音", en:"Sound"}` のように直接 table で言語毎の文言を書くことも可能です。
	- `type` によってプロパティ定義に必要な追加キー（`list`, `range` など）が変わります。

---

## 2. プロパティ定義の共通仕様

### 2.1 基本キー

- `pid`（必須）
	- データ保存先キー。
	- デフォルトでは `data[pid]` に読み書きされます。

- `lbl`（必須）
	- エディタに表示するラベル。
	- 例: `$T.lbl_sound`, `{ja:"音", en:"Sound"}` など。

- `type`（必須）
	- `PropertyType` または `RPGPropertyType` の定数。

- `defval`（推奨）
	- 未設定時に補完するデフォルト値。
	- `setDefaultProperties()` で適用されます。

- `cnt`（任意）
	- プロパティ行コンテナ UI。レイアウト調整用。
	- 未指定時は `cnt.ui`。

- `variable`（任意）
	- 変数リンク UI を表示するためのフラグ。0|1|2を指定。
	- イベントコマンドでのみ使用可能。

### 2.2 共通でよく使うキー

- `range=(min,max)` : 数値入力の範囲指定。
- `q` : 数値入力のステップ（量子化）。
- `list` : 選択肢リスト。文字列配列、`{lbl,val}` 配列、またはクロージャ。
- `multiline` : 複数行テキストの行数。
- `nullable` : `null` を許可する。`null` は未指定扱い。
- `hide=@(pl)...` : 条件非表示。
- `refresh=1` : 値変更時に UI を再構築。
- `get` / `set` : データアクセスのカスタム。
- `anime` : tween キー UI を有効化。

---

## 3. PropertyType（proptype 実装あり）

### SCALAR（1）

- 値の型: 数値（`int` / `float`）
- 主な追加キー:
	- `range`: 入力可能最小値と最大値。
	- `q`: 入力ステップ。`q=10` なら 0.1 単位入力に相当する運用が可能。
	- `ui`: `"bar"` の場合、バー付き UI を使う。
	- `dynamic`: `VALUE_CHANGED` で即時反映する。

### VEC2（2）

- 値の型: 2要素数値配列/tuple
- 主な追加キー:
	- `range`: 各軸の範囲。単一範囲または軸別範囲を指定可能。
	- `q`: 入力ステップ。
	- `ui`: 表示形式切り替え（例: `"r"`）。

### VEC3（3）

- 値の型: 3要素数値配列/tuple
- 主な追加キー:
	- `range`: 各軸の範囲。
	- `q`: 入力ステップ。
	- `ui`: `"bar"` を指定するとバー UI 系を選択。

### STRING（4）

- 値の型: 文字列
- 主な追加キー:
	- `multiline`: 複数行編集を有効化し、表示行数を調整。
	- `format`: 入力値整形関数。
	- `deflbl`: 未入力時ガイド文言。

### BOOL（5）

- 値の型: `bool`
- 主な追加キー:
	- `boollbl`: OFF/ON 側の表示ラベルを差し替える。

### LIST（6）

- 値の型: 選択項目の `val`
- 主な追加キー:
	- `list`: 選択肢定義。`["0:OFF", ...]` または `[{lbl,val}, ...]`。
	- `list` はクロージャにもでき、他プロパティ値に応じて動的生成可能。

### RGB（7）

- 値の型: 色整数
- 主な追加キー:
	- 追加キーは基本不要（UI 側で RGB 入力として扱う）。

### RGBA（8）

- 値の型: 色整数（RGBA）
- 主な追加キー:
	- 追加キーは基本不要（UI 側で alpha 入力を含む）。

### PATH（9）

- 値の型: パス文字列
- 主な追加キー:
	- `abspath`: 絶対/相対の扱いを呼び先選択ダイアログで参照。
	- `filter`: 開ける拡張子の絞り込みを呼び先で参照。

### LANGSTRING（11）

- 値の型: `{ja:"...", en:"..."}` のような言語別 table、または `null`
- 主な追加キー:
	- 追加キーは基本不要（言語切替 UI は型側実装）。

### CHECKBITS（13）

- 値の型: `int` または `int[]`
- 主な追加キー:
	- `list`: ビット項目定義。`idx` を明示するとビット位置を固定可能。
	- `hidelisticon`: ポップアップ項目のアイコン表示を抑制。

### PROPERTYLIST（14）

- 値の型: table
- 主な追加キー:
	- `propdef`: 内包プロパティ定義本体。
	- `propdef.props`: 内包する子プロパティ配列。
	- `propdef.tostring`: 一覧表示用の文字列化関数。

### SCRIPT（15）

- 値の型: スクリプト文字列
- 主な追加キー:
	- `multiline`: 編集欄の高さ調整。

### CUSTOMBUTTON（16）

- 値の型: 任意
- 主な追加キー:
	- `edit`: 編集処理関数。戻り値を新値として適用。
	- `tostring`: ボタン表示文言の文字列化関数。
	- `icon`: 表示アイコン。
	- `ui`: ボタン用 UI バリエーション指定。

### BOOL1（17）

- 値の型: `bool`
- 主な追加キー:
	- 追加キーは基本不要（省スペース表示型）。

### ROT_HEAD（18）

- 値の型: 数値（角度）
- 主な追加キー:
	- `range`: 角度範囲。
	- `q`: 角度入力ステップ。

### ROT_HPB（19）

- 値の型: 3要素角度配列（HPB）
- 主な追加キー:
	- `range`: 各軸角度範囲。
	- `q`: 入力ステップ。

### TEXTSTYLE（100）

- 値の型: フォント属性 table
- 主な追加キー:
	- 追加キーは基本不要（型側が必要項目を固定で編集）。

### STRETCH（101）

- 値の型: `null` または `[left, up, right, down, punch]`
- 主な追加キー:
	- 追加キーは基本不要（型側で範囲と構造を持つ）。

### ALIGN_STRETCH（103）

- 値の型: ビットフラグ整数
- 主な追加キー:
	- 追加キーは基本不要（型側で配置ビットを編集）。

### VEC2_PIVOT（104）

- 値の型: 2要素数値配列
- 主な追加キー:
	- `range`: 値範囲。
	- `q`: 入力ステップ。

### PATHLIST（105）

- 値の型: パス文字列配列
- 主な追加キー:
	- 追加キーは基本不要（型側で件数と DnD 編集を提供）。

### CAMERA（106）

- 値の型: `SK3DCameraData` または `null`
- 主な追加キー:
	- 追加キーは基本不要（位置・角度・fov 等を型側 UI で編集）。

### SOUNDID（107）

- 値の型: サウンド ID 文字列
- 主な追加キー:
	- 追加キーは基本不要（型側でカテゴリ/ID 選択ポップアップを処理）。

### BIT8（202）

- 値の型: 8bit 整数
- 主な追加キー:
	- 追加キーは基本不要（8 トグル固定 UI）。

### FILEPATH（203）

- 値の型: ファイルパス文字列
- 主な追加キー:
	- `abspath`: 絶対/相対の扱い。
	- `filter`: 選択可能拡張子フィルタ。

---

## 3. RPGPropertyType（proptype 実装あり）

### NAME_ICON（1001）

- 値の型: `[name, icon]`
- 主な追加キー:
	- `icontype`: アイコン選択元カテゴリ。

### LIST_SCALAR（1002）

- 値の型: `[selectedVal, scalar]`
- 主な追加キー:
	- `list`: 選択候補。
	- `range`: 数値側の範囲。
	- `q`: 数値側のステップ。

### DATAID（1003）

- 値の型: データ ID 文字列（または `"ID,num"`）
- 主な追加キー:
	- `datatype`: 選択対象データ種別。
	- `inputnum`: `"ID,num"` 形式を扱うかどうか。
	- `nullable`: 未設定を許可。

### DATAIDS（1004）

- 値の型: データ ID 配列
- 主な追加キー:
	- `datalist`: 行見出しや選択条件の定義配列。

### RESID（1005）

- 値の型: リソース ID 文字列または `null`
- 主な追加キー:
	- `restype`: 許可するリソース種別。
	- `nullable`: 未設定を許可。

### RESID_PREVIEW（1006）

- 値の型: リソース ID 文字列または `null`
- 主な追加キー:
	- `restype`: 選択対象リソース種別。
	- `nullable`: 未設定を許可。
	- `size`: プレビュー UI サイズ種別。

### VARIABLE（1007）

- 値の型: VariableBehavior 形式の値
- 主な追加キー:
	- `constbits`: 定数入力として許可する型ビット。
	- `varbits`: 変数参照として許可する型ビット。
	- `unlinkmenu`: 変数リンク解除メニュー制御。

### REQUIREMENTS（1008）

- 値の型: 要件配列 table
- 主な追加キー:
	- `varbits`: 要件内で許可する変数型制約に利用。

### EXPCURVE（1009）

- 値の型: 経験値カーブ table/tuple（例: `(base,gain)`）
- 主な追加キー:
	- `defval`: 初期カーブ値。

### PORTAL（1012）

- 値の型: 例: `{mapid="M000", evid="..."}` または `{mapid="M000", pos=(x,y,z,dir)}`
- 主な追加キー:
	- 追加キーは基本不要（型側でマップ/イベント/座標編集 UI を提供）。

### GRAPHIC（1013）

- 値の型: リソースパス文字列または `null`
- 主な追加キー:
	- `nullable`: 未設定を許可する運用を明示するために付与可能。

### VOXEL_PARTS（1014）

- 値の型: `(voxpath, partsid)` または `null`
- 主な追加キー:
	- `usevcname`: voxel 参照をパスではなく VC 名で扱う。

### PALETTEMAP（1015）

- 値の型: パレット配列（`[idx,col,...]`）
- 主な追加キー:
	- `inipal`: リセット時に戻す初期パレット。
	- `palchange`: 編集中プレビュー用の反映コールバック。

### MESSAGE（1016）

- 値の型: メッセージ文字列
- 主な追加キー:
	- `multiline`: 編集欄の行数。

### ENEMYGROUP（1017）

- 値の型: 配置配列（例: `[{id="E001",x=...,z=...}, ...]`）
- 主な追加キー:
	- 追加キーは基本不要（型側で配置 UI を提供）。

### GAMETITLE（1018）

- 値の型: `(title, appname, iconImage)`
- 主な追加キー:
	- 追加キーは基本不要。

### UIPOSITION（1019）

- 値の型: 位置 table（`x/left/right`, `y/up/down`）
- 主な追加キー:
	- 追加キーは基本不要（型側で軸アンカー方式を編集）。

### ANIME_INLINE（1020）

- 値の型: アニメ設定 table
- 主な追加キー:
	- `mdlid`: 対象モデルを固定指定。

### ANIME_POPUP（1021）

- 値の型: アニメ設定 table
- 主な追加キー:
	- `mdlid`: 対象モデルを固定指定。
	- `nullable`: 未設定を許可。

### ANIMEMAP（1023）

- 値の型: アニメ設定配列
- 主な追加キー:
	- 追加キーは基本不要（型側で add/edit/reorder を提供）。

### PLACEASSET（1024）

- 値の型: `{resid, pos=[x,y,z,dir], blend}`
- 主な追加キー:
	- 追加キーは基本不要（型側で 3D 配置 UI を提供）。

---

## 4. OptionTypes 形式のサンプル

### RESID

```sk
{ pid="snd", lbl="$T.lbl_sound", type=RESID, restype=["snd"], defval=null, nullable=true, }
```

### DATAID

```sk
{ pid="skillid", lbl="$T.lbl_skill", type=DATAID, datatype=["skill"], defval="S000" }
```

### VARIABLE

```sk
{ pid="rate", lbl="$T.lbl_userate", type=VARIABLE, constbits=2|8|16, varbits=0, defval=1.0 }
```

### CHECKBITS

```sk
{ pid="flagbits", lbl="$T.lbl_flags", type=CHECKBITS, list=sealflaglist, defval=0 }
```

### PROPERTYLIST

```sk
{
	pid="hitact",
	lbl="$T.lbl_hitact",
	type=PROPERTYLIST,
	propdef={
		name="$T.lbl_hitact",
		props=[
			{ pid="hitani", lbl="$T.lbl_anime", type=ANIME_POPUP, nullable=true },
			{ pid="hitefx", lbl="$T.lbl_effect", type=RESID, restype="efx", nullable=true },
			{ pid="hitsnd", lbl="$T.lbl_sound", type=RESID, restype=["snd"], nullable=true },
		],
		tostring=@(v) ((v["hitani"]||v["hitefx"]||v["hitsnd"]) ? sprintf("%S %S %S", v["hitani"]["id"]||"", v["hitefx"]||"", v["hitsnd"]||"") : "$T.lbl_notset"),
	},
	defval={ hitani=null, hitefx=null, hitsnd=null },
}
```

## 5. get / set キーによる値取得・設定のカスタマイズ

プロパティ定義は、以下のように `get` / `set` キーを使って、データアクセスのカスタマイズが可能です。

```
{
	...
	get = @(prop, data) (data[prop.pid] || 0),			// データが未設定の場合は 0 を返す
	set = @(prop, data, val) (data[prop.pid] <- val),	// <- 演算子でキーが存在しない場合は追加される
}
```

## 6. variable 指定でイベントコマンドを柔軟に

イベントコマンドなどの一部のプロパティ定義では、`variable` キーを指定することで、変数リンク UI を表示し、変数参照や定数入力を柔軟に切り替えることができます。

例えば、「ウェイト」コマンドは、指定した時間を待つコマンドですが、`variable=1` を指定することで、定数値だけでなく変数参照や計算式も指定可能になります。以下の定義を見てみましょう (`EventCommands.sk`)。

```
//	cmd_wait : 指定した秒数（スクリプト可）ウェイトを入れる。〇
{
	...
	props = [
		{ pid="time", lbl="$T.lbl_time", type=SCALAR, range=(0,100000), ui="bar", barrange=(0,3000,20), variable=1, },
	]
	...
	exec = @( runner, cmd){
		sleep( cmd.time);
	}
}
```

- `time` プロパティは、`variable=1` が指定されているため、ユーザーは定数値を直接入力することも、変数を参照して値を取得することもできます。
- `exec` でコマンドが実行される際に、 `cmd.time` は変数参照の場合はその変数の値が入ってきます。
- `variable=2` を指定すると、変数参照のみが可能になり、定数値の入力はできなくなります。
