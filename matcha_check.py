"""
抹茶庫存檢查（雲端版：每次執行只檢查一輪，由 GitHub 排程重複執行）
通知頻道名稱從 GitHub Secret「NTFY_TOPIC」讀取，不要寫在這個檔案裡。

判斷邏輯（針對有多種容量的商品，例如 20g/40g/100g...）：
  頁面上每個「缺貨的容量」都會出現一次 "Out of stock"。
  只要這個次數比「基準值」少，就代表有某個容量補貨了 -> 通知。
  基準值 = 全部缺貨時的次數。第一次測試會顯示這個數字，請把它填到下面的 BASELINE。
"""
import os
import re
import time
import random
import requests

# 名稱: (商品頁網址, 基準值)    基準值先填 None，測試後再填數字
# 順序 = 檢查優先順序（越前面越先檢查）
BASE = "https://www.marukyu-koyamaen.co.jp/english/shop/products/"
PRODUCTS = {
    "雲鶴 Unkaku":          (BASE + "1141020c1", None),
    "金輪 Kinrin":          (BASE + "1151020c1", None),
    "和光 Wako":            (BASE + "1161020c1", None),
    "又玄 Yugen":           (BASE + "1171020c1", None),
    "五十鈴 Isuzu":         (BASE + "1191040c1", None),
    "青嵐 Aoarashi":        (BASE + "11a1040c1", None),
    "極長安 Kiwami Choan":  (BASE + "1g36020c1", None),
    "長安 Choan":           (BASE + "1121020c1", None),
    "千木の白 Chigi no Shiro": (BASE + "1181040c1", None),
}

# ======== 以下不用改 ========
TOPIC = os.environ.get("NTFY_TOPIC", "")
IS_TEST = os.environ.get("IS_TEST") == "true"

OUT = "out of stock"
BUY_WORDS = ["add to cart", "add to basket", "カートに入れる", "加入購物車"]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml",
           "Accept-Language": "en-US,en;q=0.9,ja;q=0.8"}


def notify(text, url=None):
    if not TOPIC:
        print("沒有設定 NTFY_TOPIC，無法通知")
        return
    headers = {"Priority": "high"}
    if url:
        headers["Click"] = url
    try:
        requests.post(f"https://ntfy.sh/{TOPIC}",
                      data=text.encode("utf-8"), headers=headers, timeout=15)
    except Exception as e:
        print("通知失敗：", e)


def check(url, baseline):
    """回傳 (狀態, 說明)。狀態 True=有貨, False=缺貨, None=無法判斷"""
    r = requests.get(url, headers=HEADERS, timeout=20)
    if r.status_code in (403, 429, 503):
        return None, f"被網站擋下 (HTTP {r.status_code})"
    r.raise_for_status()
    html = r.text.lower()

    # 去掉程式碼與固定的限量公告，只看畫面上看得到的文字
    html = re.sub(r"<(script|style).*?</\1>", " ", html, flags=re.S)
    html = re.sub(r"about limited availability.*?as soon as possible\.?",
                  " ", html, flags=re.S)

    n_out = html.count(OUT)
    n_buy = sum(html.count(w) for w in BUY_WORDS)
    info = f"缺貨標籤={n_out}個, 購買按鈕字樣={n_buy}個"

    if "product" not in html and n_out == 0 and n_buy == 0:
        return None, "頁面內容不像商品頁（可能被擋或改版）；" + info
    if baseline is not None:
        if n_out < baseline:
            return True, f"缺貨標籤減少了！{info}（基準{baseline}）"
        return False, f"全部缺貨；{info}（基準{baseline}）"
    # 還沒設定基準值：用保守規則
    if n_buy > 0:
        return True, "（未設基準，暫以有購買按鈕判斷）" + info
    if n_out > 0:
        return False, "（未設基準）" + info
    return None, "看不出庫存狀態；" + info


def main():
    lines = []
    for i, (name, (url, baseline)) in enumerate(PRODUCTS.items()):
        if i > 0:
            time.sleep(random.uniform(2, 5))  # 每款之間隔幾秒，避免被當成機器人
        try:
            status, why = check(url, baseline)
        except Exception as e:
            status, why = None, f"讀取失敗 ({e})"
        label = {True: "有貨！", False: "缺貨", None: "無法判斷"}[status]
        print(f"{name}: {label} - {why}")
        lines.append(f"{name}: {label}\n  {why}")
        if status is True:
            notify(f"🍵 有貨了！{name}\n趕快下單：{url}", url)
    if IS_TEST:
        notify("測試結果 ✅\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
