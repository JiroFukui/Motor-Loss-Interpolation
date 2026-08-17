import streamlit as st
import pandas as pd
import numpy as np
from scipy.interpolate import RectBivariateSpline
import plotly.graph_objects as go
import io

st.set_page_config(page_title="モータ損失データ補間アプリ", layout="wide")

st.title("モータ損失データ補間アプリ")
st.markdown("異なる刻み方のモータに対して損失データを補間します")

# サイドバーで設定
st.sidebar.header("設定")

# ステップ1: 元データのアップロード
st.header("1. 元の損失データをアップロード")
st.markdown("**対応形式**: CSV (.csv) または Excel (.xlsx, .xls)")

# データ形式の選択
data_format = st.radio(
    "データ形式を選択してください",
    ["リスト形式（3列）", "マトリックス形式（損失マップ）"],
    help="リスト形式: 1列目=回転数, 2列目=トルク, 3列目=損失\nマトリックス形式: 縦軸=トルク, 横軸=回転数, セル=損失"
)

uploaded_file = st.file_uploader("ファイルを選択", type=['csv', 'xlsx', 'xls'])

if uploaded_file is not None:
    try:
        # ファイル形式の判定と読み込み
        file_extension = uploaded_file.name.split('.')[-1].lower()

        if file_extension == 'csv':
            df = pd.read_csv(uploaded_file)
        elif file_extension in ['xlsx', 'xls']:
            # Excelファイルの読み込み
            excel_file = pd.ExcelFile(uploaded_file)

            # シートが複数ある場合は選択させる
            if len(excel_file.sheet_names) > 1:
                sheet_name = st.selectbox(
                    "シートを選択してください",
                    excel_file.sheet_names
                )
            else:
                sheet_name = excel_file.sheet_names[0]

            df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
            st.info(f"読み込んだシート: {sheet_name}")
        else:
            st.error("対応していないファイル形式です")
            df = None

        if df is None:
            pass
        else:
            # データ形式に応じた処理
            if data_format == "リスト形式（3列）":
                # リスト形式の処理
                if len(df.columns) < 3:
                    st.error("ファイルには少なくとも3列（回転数、トルク、損失）が必要です")
                    df = None
                else:
                    # 列名を標準化
                    df.columns = ['回転数_rpm', 'トルク_Nm', '損失_Wh'] + list(df.columns[3:])
                    st.success(f"データを読み込みました: {len(df)}行")
                    st.dataframe(df.head(10))

            else:  # マトリックス形式
                st.info("マトリックス形式として読み込みます")

                # 1行目を回転数として使用（ヘッダー）
                # 1列目をトルクとして使用（インデックス）

                try:
                    # データフレームの1行目が回転数、1列目がトルク
                    matrix_df = df.copy()

                    # ヘッダーとインデックスの処理
                    if matrix_df.iloc[0, 0] == matrix_df.columns[0] or pd.isna(matrix_df.iloc[0, 0]) or matrix_df.iloc[0, 0] == '':
                        # 左上のセルが空白または重複している場合
                        rpm_values = matrix_df.iloc[0, 1:].values
                        torque_values = matrix_df.iloc[1:, 0].values
                        loss_matrix = matrix_df.iloc[1:, 1:].values
                    else:
                        # 1行目と1列目がそのままデータの場合
                        rpm_values = matrix_df.columns[1:]
                        torque_values = matrix_df.iloc[:, 0].values
                        loss_matrix = matrix_df.iloc[:, 1:].values

                    # 数値に変換
                    rpm_values = pd.to_numeric(rpm_values, errors='coerce')
                    torque_values = pd.to_numeric(torque_values, errors='coerce')
                    loss_matrix = pd.DataFrame(loss_matrix).apply(pd.to_numeric, errors='coerce').values

                    # NaN値のチェック
                    if np.isnan(rpm_values).any() or np.isnan(torque_values).any():
                        st.error("回転数またはトルクの値に数値以外のデータが含まれています")
                        df = None
                    else:
                        # マトリックス形式を表示
                        st.write("読み込んだマトリックス（損失マップ）:")
                        display_matrix = pd.DataFrame(
                            loss_matrix,
                            index=[f"{t:.1f}" for t in torque_values],
                            columns=[f"{r:.0f}" for r in rpm_values]
                        )
                        display_matrix.index.name = "トルク[Nm]"
                        display_matrix.columns.name = "回転数[rpm]"
                        st.dataframe(display_matrix)

                        # リスト形式に変換
                        data_list = []
                        for i, torque in enumerate(torque_values):
                            for j, rpm in enumerate(rpm_values):
                                if not np.isnan(loss_matrix[i, j]):
                                    data_list.append({
                                        '回転数_rpm': rpm,
                                        'トルク_Nm': torque,
                                        '損失_Wh': loss_matrix[i, j]
                                    })

                        df = pd.DataFrame(data_list)
                        st.success(f"マトリックスからリスト形式に変換しました: {len(df)}行")

                except Exception as e:
                    st.error(f"マトリックス形式の読み込みに失敗しました: {str(e)}")
                    st.info("ヒント: 1行目に回転数、1列目にトルク、セル内に損失値を配置してください")
                    df = None

        if df is not None and len(df) > 0:

            # 元データの範囲を表示
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("回転数範囲", f"{df['回転数_rpm'].min():.0f} - {df['回転数_rpm'].max():.0f} rpm")
            with col2:
                st.metric("トルク範囲", f"{df['トルク_Nm'].min():.2f} - {df['トルク_Nm'].max():.2f} Nm")
            with col3:
                st.metric("損失範囲", f"{df['損失_Wh'].min():.2f} - {df['損失_Wh'].max():.2f} Wh")

            # 元データの可視化
            st.subheader("元データの可視化")

            # グリッドデータの作成（ピボット）
            pivot_df = df.pivot_table(
                values='損失_Wh',
                index='トルク_Nm',
                columns='回転数_rpm',
                aggfunc='mean'
            )

            fig_original = go.Figure(data=go.Heatmap(
                z=pivot_df.values,
                x=pivot_df.columns,
                y=pivot_df.index,
                colorscale='RdYlBu_r',
                colorbar=dict(title="損失 [Wh]")
            ))

            fig_original.update_layout(
                title="元の損失データ（ヒートマップ）",
                xaxis_title="回転数 [rpm]",
                yaxis_title="トルク [Nm]",
                height=500
            )

            st.plotly_chart(fig_original, use_container_width=True)

            # ステップ2: 新しいグリッドの設定
            st.header("2. 新しいモータのグリッド設定")

            col1, col2 = st.columns(2)

            with col1:
                st.subheader("回転数の設定")
                rpm_method = st.radio(
                    "設定方法",
                    ["範囲と刻み幅", "個別指定"],
                    key="rpm_method"
                )

                if rpm_method == "範囲と刻み幅":
                    rpm_use_zero_base = st.checkbox(
                        "0を基準に刻み幅を設定",
                        value=False,
                        key="rpm_zero_base",
                        help="チェックすると、0から刻み幅の倍数で範囲を包含するグリッドを生成します"
                    )

                    rpm_min = st.number_input(
                        "最小回転数 [rpm]",
                        value=float(df['回転数_rpm'].min()),
                        step=100.0
                    )
                    rpm_max = st.number_input(
                        "最大回転数 [rpm]",
                        value=float(df['回転数_rpm'].max()),
                        step=100.0
                    )
                    rpm_step = st.number_input(
                        "刻み幅 [rpm]",
                        value=100.0,
                        step=10.0,
                        min_value=1.0
                    )

                    if rpm_use_zero_base:
                        # 0を基準に刻み幅の倍数でグリッド生成（最小値～最大値を含む）
                        rpm_start = np.floor(rpm_min / rpm_step) * rpm_step
                        rpm_end = np.ceil(rpm_max / rpm_step) * rpm_step
                        # 0から刻み幅で生成
                        temp_rpm = np.arange(rpm_start, rpm_end + rpm_step/2, rpm_step)
                        # 最小値以上、最大値以下の範囲に制限
                        temp_rpm = temp_rpm[(temp_rpm >= rpm_min) & (temp_rpm <= rpm_max)]

                        # 最小値を含むことを保証
                        if len(temp_rpm) == 0 or temp_rpm[0] > rpm_min:
                            temp_rpm = np.insert(temp_rpm, 0, rpm_min)

                        # 最大値を含むことを保証
                        if temp_rpm[-1] < rpm_max:
                            temp_rpm = np.append(temp_rpm, rpm_max)

                        new_rpm = temp_rpm
                    else:
                        new_rpm = np.arange(rpm_min, rpm_max + rpm_step/2, rpm_step)
                else:
                    rpm_input = st.text_area(
                        "回転数をカンマ区切りで入力",
                        value=",".join([str(int(x)) for x in np.linspace(df['回転数_rpm'].min(), df['回転数_rpm'].max(), 10)])
                    )
                    try:
                        new_rpm = np.array([float(x.strip()) for x in rpm_input.split(',')])
                    except:
                        st.error("回転数の入力形式が正しくありません")
                        new_rpm = np.array([])

            with col2:
                st.subheader("トルクの設定")

                # アウトライントルク設定モードの選択
                torque_range_mode = st.radio(
                    "アウトライントルク設定モード",
                    ["一定範囲", "回転数依存"],
                    key="torque_range_mode",
                    help="一定範囲: 全回転数で同じトルク範囲\n回転数依存: 回転数ごとに異なるトルク範囲を設定"
                )

                # 回転数依存のトルク範囲設定を保存する変数
                rpm_torque_ranges = None

                if torque_range_mode == "回転数依存":
                    st.info("回転数ごとの最小・最大トルクを設定します")

                    torque_range_input_method = st.radio(
                        "入力方法",
                        ["テキスト入力", "線形補間"],
                        key="torque_range_input_method"
                    )

                    if torque_range_input_method == "テキスト入力":
                        torque_range_text = st.text_area(
                            "回転数ごとのトルク範囲を入力（回転数,最小トルク,最大トルク）",
                            value=f"{df['回転数_rpm'].min():.0f},{df['トルク_Nm'].min():.1f},{df['トルク_Nm'].max():.1f}\n{df['回転数_rpm'].max():.0f},{df['トルク_Nm'].min():.1f},{df['トルク_Nm'].max():.1f}",
                            height=150,
                            help="各行に「回転数,最小トルク,最大トルク」の形式で入力"
                        )

                        try:
                            lines = [line.strip() for line in torque_range_text.strip().split('\n') if line.strip()]
                            rpm_torque_ranges = []
                            for line in lines:
                                parts = [float(x.strip()) for x in line.split(',')]
                                if len(parts) == 3:
                                    rpm_torque_ranges.append({
                                        'rpm': parts[0],
                                        'torque_min': parts[1],
                                        'torque_max': parts[2]
                                    })

                            if len(rpm_torque_ranges) < 2:
                                st.warning("少なくとも2行の入力が必要です")
                            else:
                                # 表示
                                display_df = pd.DataFrame(rpm_torque_ranges)
                                display_df.columns = ['回転数[rpm]', '最小トルク[Nm]', '最大トルク[Nm]']
                                st.dataframe(display_df)
                        except Exception as e:
                            st.error(f"入力形式エラー: {str(e)}")
                            rpm_torque_ranges = None

                    else:  # 線形補間
                        st.write("開始・終了点の回転数でのトルク範囲を設定")

                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.write("**開始回転数**")
                            rpm_start_range = st.number_input(
                                "開始回転数 [rpm]",
                                value=float(df['回転数_rpm'].min()),
                                key="rpm_start_range"
                            )
                            torque_min_start = st.number_input(
                                "開始時の最小トルク [Nm]",
                                value=float(df['トルク_Nm'].min()),
                                key="torque_min_start"
                            )
                            torque_max_start = st.number_input(
                                "開始時の最大トルク [Nm]",
                                value=float(df['トルク_Nm'].max()),
                                key="torque_max_start"
                            )

                        with col_b:
                            st.write("**終了回転数**")
                            rpm_end_range = st.number_input(
                                "終了回転数 [rpm]",
                                value=float(df['回転数_rpm'].max()),
                                key="rpm_end_range"
                            )
                            torque_min_end = st.number_input(
                                "終了時の最小トルク [Nm]",
                                value=float(df['トルク_Nm'].min()),
                                key="torque_min_end"
                            )
                            torque_max_end = st.number_input(
                                "終了時の最大トルク [Nm]",
                                value=float(df['トルク_Nm'].max()),
                                key="torque_max_end"
                            )

                        rpm_torque_ranges = [
                            {'rpm': rpm_start_range, 'torque_min': torque_min_start, 'torque_max': torque_max_start},
                            {'rpm': rpm_end_range, 'torque_min': torque_min_end, 'torque_max': torque_max_end}
                        ]

                # トルクグリッドの生成
                torque_method = st.radio(
                    "設定方法",
                    ["範囲と刻み幅", "個別指定"],
                    key="torque_method"
                )

                if torque_method == "範囲と刻み幅":
                    torque_use_zero_base = st.checkbox(
                        "0を基準に刻み幅を設定",
                        value=False,
                        key="torque_zero_base",
                        help="チェックすると、0から刻み幅の倍数で範囲を包含するグリッドを生成します"
                    )

                    if torque_range_mode == "一定範囲":
                        torque_min = st.number_input(
                            "最小トルク [Nm]",
                            value=float(df['トルク_Nm'].min()),
                            step=1.0
                        )
                        torque_max = st.number_input(
                            "最大トルク [Nm]",
                            value=float(df['トルク_Nm'].max()),
                            step=1.0
                        )
                    else:
                        # 回転数依存の場合は、全体の最小・最大を使用
                        if rpm_torque_ranges:
                            torque_min = min([r['torque_min'] for r in rpm_torque_ranges])
                            torque_max = max([r['torque_max'] for r in rpm_torque_ranges])
                            st.info(f"トルク範囲の全体: {torque_min:.1f} - {torque_max:.1f} Nm")
                        else:
                            torque_min = float(df['トルク_Nm'].min())
                            torque_max = float(df['トルク_Nm'].max())

                    torque_step = st.number_input(
                        "刻み幅 [Nm]",
                        value=1.0,
                        step=0.1,
                        min_value=0.01
                    )

                    if torque_use_zero_base:
                        # 0を基準に刻み幅の倍数でグリッド生成（最小値～最大値を含む）
                        torque_start = np.floor(torque_min / torque_step) * torque_step
                        torque_end = np.ceil(torque_max / torque_step) * torque_step
                        # 0から刻み幅で生成
                        temp_torque = np.arange(torque_start, torque_end + torque_step/2, torque_step)
                        # 最小値以上、最大値以下の範囲に制限
                        temp_torque = temp_torque[(temp_torque >= torque_min) & (temp_torque <= torque_max)]

                        # 最小値を含むことを保証
                        if len(temp_torque) == 0 or temp_torque[0] > torque_min:
                            temp_torque = np.insert(temp_torque, 0, torque_min)

                        # 最大値を含むことを保証
                        if temp_torque[-1] < torque_max:
                            temp_torque = np.append(temp_torque, torque_max)

                        new_torque = temp_torque
                    else:
                        new_torque = np.arange(torque_min, torque_max + torque_step/2, torque_step)
                else:
                    torque_input = st.text_area(
                        "トルクをカンマ区切りで入力",
                        value=",".join([f"{x:.1f}" for x in np.linspace(df['トルク_Nm'].min(), df['トルク_Nm'].max(), 10)])
                    )
                    try:
                        new_torque = np.array([float(x.strip()) for x in torque_input.split(',')])
                    except:
                        st.error("トルクの入力形式が正しくありません")
                        new_torque = np.array([])

            if len(new_rpm) > 0 and len(new_torque) > 0:
                st.info(f"新しいグリッド: 回転数 {len(new_rpm)}点 × トルク {len(new_torque)}点 = 合計 {len(new_rpm) * len(new_torque)}点")

                # ステップ3: 補間実行
                st.header("3. 補間実行")

                col_interp1, col_interp2 = st.columns(2)

                with col_interp1:
                    interpolation_direction = st.radio(
                        "補間方向",
                        ["2次元補間（横・縦両方向）", "1次元補間（縦方向のみ）"],
                        help="2次元: 回転数とトルク両方を考慮して補間\n1次元（縦）: 各回転数ごとに、トルク方向のみで補間"
                    )

                with col_interp2:
                    interpolation_method = st.selectbox(
                        "補間方法",
                        ["線形補間 (linear)", "3次スプライン補間 (cubic)"],
                        index=1
                    )

                if st.button("補間を実行", type="primary"):
                    with st.spinner("補間を計算中..."):
                        try:
                            # 回転数依存のトルク範囲補間関数
                            def get_torque_range_at_rpm(rpm_val, rpm_torque_ranges):
                                """指定回転数でのトルク範囲を線形補間で取得"""
                                if not rpm_torque_ranges or len(rpm_torque_ranges) < 2:
                                    return None, None

                                # rpm_torque_rangesをrpmでソート
                                sorted_ranges = sorted(rpm_torque_ranges, key=lambda x: x['rpm'])
                                rpms = np.array([r['rpm'] for r in sorted_ranges])
                                torque_mins = np.array([r['torque_min'] for r in sorted_ranges])
                                torque_maxs = np.array([r['torque_max'] for r in sorted_ranges])

                                # 線形補間
                                torque_min_at_rpm = np.interp(rpm_val, rpms, torque_mins)
                                torque_max_at_rpm = np.interp(rpm_val, rpms, torque_maxs)

                                return torque_min_at_rpm, torque_max_at_rpm

                            if interpolation_direction == "1次元補間（縦方向のみ）":
                                # 1次元補間（縦方向のみ）
                                from scipy.interpolate import interp1d

                                result_data = []
                                new_loss_matrix = np.full((len(new_torque), len(new_rpm)), np.nan)

                                st.info("各回転数ごとに、トルク方向のみで補間を行います。")

                                for j, rpm_val in enumerate(new_rpm):
                                    # この回転数に最も近い元データの回転数を探す
                                    unique_rpm_original = df['回転数_rpm'].unique()
                                    closest_rpm = unique_rpm_original[np.argmin(np.abs(unique_rpm_original - rpm_val))]

                                    # 最も近い回転数のデータを取得
                                    rpm_data = df[df['回転数_rpm'] == closest_rpm].copy()

                                    if len(rpm_data) >= 2:
                                        # トルクでソート
                                        rpm_data = rpm_data.sort_values('トルク_Nm')
                                        torques_original = rpm_data['トルク_Nm'].values
                                        losses_original = rpm_data['損失_Wh'].values

                                        # 1次元補間関数を作成
                                        kind = 'cubic' if "cubic" in interpolation_method and len(rpm_data) >= 4 else 'linear'
                                        try:
                                            f = interp1d(torques_original, losses_original, kind=kind,
                                                        fill_value='extrapolate', bounds_error=False)

                                            # 回転数ごとのトルク範囲を取得
                                            if torque_range_mode == "回転数依存" and rpm_torque_ranges:
                                                torque_min_at_rpm, torque_max_at_rpm = get_torque_range_at_rpm(rpm_val, rpm_torque_ranges)
                                            else:
                                                torque_min_at_rpm = new_torque.min()
                                                torque_max_at_rpm = new_torque.max()

                                            # 新しいトルクで補間
                                            for i, torque_val in enumerate(new_torque):
                                                # トルク範囲チェック
                                                if torque_val >= torque_min_at_rpm and torque_val <= torque_max_at_rpm:
                                                    loss_val = float(f(torque_val))
                                                    new_loss_matrix[i, j] = loss_val
                                                    result_data.append({
                                                        '回転数_rpm': rpm_val,
                                                        'トルク_Nm': torque_val,
                                                        '損失_Wh': loss_val
                                                    })
                                        except Exception as e:
                                            st.warning(f"回転数 {rpm_val:.0f} rpm での補間に失敗しました: {str(e)}")
                                    else:
                                        st.warning(f"回転数 {rpm_val:.0f} rpm のデータが不足しています（{len(rpm_data)}点）")

                                result_df = pd.DataFrame(result_data)

                            else:
                                # 2次元補間（従来の実装）
                                # 元データの一意な回転数とトルクを取得してソート
                                unique_rpm = np.sort(df['回転数_rpm'].unique())
                                unique_torque = np.sort(df['トルク_Nm'].unique())

                                # グリッドデータの作成
                                Z = np.zeros((len(unique_torque), len(unique_rpm)))
                                for i, torque_val in enumerate(unique_torque):
                                    for j, rpm_val in enumerate(unique_rpm):
                                        mask = (df['回転数_rpm'] == rpm_val) & (df['トルク_Nm'] == torque_val)
                                        if mask.any():
                                            Z[i, j] = df.loc[mask, '損失_Wh'].mean()
                                        else:
                                            Z[i, j] = np.nan

                                # NaN値の処理
                                if np.isnan(Z).any():
                                    st.warning("元データに欠損値があります。損失傾向を再現するため補間処理を行います。")
                                    from scipy.interpolate import griddata
                                    points = df[['回転数_rpm', 'トルク_Nm']].values
                                    values = df['損失_Wh'].values
                                    grid_rpm, grid_torque = np.meshgrid(unique_rpm, unique_torque)

                                    # まず線形補間を試行
                                    try:
                                        Z_linear = griddata(points, values, (grid_rpm, grid_torque), method='linear')
                                        # 線形補間で埋められなかった部分は最近傍値で補完
                                        if np.isnan(Z_linear).any():
                                            Z_nearest = griddata(points, values, (grid_rpm, grid_torque), method='nearest')
                                            Z = np.where(np.isnan(Z_linear), Z_nearest, Z_linear)
                                            st.info("線形補間 + 最近傍補完を使用しました")
                                        else:
                                            Z = Z_linear
                                            st.info("線形補間を使用しました")
                                    except:
                                        # 線形補間が失敗した場合は最近傍値を使用
                                        Z = griddata(points, values, (grid_rpm, grid_torque), method='nearest')
                                        st.info("最近傍補完を使用しました")

                                # 補間関数の作成
                                kx = 3 if "cubic" in interpolation_method else 1
                                ky = 3 if "cubic" in interpolation_method else 1

                                # データポイント数が補間次数より少ない場合の対処
                                if len(unique_rpm) < kx + 1:
                                    kx = len(unique_rpm) - 1
                                if len(unique_torque) < ky + 1:
                                    ky = len(unique_torque) - 1

                                interpolator = RectBivariateSpline(
                                    unique_torque,
                                    unique_rpm,
                                    Z,
                                    kx=kx,
                                    ky=ky
                                )

                                # 新しいグリッドで補間（回転数依存のトルク範囲を考慮）
                                result_data = []
                                new_loss_matrix = np.full((len(new_torque), len(new_rpm)), np.nan)

                                for j, rpm_val in enumerate(new_rpm):
                                    # 回転数ごとのトルク範囲を取得
                                    if torque_range_mode == "回転数依存" and rpm_torque_ranges:
                                        torque_min_at_rpm, torque_max_at_rpm = get_torque_range_at_rpm(rpm_val, rpm_torque_ranges)
                                    else:
                                        torque_min_at_rpm = new_torque.min()
                                        torque_max_at_rpm = new_torque.max()

                                    for i, torque_val in enumerate(new_torque):
                                        # トルク範囲チェック
                                        if torque_val >= torque_min_at_rpm and torque_val <= torque_max_at_rpm:
                                            loss_val = interpolator(torque_val, rpm_val)[0, 0]
                                            new_loss_matrix[i, j] = loss_val
                                            result_data.append({
                                                '回転数_rpm': rpm_val,
                                                'トルク_Nm': torque_val,
                                                '損失_Wh': loss_val
                                            })

                                result_df = pd.DataFrame(result_data)

                            st.success("補間が完了しました！")

                            # 結果の表示
                            st.subheader("補間結果")
                            st.dataframe(result_df.head(20))

                            # 統計情報
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("データ点数", f"{len(result_df)}点")
                            with col2:
                                st.metric("損失の平均", f"{result_df['損失_Wh'].mean():.2f} Wh")
                            with col3:
                                st.metric("損失の最大", f"{result_df['損失_Wh'].max():.2f} Wh")

                            # 補間結果の可視化
                            st.subheader("補間結果の可視化")

                            # 回転数依存のトルク範囲を表示
                            if torque_range_mode == "回転数依存" and rpm_torque_ranges:
                                st.info("⚠️ 回転数依存のトルク範囲が適用されています。範囲外のポイントは除外されています。")

                            fig_result = go.Figure(data=go.Heatmap(
                                z=new_loss_matrix,
                                x=new_rpm,
                                y=new_torque,
                                colorscale='RdYlBu_r',
                                colorbar=dict(title="損失 [Wh]")
                            ))

                            fig_result.update_layout(
                                title="補間後の損失データ（ヒートマップ）",
                                xaxis_title="回転数 [rpm]",
                                yaxis_title="トルク [Nm]",
                                height=500
                            )

                            st.plotly_chart(fig_result, use_container_width=True)

                            # 3Dサーフェスプロット
                            st.subheader("3D表示")

                            fig_3d = go.Figure(data=[go.Surface(
                                z=new_loss_matrix,
                                x=new_rpm,
                                y=new_torque,
                                colorscale='RdYlBu_r',
                                colorbar=dict(title="損失 [Wh]")
                            )])

                            fig_3d.update_layout(
                                title="補間結果（3D）",
                                scene=dict(
                                    xaxis_title="回転数 [rpm]",
                                    yaxis_title="トルク [Nm]",
                                    zaxis_title="損失 [Wh]"
                                ),
                                height=600
                            )

                            st.plotly_chart(fig_3d, use_container_width=True)

                            # ダウンロード
                            st.subheader("結果のダウンロード")

                            # マトリックス形式（2次元MAP）に変換
                            matrix_result = pd.DataFrame(
                                new_loss_matrix,
                                index=new_torque,
                                columns=new_rpm
                            )
                            matrix_result.index.name = 'トルク[Nm]'
                            matrix_result.columns.name = '回転数[rpm]'

                            # リセットしてトルク列を明示的に追加
                            matrix_output = matrix_result.reset_index()

                            col1, col2 = st.columns(2)

                            with col1:
                                # CSV形式でダウンロード
                                csv_buffer = io.StringIO()
                                matrix_output.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                                csv_data = csv_buffer.getvalue()

                                st.download_button(
                                    label="📥 CSV形式でダウンロード（2次元MAP）",
                                    data=csv_data,
                                    file_name="interpolated_motor_loss_matrix.csv",
                                    mime="text/csv"
                                )

                            with col2:
                                # Excel形式でダウンロード
                                excel_buffer = io.BytesIO()
                                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                                    matrix_output.to_excel(writer, index=False, sheet_name='補間結果')
                                excel_data = excel_buffer.getvalue()

                                st.download_button(
                                    label="📥 Excel形式でダウンロード（2次元MAP）",
                                    data=excel_data,
                                    file_name="interpolated_motor_loss_matrix.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                )

                        except Exception as e:
                            st.error(f"補間エラー: {str(e)}")
                            st.exception(e)

    except Exception as e:
        st.error(f"ファイル読み込みエラー: {str(e)}")
        st.exception(e)

else:
    st.info("👆 CSVまたはExcelファイルをアップロードしてください")

    # サンプルデータの説明
    st.markdown("---")
    st.subheader("📝 ファイルの形式例")

    # タブで形式を切り替え
    tab1, tab2 = st.tabs(["リスト形式", "マトリックス形式"])

    with tab1:
        st.markdown("**リスト形式（3列）**")
        sample_data_list = pd.DataFrame({
            '回転数_rpm': [1000, 1000, 1000, 2000, 2000, 2000, 3000, 3000, 3000],
            'トルク_Nm': [10, 20, 30, 10, 20, 30, 10, 20, 30],
            '損失_Wh': [5.2, 8.5, 12.3, 6.1, 9.8, 14.2, 7.3, 11.2, 16.5]
        })

        st.dataframe(sample_data_list)

        # サンプルファイルのダウンロード
        col1, col2 = st.columns(2)

        with col1:
            sample_csv = sample_data_list.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 リスト形式CSVをダウンロード",
                data=sample_csv,
                file_name="sample_motor_loss_list.csv",
                mime="text/csv"
            )

        with col2:
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                sample_data_list.to_excel(writer, index=False, sheet_name='損失データ')
            excel_data = excel_buffer.getvalue()

            st.download_button(
                label="📥 リスト形式Excelをダウンロード",
                data=excel_data,
                file_name="sample_motor_loss_list.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    with tab2:
        st.markdown("**マトリックス形式（損失マップ）**")
        st.markdown("縦軸: トルク[Nm]、横軸: 回転数[rpm]、セル: 損失[Wh]")

        # マトリックス形式のサンプルデータ作成
        rpm_values = [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000]
        torque_values = [5, 10, 15, 20, 25]

        loss_matrix = []
        for torque in torque_values:
            row = []
            for rpm in rpm_values:
                loss = (rpm / 1000) * (torque / 10) * 1.5 + (torque / 5)
                row.append(round(loss, 1))
            loss_matrix.append(row)

        sample_data_matrix = pd.DataFrame(loss_matrix, columns=rpm_values)
        sample_data_matrix.insert(0, 'トルク[Nm]', torque_values)

        st.dataframe(sample_data_matrix)

        # サンプルファイルのダウンロード
        col1, col2 = st.columns(2)

        with col1:
            sample_csv_matrix = sample_data_matrix.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 マトリックス形式CSVをダウンロード",
                data=sample_csv_matrix,
                file_name="sample_motor_loss_matrix.csv",
                mime="text/csv"
            )

        with col2:
            excel_buffer_matrix = io.BytesIO()
            with pd.ExcelWriter(excel_buffer_matrix, engine='openpyxl') as writer:
                sample_data_matrix.to_excel(writer, index=False, sheet_name='損失マップ')
            excel_data_matrix = excel_buffer_matrix.getvalue()

            st.download_button(
                label="📥 マトリックス形式Excelをダウンロード",
                data=excel_data_matrix,
                file_name="sample_motor_loss_matrix.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# フッター
st.markdown("---")
st.markdown("**モータ損失データ補間アプリ** | 2次元補間により異なるグリッドのモータデータを生成")
