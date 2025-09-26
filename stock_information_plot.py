import pandas as pd
import matplotlib
matplotlib.use('Agg')  # 【新增】設定 Matplotlib 後端為 Agg (必須在 pyplot 導入前)
import matplotlib.pyplot as plt
import numpy as np
import os
import datetime
import requests
import twstock

# 設定中文字型，以確保在不同作業系統上都能正確顯示
plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'Heiti TC', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False # 解決負號顯示問題

def get_stock_code(stock_identifier, df):
    """
    根據股票代碼或名稱查找股票代碼。
    (此函式保留給 plot_stock_major_shareholders 使用)
    """
    identifier_str = str(stock_identifier)
    if identifier_str.isdigit() and int(identifier_str) in df['Code'].values:
        return identifier_str
    exact_match = df.loc[df['Name'] == identifier_str, 'Code']
    if not exact_match.empty:
        return str(exact_match.iloc[0])
    partial_match = df[df['Name'].str.contains(identifier_str, na=False)]
    if not partial_match.empty:
        return str(partial_match['Code'].iloc[0])
    return None

def plot_stock_revenue_trend(stock_identifier, save_path):
    """
    從 FinMind API 讀取資料並繪製營收趨勢圖，儲存為圖片。
    資料範圍：最近三個完整年度 + 當年度至今。
    修正：使用 revenue_year 和 revenue_month 對應營收月份。

    Parameters:
    stock_identifier (str or int): 股票代碼或名稱。
    save_path (str): 圖片儲存路徑。

    Returns:
    str: 成功時回傳 None，失敗時回傳錯誤訊息。
    """
    # --- 1. 股票代碼與名稱解析 ---
    try:
        stock_info = twstock.codes[str(stock_identifier)]
        stock_code = stock_info.code
        stock_name = stock_info.name
    except KeyError:
        return f"錯誤: 在 twstock 資料庫中找不到股票 '{stock_identifier}'"

    # --- 2. 從 FinMind API 獲取資料 ---
    try:
        finmind_api_token = os.getenv('FINMIND_API_TOKEN')
        finmind_url = "https://api.finmindtrade.com/api/v4/data"
        
        current_year = datetime.date.today().year
        start_year = current_year - 3
        start_date = f"{start_year}-01-01"
        end_date = datetime.date.today().strftime('%Y-%m-%d')

        params = {
            "dataset": "TaiwanStockMonthRevenue",
            "data_id": stock_code,
            "start_date": start_date,
            "end_date": end_date,
        }
        headers = {}
        if finmind_api_token:
            headers["Authorization"] = f"Bearer {finmind_api_token}"

        response = requests.get(finmind_url, params=params, headers=headers, timeout=20)
        response.raise_for_status()

        raw_data = response.json()
        if raw_data.get("status") != 200:
             raise ValueError(f"FinMind API 錯誤: {raw_data.get('msg', '未知錯誤')}")

        data_list = raw_data.get('data')
        if not data_list:
            raise ValueError(f"FinMind API 未回傳股票 {stock_code} 的月營收資料。")

        revenue_df = pd.DataFrame(data_list)
        
        # --- 修正處：欄位檢查 ---
        # 確保 API 回傳了營收歸屬的年份和月份欄位
        required_cols = ['date', 'revenue', 'revenue_year', 'revenue_month']
        missing_cols = [col for col in required_cols if col not in revenue_df.columns]
        if missing_cols:
            raise ValueError(f"FinMind API 回傳的資料缺少必要欄位: {', '.join(missing_cols)}")

    except requests.exceptions.RequestException as e:
        return f"錯誤: 連線 FinMind API 時發生錯誤: {e}"
    except ValueError as e:
        return f"錯誤: 處理 FinMind API 資料時發生錯誤: {e}"
    except Exception as e:
        return f"錯誤: 獲取營收資料時發生未預期錯誤: {e}"

    # --- 3. 數據處理 ---
    revenue_df.rename(columns={'revenue': 'Revenue'}, inplace=True)
    revenue_df['date'] = pd.to_datetime(revenue_df['date'])
    revenue_df.sort_values('date', inplace=True)
    
    revenue_df['Revenue'] = revenue_df['Revenue'] / 1000

    # --- 修正處：使用 revenue_year 和 revenue_month 來確定歸屬月份 ---
    # 這一步是修正數據偏移的關鍵
    revenue_df['Year'] = pd.to_numeric(revenue_df['revenue_year'])
    revenue_df['Month'] = pd.to_numeric(revenue_df['revenue_month'])

    # 計算 YoY (年增率)
    revenue_df.sort_values(by=['Month', 'Year'], inplace=True)
    revenue_df['YoY'] = revenue_df.groupby('Month')['Revenue'].pct_change(periods=1) * 100

    revenue_df = revenue_df[revenue_df['Year'] >= start_year]
    
    current_year_data = revenue_df[revenue_df['Year'] == current_year].copy()

    # --- 4. 繪圖部分 ---
    fig, ax1 = plt.subplots(figsize=(12, 7))
    years = sorted(revenue_df['Year'].unique())
    # 重新定義顏色順序以符合範例圖
    colors_map = {
        current_year - 3: 'red',    # 2022年
        current_year - 2: 'green',  # 2023年
        current_year - 1: 'orange', # 2024年
        current_year:     'blue',    # 2025年
    }
    
    for year in years:
        color = colors_map.get(year, 'gray') # 如果有更早的年份，用灰色表示
        data = revenue_df[revenue_df['Year'] == year]
        if not data.empty:
            ax1.plot(data['Month'], data['Revenue'], marker='o', linestyle='-', label=f'{year}年', color=color)
            
            # 在所有年份的節點上標註數值
            for _, row in data.iterrows():
                ax1.text(row['Month'], row['Revenue'], f'{int(row["Revenue"]):,}', ha='center', va='bottom')

    ax1.set_xlabel('月份')
    ax1.set_ylabel('月營收，單位：千元')
    ax1.set_xticks(np.arange(1, 13))
    ax1.set_xticklabels([f'{i}月' for i in range(1, 13)])
    
    if not current_year_data.empty and 'YoY' in current_year_data.columns:
        ax2 = ax1.twinx()
        ax2.bar(current_year_data['Month'], current_year_data['YoY'], alpha=0.3, color='lightgreen', label=f'{current_year} YOY')
        ax2.set_ylabel(f'{current_year} YOY，單位 : %')
        # 確保Y軸範圍合理
        yoy_max = current_year_data['YoY'].max()
        if pd.notna(yoy_max) and yoy_max > 0:
            ax2.set_ylim(bottom=0, top=yoy_max * 1.5)
        ax2.legend(loc='upper right')

    title = f"{stock_code} {stock_name} 營收變化圖"
    plt.title(title, fontsize=16)

    ax1.legend(loc='upper left')
    plt.grid(True)
    fig.tight_layout()
    
    plt.savefig(save_path)
    plt.close(fig)
    return None


