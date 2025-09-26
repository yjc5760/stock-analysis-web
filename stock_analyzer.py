import os
import matplotlib
matplotlib.use('Agg')  # 【新增】設定 Matplotlib 後端為 Agg (必須在 pyplot 導入前)
import matplotlib.pyplot as plt
from matplotlib.font_manager import fontManager
# 設定支援中文的字型 (例如：微軟正黑體)
plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei']
plt.rcParams['axes.unicode_minus'] = False # 解決負號顯示問題

import requests # 新增導入 requests
import twstock
import pandas as pd
import numpy as np
import mplfinance as mpf
from datetime import date, timedelta
import matplotlib.pyplot as plt
from matplotlib.font_manager import fontManager
import matplotlib.dates as mdates

# 移除特定字型設定
# # fontManager.addfont('TaipeiSansTCBeta-Regular.ttf')
# # plt.rc('font', family='Taipei Sans TC Beta')

class TaiwanStockAnalyzer:
    def __init__(self, stock_id: str, days: int = 300) -> None:
        """
        初始化股票分析器
        :param stock_id: 股票代碼
        :param days: 分析期間天數
        """
        self.stock_id = stock_id
        self.days = days
        self.start_date = date.today() - timedelta(days=days)
        self.stock_name = self._get_stock_name()
        self.price_data: pd.DataFrame = pd.DataFrame()
        self.indicators = {}
        # 從環境變數讀取 FinMind API token，如果未設定則為 None
        self.finmind_api_token = os.getenv('FINMIND_API_TOKEN')


    def _get_stock_name(self) -> str:
        """利用 twstock 取得股票名稱"""
        try:
            info = twstock.codes[self.stock_id]
            return info.name
        except KeyError:
            # 如果 twstock 找不到，可以考慮未來從 FinMind API 獲取，或返回代碼本身
            print(f"警告: 股票代碼 {self.stock_id} 在 twstock.codes 中未找到。將使用代碼作為名稱。")
            return self.stock_id

    def fetch_data(self) -> None:
        """從 FinMind API 抓取股票資料"""
        print(f"正在從 FinMind API 抓取股票 {self.stock_id} 的資料...")
        
        finmind_url = "https://api.finmindtrade.com/api/v4/data"
        
        params = {
            "dataset": "TaiwanStockPrice",
            "data_id": self.stock_id,
            "start_date": self.start_date.strftime('%Y-%m-%d'),
            "end_date": date.today().strftime('%Y-%m-%d'), # FinMind 通常包含 end_date 當天
        }
        # 如果有 API token，則加入到 headers
        headers = {}
        if self.finmind_api_token:
            headers["Authorization"] = f"Bearer {self.finmind_api_token}"
            print("使用 FinMind API Token 進行驗證。")
        else:
            print("警告: 未設定 FINMIND_API_TOKEN 環境變數，將嘗試匿名存取 FinMind API。部分資料可能受限。")


        try:
            response = requests.get(finmind_url, params=params, headers=headers, timeout=20)
            response.raise_for_status() # 如果 HTTP 請求返回不成功的狀態碼，則拋出 HTTPError
            
            raw_data = response.json()
            
            if raw_data.get("status") != 200 and raw_data.get("msg") != "success": # FinMind API 成功時 status code 可能是 200，msg 是 "success"
                error_message_from_api = raw_data.get('error_message', 'FinMind API 回傳錯誤，但未提供詳細訊息。')
                status_code_from_api = raw_data.get('status_code', 'N/A')
                raise ValueError(f"FinMind API 錯誤 (代碼: {status_code_from_api}): {error_message_from_api}")

            data_list = raw_data.get('data')
            if not data_list:
                raise ValueError(f"FinMind API 未回傳股票 {self.stock_id} 在指定日期範圍內的資料。")

            data = pd.DataFrame(data_list)
            
            # 欄位名稱轉換與檢查
            # FinMind 'TaiwanStockPrice' 的欄位通常是: date, stock_id, Trading_Volume, Trading_money, open, max, min, close, spread, Trading_turnover
            # 我們需要: Date (index), Open, High, Low, Close, Volume
            required_finmind_cols = ['date', 'open', 'max', 'min', 'close', 'Trading_Volume']
            missing_cols = [col for col in required_finmind_cols if col not in data.columns]
            if missing_cols:
                raise ValueError(f"FinMind API 回傳的資料缺少必要欄位: {', '.join(missing_cols)}")

            # 重新命名欄位以符合 mplfinance 的需求
            data.rename(columns={
                'date': 'Date', # 將會設為 index
                'open': 'Open',
                'max': 'High',
                'min': 'Low',
                'close': 'Close',
                'Trading_Volume': 'Volume' # 注意：FinMind 的 Volume 單位是「股」，yfinance 是「股」
            }, inplace=True)
            
            # 將 'Date' 欄位轉換為 datetime 物件並設為索引
            data['Date'] = pd.to_datetime(data['Date'])
            data.set_index('Date', inplace=True)
            
            # 選擇需要的欄位
            data = data[['Open', 'High', 'Low', 'Close', 'Volume']]
            
            # 確保數值型態
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                data[col] = pd.to_numeric(data[col], errors='coerce')
            
            # Volume 可能需要除以 1000 如果是以「張」為單位，但 FinMind 的 TaiwanStockPrice 是「股」
            # data['Volume'] = data['Volume'] / 1000 # 如果 FinMind 回傳的是「股」而 yfinance 是「張」，則不需要此行

            self.price_data = data.dropna(subset=['Close']) # 主要依賴 'Close' 是否有效
            
            if self.price_data.empty:
                raise ValueError(f"股票 {self.stock_id} 從 FinMind API 取得資料後，在去除 'Close' 為空的資料後無剩餘數據。")
            
            print(f"成功從 FinMind API 抓取並處理 {self.stock_id} 的資料。共 {len(self.price_data)} 筆。")

        except requests.exceptions.RequestException as e:
            raise ValueError(f"連線 FinMind API 時發生錯誤: {e}")
        except ValueError as e: # 捕捉上面拋出的 ValueError
            raise ValueError(f"處理 FinMind API 資料時發生錯誤: {e}")
        except Exception as e: # 捕捉其他未預期錯誤
            raise ValueError(f"抓取 FinMind API 資料時發生未預期錯誤: {type(e).__name__} - {e}")

    def calculate_weighted_moving_average(self, prices, period):
        """
        計算加權移動平均線 (WMA)
        WMA(N) = {(當期收盤價 x N) + [前期收盤價 x (N – 1)] + …… + 第N期收盤價 x 1} / 加權乘數的總和
        加權乘數總和 = N + (N – 1) + (N – 2) + …… + 1 = N * (N + 1) / 2

        :param prices: 價格序列
        :param period: WMA 周期
        :return: 加權移動平均值列表
        """
        result = np.zeros_like(prices, dtype=float)
        result[:] = np.nan  # 初始化為 NaN

        # 加權乘數總和: N + (N-1) + ... + 1 = N*(N+1)/2
        weight_sum = period * (period + 1) / 2

        for i in range(period - 1, len(prices)):
            weighted_sum = 0
            for j in range(period):
                # 給最近的價格最高權重 (period)，給最早的價格最低權重 (1)
                weight = period - j
                weighted_sum += prices[i - j] * weight

            result[i] = weighted_sum / weight_sum

        return result

    def _calculate_sma(self, data, period):
        """計算簡單移動平均線"""
        return pd.Series(data).rolling(window=period).mean().values

    def _calculate_stochastic(self, high, low, close, k_period=9, k_slowing=3, d_period=3):
        """
        計算 KD 指標
        k_period: 計算%K的周期
        k_slowing: %K緩衝期
        d_period: 計算%D的周期
        """
        high_series = pd.Series(high)
        low_series = pd.Series(low)
        close_series = pd.Series(close)

        # 計算 %K 原始值 (未平滑)
        min_low = low_series.rolling(window=k_period).min()
        max_high = high_series.rolling(window=k_period).max()
        raw_k = 100 * ((close_series - min_low) / (max_high - min_low))

        # 平滑 %K
        k = raw_k.rolling(window=k_slowing).mean().values

        # 計算 %D (對 %K 再次平滑)
        d = pd.Series(k).rolling(window=d_period).mean().values

        return k, d

    def _calculate_macd(self, prices, fast_period=12, slow_period=26, signal_period=9):
        """
        計算 MACD 指標
        fast_period: 快線週期
        slow_period: 慢線週期
        signal_period: 信號線週期
        """
        prices_series = pd.Series(prices)

        # 計算快線 EMA
        ema_fast = prices_series.ewm(span=fast_period, adjust=False).mean()

        # 計算慢線 EMA
        ema_slow = prices_series.ewm(span=slow_period, adjust=False).mean()

        # 計算 MACD 線
        macd = ema_fast - ema_slow

        # 計算信號線 (MACD 的 EMA)
        signal = macd.ewm(span=signal_period, adjust=False).mean()

        # 計算柱狀圖
        histogram = macd - signal

        return macd.values, signal.values, histogram.values

    def calculate_indicators(self) -> None:
        """計算技術指標 (不使用 TA-lib)"""
        close = self.price_data['Close'].values
        high = self.price_data['High'].values
        low = self.price_data['Low'].values

        # 計算簡單移動平均線 (SMA)
        self.indicators['sma5'] = self._calculate_sma(close, 5)
        self.indicators['sma20'] = self._calculate_sma(close, 20)
        self.indicators['sma60'] = self._calculate_sma(close, 60)

        # 計算 KD 指標
        self.indicators['k'], self.indicators['d'] = self._calculate_stochastic(high, low, close)

        # 計算均線間的乖離百分比
        self.indicators['dev_5_20'] = (self.indicators['sma5'] - self.indicators['sma20']) / self.indicators['sma20'] * 100
        self.indicators['dev_20_60'] = (self.indicators['sma20'] - self.indicators['sma60']) / self.indicators['sma60'] * 100
        self.indicators['dev_5_60'] = (self.indicators['sma5'] - self.indicators['sma60']) / self.indicators['sma60'] * 100
        self.indicators['dev_1_20'] = (close - self.indicators['sma20']) / self.indicators['sma20'] * 100

        # 計算 MACD 指標
        self.indicators['macd'], self.indicators['macd_signal'], self.indicators['macd_hist'] = self._calculate_macd(close)

        # 計算週線指標 (5WMA 和 10WMA)
        self.indicators['wma5'] = self.calculate_weighted_moving_average(close, 5)
        self.indicators['wma10'] = self.calculate_weighted_moving_average(close, 10)

    def calculate_signals(self) -> None:
        """計算交易訊號"""
        # 階梯訊號
        self.indicators['I_value'] = self._calculate_stair_signal()

        # 乖離訊號
        self.indicators['J_value'] = self._calculate_deviation_signal()

        # 趨勢訊號：若 dev_5_60 為正則為多頭 (3)，否則空頭 (-3)
        self.indicators['K_value'] = [3 if dev >= 0 else -3 for dev in self.indicators['dev_5_60']]

        # KD 訊號：當 K 值大於等於80時視為超買（100）；低於等於20則為超賣（0）；中間則不顯示
        self.indicators['L_value'] = [100 if k >= 80 else (0 if k <= 20 else np.nan) for k in self.indicators['k']]

    def _calculate_stair_signal(self) -> list:
        """根據均線乖離計算階梯型態訊號"""
        signals = []
        for i in range(len(self.price_data)):
            dev_5_20 = self.indicators['dev_5_20'][i]
            dev_20_60 = self.indicators['dev_20_60'][i]
            dev_5_60 = self.indicators['dev_5_60'][i]

            if dev_5_20 >= dev_5_60 and dev_5_60 >= dev_20_60:
                signals.append(1)
            elif dev_5_60 >= dev_5_20 and dev_5_20 >= dev_20_60:
                signals.append(2)
            elif dev_5_60 >= dev_20_60 and dev_20_60 >= dev_5_20:
                signals.append(3)
            elif dev_20_60 >= dev_5_60 and dev_5_60 >= dev_5_20:
                signals.append(-1)
            elif dev_20_60 >= dev_5_20 and dev_5_20 >= dev_5_60:
                signals.append(-2)
            else:
                signals.append(-3)
        return signals

    def _calculate_deviation_signal(self) -> list:
        """根據收盤價與月線乖離計算乖離訊號"""
        return [4 if dev >= 5 else (-4 if dev <= -5 else np.nan)
                for dev in self.indicators['dev_1_20']]

    def create_chart(self, save_path: str = None) -> None:
        """
        建立並顯示或儲存技術分析圖表
        使用 mplfinance 的 make_addplot 來添加各個指標
        """
        # 為避免指標計算出現 NaN，從資料中剔除前一段資料
        start_idx = 101
        price_data = self.price_data.iloc[start_idx:].copy()

        # 將各項指標轉為 Series，並對齊日期索引
        series_dict = {}
        for key, values in self.indicators.items():
            series_dict[key] = pd.Series(values, index=self.price_data.index).iloc[start_idx:]

        # 建立 addplot 列表
        ap = []

        # 添加移動平均線
        ap.append(mpf.make_addplot(series_dict['sma5'], color='blue', width=1, panel=0, label='週線'))
        ap.append(mpf.make_addplot(series_dict['sma20'], color='orange', width=1, panel=0, label='月線'))
        ap.append(mpf.make_addplot(series_dict['sma60'], color='red', width=1, panel=0, label='季線'))

        # 添加 KD 指標 (panel=2)
        ap.append(mpf.make_addplot(series_dict['k'], color='red', width=1, panel=2, label='K值'))
        ap.append(mpf.make_addplot(series_dict['d'], color='green', width=1, panel=2, label='D值'))
        ap.append(mpf.make_addplot(series_dict['L_value'], type='scatter', color='blue', panel=2, label='KD信號'))

        # 添加乖離率 (panel=3)
        ap.append(mpf.make_addplot(series_dict['dev_5_20'], color='red', width=1, panel=3, label='週-月'))
        ap.append(mpf.make_addplot(series_dict['dev_20_60'], color='green', width=1, panel=3, label='月-季'))
        ap.append(mpf.make_addplot(series_dict['dev_5_60'], color='orange', width=1, panel=3, label='週-季'))

        # 添加信號 (panel=4)
        ap.append(mpf.make_addplot(series_dict['I_value'], type='bar', color='red', width=1, panel=4, label='階梯信號'))
        ap.append(mpf.make_addplot(series_dict['J_value'], type='scatter', color='blue', panel=4, label='乖離信號'))
        ap.append(mpf.make_addplot(series_dict['K_value'], color='orange', width=2, panel=4, label='多空信號'))

        # 添加 MACD 指標 (panel=5)
        ap.append(mpf.make_addplot(series_dict['macd'], color='blue', width=1, panel=5, label='MACD'))
        ap.append(mpf.make_addplot(series_dict['macd_signal'], color='red', width=1, panel=5, label='Signal'))

        # 修改 MACD 柱狀圖，將正值設為紅色，負值設為綠色
        # 創建正值和負值的 Series
        macd_hist_pos = series_dict['macd_hist'].copy()
        macd_hist_neg = series_dict['macd_hist'].copy()

        # 將負值設為 NaN 在正值 Series 中，將正值設為 NaN 在負值 Series 中
        macd_hist_pos[macd_hist_pos <= 0] = np.nan
        macd_hist_neg[macd_hist_neg > 0] = np.nan

        # 分別添加正值（紅色）和負值（綠色）柱狀圖
        ap.append(mpf.make_addplot(macd_hist_pos, type='bar', color='red', width=0.7, panel=5, label='Histogram (+)'))
        ap.append(mpf.make_addplot(macd_hist_neg, type='bar', color='green', width=0.7, panel=5, label='Histogram (-)'))

        # 添加WMA指標 (panel=6)
        ap.append(mpf.make_addplot(series_dict['wma5'], color='red', width=1.5, panel=6, label='5WMA'))
        ap.append(mpf.make_addplot(series_dict['wma10'], color='green', width=1.5, panel=6, label='10WMA'))

        # 設定圖表樣式
        style = mpf.make_mpf_style(
            base_mpf_style='yahoo',
            marketcolors=mpf.make_marketcolors(
              up='red',     # 上漲 K 線顏色
              down='green', # 下跌 K 線顏色
              edge='inherit', # 繼承顏色
              wick='inherit', # 繼承顏色
              volume='inherit' # 繼承顏色
            ),
            rc={
                'font.family': 'sans-serif', # 使用上面設定的 sans-serif 字型
                'font.sans-serif': ['Microsoft JhengHei'], # 再次確保字型設定
                'axes.unicode_minus': False, # 解決負號顯示問題
                'figure.figsize': (18, 18),  # 增加圖表高度以容納更多面板
                'axes.labelsize': 12,
                'xtick.labelsize': 10,
                'ytick.labelsize': 10
            }
        )

        # 設定圖表標題和各個面板的高度比例
        title = f'{self.stock_name} ({self.stock_id})'

        if save_path:
            # 如果要儲存圖片，不使用 returnfig
            mpf.plot(
                price_data,
                type='candle',
                addplot=ap,
                volume=True,
                panel_ratios=(40, 15, 15, 15, 15, 15, 15),  # 調整面板比例以包含兩個新面板
                style=style,
                title=title,
                show_nontrading=False,
                xrotation=90,
                figscale=2.0,
                savefig=save_path
            )
            plt.close()
        else:
            # 如果要顯示圖片，使用 returnfig
            fig, axlist = mpf.plot(
                price_data,
                type='candle',
                addplot=ap,
                volume=True,
                panel_ratios=(40, 15, 15, 15, 15, 15, 15),  # 調整面板比例以包含兩個新面板
                style=style,
                title=title,
                show_nontrading=False,
                xrotation=90,
                figscale=2.0,
                returnfig=True
            )

            # 設定所有子圖的日期格式和旋轉角度
            for ax in axlist:
                ax.tick_params(axis='x', rotation=90)

            plt.show()

