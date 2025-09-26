import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from typing import Optional
from datetime import datetime
from io import StringIO

class StockHoldersScraper:
    def __init__(self):
        self.url = 'https://norway.twsthr.info/StockHoldersContinue.aspx'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        }
        self.params = {
            'Show': '1',
            'continue': 'Y',
            'weeks': '0',
            'growthrate': '-101',
            'beforeweek': '1',
            'price': '5000',
            'valuerank': '1-3000',
            'display': '1'
        }

    def fetch_data(self) -> Optional[str]:
        """從網站獲取資料"""
        try:
            response = requests.get(self.url, headers=self.headers, params=self.params)
            response.encoding = 'utf-8'
            return response.text
        except requests.RequestException as e:
            print(f"抓取資料時發生錯誤: {e}")
            return None

    @staticmethod
    def parse_date(date_str: str) -> str:
        """將日期字串解析為標準化格式"""
        # 處理 "YYYY MMDD" 格式
        full_date_match = re.match(r'(\d{4})\s*(\d{4})', date_str)
        if full_date_match:
            year = full_date_match.group(1)
            mmdd = full_date_match.group(2)
            return f"{year}-{mmdd[:2]}-{mmdd[2:]}"

        # 處理 "MMDD" 格式
        mmdd_match = re.match(r'^(\d{4})$', date_str)
        if mmdd_match:
            mmdd = mmdd_match.group(1)
            month = int(mmdd[:2])
            current_year = datetime.now().year
            # 根據月份判斷年份 (此為原腳本邏輯)
            year = current_year
            return f"{year}-{mmdd[:2]}-{mmdd[2:]}"

        return date_str

    def process_table(self, html_content: str) -> Optional[pd.DataFrame]:
        """處理 HTML 表格並回傳 DataFrame"""
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            table = soup.find('table', class_=["display", "dataTable", "no-footer"])

            if not table:
                print("在 HTML 內容中找不到表格")
                return None

            df = pd.read_html(StringIO(str(table)))[0]

            # 提取相關欄位
            df_subset = df.iloc[:, 3:18]
            df_subset = df_subset.drop(df_subset.columns[[1, 2]], axis=1)

            # 提取股票代碼和名稱
            df_subset[['Code', 'Name']] = df_subset.iloc[:, 0].str.extract(r'(\d{4})\s*(.*)')

            # 重新組織欄位順序
            cols = df_subset.columns.tolist()
            cols.remove('Code')
            cols.remove('Name')
            new_order = ['Code', 'Name'] + cols
            df_subset = df_subset[new_order]

            # 移除多餘的欄位
            df_subset = df_subset.drop(df_subset.columns[2], axis=1)

            # 處理日期欄位
            cols = df_subset.columns.tolist()
            for i in range(2, 14):
                cols[i] = self.parse_date(cols[i])
            df_subset.columns = cols

            # 轉換數值欄位
            for col in df_subset.columns[2:14]:
                df_subset[col] = pd.to_numeric(df_subset[col], errors='coerce')

            return df_subset

        except Exception as e:
            print(f"處理表格時發生錯誤: {e}")
            return None

    @staticmethod
    def save_to_csv(df: pd.DataFrame, filename: str = '大戶股權.csv'):
        """將 DataFrame 儲存為 CSV 檔案至當前目錄"""
        try:
            # 將檔案儲存至當前目錄
            df.to_csv(filename, index=False, encoding='utf-8-sig')
            print(f"檔案已成功儲存為 '{filename}'")

        except Exception as e:
            print(f"儲存檔案時發生錯誤: {e}")

def main():
    """主執行函式"""
    # 初始化爬蟲
    scraper = StockHoldersScraper()

    # 獲取並處理資料
    html_content = scraper.fetch_data()
    if html_content:
        df = scraper.process_table(html_content)
        if df is not None:
            # 儲存到 CSV
            scraper.save_to_csv(df)
            print("資料處理完成。")
            print(df.head())
        else:
            print("處理表格資料失敗")
    else:
        print("從網站獲取資料失敗")

if __name__ == "__main__":
    main()