# app.py (已修改)

from flask import Flask, render_template, request, url_for, redirect, flash
import os
import pandas as pd
import importlib

# --------------------------------------------------------------------------------
# 【新增】導入您的 scraper.py
# --------------------------------------------------------------------------------
try:
    from scraper import scrape_goodinfo
except ImportError:
    print("警告：找不到 'scraper.py' 檔案，'我的選股' 功能將無法使用。")
    # 定義一個假函式以避免啟動錯誤
    def scrape_goodinfo():
        print("錯誤：scrape_goodinfo 函式未定義。")
        return None
# --------------------------------------------------------------------------------

from dotenv import load_dotenv
load_dotenv('Finmind.env')

try:
    from stock_analyzer import analyze_stock
    from stock_information_plot import plot_stock_revenue_trend, plot_stock_major_shareholders, get_stock_code
    import stock_holders_scraper
    
    concentration_analyzer = importlib.import_module("1日籌碼集中度")
    fetch_stock_concentration_data = concentration_analyzer.fetch_stock_concentration_data
    filter_stock_data = concentration_analyzer.filter_stock_data

except ImportError as e:
    print(f"錯誤：無法導入必要的模組。請確認 'stock_analyzer.py', 'stock_information_plot.py', 'stock_holders_scraper.py' 和 '1日籌碼集中度.py' 檔案皆存在於同個資料夾中。")
    print(f"詳細錯誤：{e}")
    exit()

# Flask 應用程式設定
app = Flask(__name__)
app.secret_key = 'a_random_secret_key_for_your_app'

if not os.path.exists('static'):
    os.makedirs('static')

# 資料載入與管理
stock_list_df = None

def load_stock_list():
    """從 CSV 檔案載入股票代碼與名稱的對照表。"""
    try:
        return pd.read_csv('大戶股權.csv')[['Code', 'Name']]
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"讀取 '大戶股權.csv' 時發生錯誤: {e}")
        return None

stock_list_df = load_stock_list()

# Flask 路由 (Routes)

@app.route('/', methods=['GET', 'POST'])
def index():
    """應用程式首頁，處理股票查詢。"""
    if request.method == 'POST':
        stock_identifier = request.form.get('stock_id')
        if not stock_identifier:
            return render_template('index.html', error="請輸入股票代碼或名稱。")
        
        if stock_list_df is None:
             return render_template('index.html', error="找不到 '大戶股權.csv' 檔案，請先點擊「大戶股權每周更新」按鈕來下載最新資料。")

        stock_code = None
        try:
            if str(stock_identifier).isdigit() and int(stock_identifier) in stock_list_df['Code'].values:
                stock_code = str(int(stock_identifier))
        except ValueError:
            pass
        
        if not stock_code:
            stock_code = get_stock_code(stock_identifier, stock_list_df)

        if not stock_code:
            return render_template('index.html', stock_id_show=stock_identifier, error=f"找不到股票 '{stock_identifier}'。請確認代碼或名稱是否正確。")

        stock_name = stock_list_df[stock_list_df['Code'] == int(stock_code)]['Name'].values[0]

        tech_analysis_path_rel = os.path.join('static', f'stock_analysis_{stock_code}.png')
        revenue_chart_path_rel = os.path.join('static', f'revenue_{stock_code}.png')
        shareholder_chart_path_rel = os.path.join('static', f'shareholders_{stock_code}.png')

        if not os.path.exists(tech_analysis_path_rel):
            print(f"技術分析圖不存在，正在為 {stock_code} 生成...")
            error_msg = analyze_stock(stock_code)
            if "錯誤" in str(error_msg):
                return render_template('index.html', error=error_msg)
        
        if not os.path.exists(revenue_chart_path_rel):
            print(f"營收圖不存在，正在為 {stock_code} 生成...")
            error_msg = plot_stock_revenue_trend(stock_code, revenue_chart_path_rel)
            if error_msg:
                return render_template('index.html', error=error_msg)
        
        if not os.path.exists(shareholder_chart_path_rel):
            print(f"大戶股權圖不存在，正在為 {stock_code} 生成...")
            error_msg = plot_stock_major_shareholders(stock_code, shareholder_chart_path_rel)
            if error_msg:
                return render_template('index.html', error=error_msg)
        
        return render_template('index.html', 
                               tech_chart=url_for('static', filename=f'stock_analysis_{stock_code}.png'), 
                               revenue_chart=url_for('static', filename=f'revenue_{stock_code}.png'),
                               shareholder_chart=url_for('static', filename=f'shareholders_{stock_code}.png'),
                               stock_id_show=f"{stock_name} ({stock_code})")

    return render_template('index.html')