def analyze_stock(stock_id: str, days: int = 300, save_path: str = None) -> str:
    """
    主函式：分析指定股票並顯示/儲存圖表
    :param stock_id: 股票代碼
    :param days: 分析期間天數
    :param save_path: 圖表儲存路徑。如果為 None，將儲存到 static 資料夾。
    :return: 成功時回傳圖片的相對路徑，失敗時回傳錯誤訊息。
    """
    try:
        analyzer = TaiwanStockAnalyzer(stock_id, days)
        print(f"正在抓取 {stock_id} ({analyzer.stock_name}) 的資料...")
        analyzer.fetch_data()
        print("計算技術指標中...")
        analyzer.calculate_indicators()
        print("計算交易訊號中...")
        analyzer.calculate_signals()

        # 設定儲存路徑到 static 資料夾
        static_folder = 'static'
        if not os.path.exists(static_folder):
            os.makedirs(static_folder) # 如果 static 資料夾不存在則建立

        # 使用固定的檔名格式，方便網頁引用
        image_filename = f"stock_analysis_{stock_id}.png"
        save_image_path = os.path.join(static_folder, image_filename)

        print(f"產生圖表並儲存至: {save_image_path}")
        analyzer.create_chart(save_path=save_image_path) # 強制儲存

        # 回傳相對於網頁根目錄的路徑
        return os.path.join('static', image_filename).replace('\\', '/') # 確保路徑分隔符為 /

    except Exception as e:
        error_message = f"分析過程發生錯誤 ({stock_id}): {str(e)}"
        print(error_message)
        return error_message # 回傳錯誤訊息