def plot_stock_major_shareholders(stock_identifier, save_path):
    """
    從 大戶股權.csv 讀取資料並繪製大戶股權圖，儲存為圖片。
    (此函式維持原樣，不受影響)
    """
    try:
        major_shareholders_df = pd.read_csv('大戶股權.csv')
    except FileNotFoundError:
        return "錯誤: 找不到 大戶股權.csv 檔案。"

    stock_code = get_stock_code(stock_identifier, major_shareholders_df)
    if not stock_code:
        return f"錯誤: 在 大戶股權.csv 中找不到股票 {stock_identifier}"

    stock_data = major_shareholders_df[major_shareholders_df['Code'] == int(stock_code)]

    if stock_data.empty:
        return f"錯誤: 在 大戶股權.csv 中找不到股票代碼 {stock_code} 的資料"
    
    stock_major_shareholders = stock_data.iloc[0, 2:]
    
    valid_dates = []
    valid_values = []
    for date_str, value in stock_major_shareholders.items():
        try:
            pd.to_datetime(date_str)
            valid_dates.append(date_str)
            valid_values.append(value)
        except (ValueError, TypeError):
            continue
            
    dates = pd.to_datetime(valid_dates, errors='coerce')
    values = pd.to_numeric(valid_values, errors='coerce')

    valid_mask = ~pd.isna(dates) & ~np.isnan(values)
    dates = dates[valid_mask]
    values = values[valid_mask]
    
    sorted_idx = dates.argsort()
    sorted_dates_str = dates[sorted_idx].strftime('%Y-%m-%d')
    sorted_values = values[sorted_idx]

    # --- 繪圖部分 ---
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.step(sorted_dates_str, sorted_values, where='pre', marker='o', linestyle='-', color='dodgerblue', linewidth=3)
    
    for i, value in enumerate(sorted_values):
        ax.text(sorted_dates_str[i], sorted_values[i], f'{value:.2f}%', ha='center', va='bottom', fontsize=10, color='darkblue')

    stock_name = stock_data['Name'].values[0]
    title = f"{stock_data['Code'].values[0]} {stock_name} 大戶股權變化圖 (持股>400張)"
    plt.title(title, fontsize=16)
    plt.xlabel('日期 (週為單位)', fontsize=12)
    plt.ylabel('大戶股權比例 (%)', fontsize=12)
    
    plt.grid(True, which='both', linestyle='--', linewidth=0.7, alpha=0.7)
    plt.xticks(rotation=45, fontsize=10)
    plt.yticks(fontsize=10)
    plt.gca().set_facecolor('white')
    fig.tight_layout()

    plt.savefig(save_path)
    plt.close(fig)
    return None