@app.route('/concentration_pick', methods=['POST'])
def concentration_pick():
    """執行籌碼集中度選股，並為結果批量生成圖表。"""
    try:
        flash("開始執行籌碼集中度選股，過程可能需要數分鐘，請耐心等候...", "success")
        
        stock_data = fetch_stock_concentration_data()
        
        if stock_data is None:
            flash("無法獲取籌碼集中度資料，可能是來源網站暫時無法訪問或格式已變更。", "error")
            return redirect(url_for('index'))

        filtered_stocks = filter_stock_data(stock_data)
        
        if filtered_stocks is None:
            flash("資料篩選過程中發生錯誤，請查看終端機日誌。", "error")
            return redirect(url_for('index'))

        if filtered_stocks.empty:
            flash("根據篩選條件，目前沒有找到任何符合的股票。", "success")
            return redirect(url_for('index'))
        
        print("\n===== 開始為篩選出的股票批量生成圖表 =====")
        filtered_stocks['代碼'] = filtered_stocks['代碼'].astype(str)

        for index, stock in filtered_stocks.iterrows():
            stock_code = stock['代碼']
            stock_name = stock['股票名稱']
            print(f"\n--- 正在處理: {stock_name} ({stock_code}) ---")

            try:
                print(f"  -> 生成技術分析圖...")
                tech_chart_result = analyze_stock(stock_code)
                if "錯誤" in str(tech_chart_result):
                    print(f"     [失敗] 技術分析圖生成失敗: {tech_chart_result}")
                else:
                    print(f"     [成功] 技術分析圖已儲存至 {tech_chart_result}")

                print(f"  -> 生成月營收趨勢圖...")
                revenue_chart_path = os.path.join('static', f'revenue_{stock_code}.png')
                revenue_error = plot_stock_revenue_trend(stock_code, revenue_chart_path)
                if revenue_error:
                    print(f"     [失敗] 月營收圖生成失敗: {revenue_error}")
                else:
                    print(f"     [成功] 月營收趨勢圖已儲存至 {revenue_chart_path}")

                print(f"  -> 生成大戶股權變化圖...")
                shareholder_chart_path = os.path.join('static', f'shareholders_{stock_code}.png')
                shareholder_error = plot_stock_major_shareholders(stock_code, shareholder_chart_path)
                if shareholder_error:
                    print(f"     [失敗] 大戶股權圖生成失敗: {shareholder_error}")
                else:
                    print(f"     [成功] 大戶股權變化圖已儲存至 {shareholder_chart_path}")
            
            except Exception as e:
                print(f"  -> 為 {stock_name} ({stock_code}) 生成圖表時發生未預期錯誤: {e}")
                continue

        print("===== 所有圖表生成完畢 =====\n")
        flash("選股完成！所有符合條件的股票圖表均已在背景生成完畢。", "success")

        concentration_table_html = filtered_stocks.to_html(
            classes='table-style', 
            index=False, 
            border=0
        )
        
        return render_template('index.html', concentration_table=concentration_table_html)

    except Exception as e:
        print(f"執行籌碼集中度選股的總過程中發生未預期錯誤: {e}")
        flash(f"執行選股時發生嚴重錯誤: {e}", "error")
        return redirect(url_for('index'))

# --------------------------------------------------------------------------------
# 【新增】處理 "我的選股" 的路由
# --------------------------------------------------------------------------------
@app.route('/my_stock_picks', methods=['POST'])
def my_stock_picks():
    """執行 scraper.py 中的爬蟲，並將結果顯示在主頁。"""
    try:
        flash("開始執行「我的選股」(from Goodinfo)，請稍候...", "success")
        
        # 呼叫從 scraper.py 導入的函式
        scraped_df = scrape_goodinfo()
        
        # 檢查是否有回傳資料
        if scraped_df is None or scraped_df.empty:
            flash("「我的選股」未回傳任何資料，可能是來源網站無符合條件的股票或網站結構已變更。", "error")
            return redirect(url_for('index'))

        # 將 DataFrame 轉換為 HTML 表格
        my_picks_table_html = scraped_df.to_html(
            classes='table-style', 
            index=False, 
            border=0
        )
        
        # 帶著新的表格資料渲染主頁面
        flash("「我的選股」執行完畢！", "success")
        return render_template('index.html', my_picks_table=my_picks_table_html)

    except Exception as e:
        print(f"執行「我的選股」過程中發生未預期錯誤: {e}")
        flash(f"執行「我的選股」時發生嚴重錯誤: {e}", "error")
        return redirect(url_for('index'))
# --------------------------------------------------------------------------------

@app.route('/update', methods=['POST'])
def update_data():
    """執行爬蟲來更新大戶股權資料"""
    global stock_list_df
    try:
        print("開始執行大戶股權資料更新...")
        stock_holders_scraper.main()
        stock_list_df = load_stock_list()
        print("資料更新成功，DataFrame 已重新載入。")
        flash("大戶股權資料已成功更新！", "success")
    except Exception as e:
        print(f"資料更新過程中發生嚴重錯誤: {e}")
        flash(f"資料更新失敗，請查看終端機錯誤訊息: {e}", "error")
    
    return redirect(url_for('index'))

# 應用程式啟動點

if __name__ == '__main__':
    # 這段程式碼只會在您於本地端直接執行 python app.py 時才會運行
    # 在雲端 Gunicorn 環境下，這段不會被執行
    if not os.getenv('FINMIND_API_TOKEN'):
        print("\n" + "="*60)
        print("警告: 未設定 FINMIND_API_TOKEN 環境變數...")
        print("="*60 + "\n")
    
    # 這裡的 port=int(os.environ.get('PORT', 5000)) 是為了更好地相容雲端平台
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)