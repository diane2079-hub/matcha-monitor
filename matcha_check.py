"""
抹茶庫存檢查（雲端版，使用真正的瀏覽器開頁面）
通知頻道名稱從 GitHub Secret「NTFY_TOPIC」讀取，不要寫在這個檔案裡。

為什麼用瀏覽器？小山園的庫存是網頁打開後才用 JavaScript 畫出來的，
單純下載原始碼看不到，所以要讓瀏覽器真的把頁面跑完再讀。

判斷邏輯（商品有多種容量，例如 20g/40g/100g...）：
  畫面上每個「缺貨的容量」都會出現一次 "Out of stock"。
  只要這個次數比「基準值」少，就代表有某個容量補貨了 -> 通知。
  基準值 = 全部缺貨時的次數。第一次測試會顯示這個數字，請把它填到下面。
"""
import os
import re
import time
import random
import requests
from playwright.sync_api import sync_playwright

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
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


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


def check(page, url, baseline):
    """回傳 (狀態, 說明)。狀態 True=有貨, False=缺貨, None=無法判斷"""
    resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
    code = resp.status if resp else 0
    if code in (403, 429, 503):
        return None, f"被網站擋下 (HTTP {code})"
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(2500)  # 多等一下，讓庫存標籤跑出來

    title = (page.title() or "")[:18]
    text = page.inner_text("body").lower()
    # 去掉固定的限量公告，免得干擾
    text = re.sub(r"about limited availability.*?as soon as possible\.?",
                  " ", text, flags=re.S)

    n_out = text.count(OUT)
    n_buy = sum(text.count(w) for w in BUY_WORDS)
    info = f"缺貨標籤={n_out}個, 購買字樣={n_buy}個"
    if IS_TEST:
        info += f" | H{code} T[{title}] 文字長{len(text)}"

    if len(text) < 200:
        return None, "頁面幾乎沒有內容（可能被擋）；" + info
    if baseline is not None:
        if n_out < baseline:
            return True, f"缺貨標籤減少了！{info}（基準{baseline}）"
        return False, f"全部缺貨；{info}（基準{baseline}）"
    # 還沒設定基準值：用保守規則
    if n_buy > 0:
        return True, "（未設基準，暫以有購買字樣判斷）" + info
    if n_out > 0:
        return False, "（未設基準）" + info
    return None, "看不出庫存狀態；" + info


def main():
    lines = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        context = browser.new_context(user_agent=UA, locale="en-US",
                                      viewport={"width": 1280, "height": 900})
        for i, (name, (url, baseline)) in enumerate(PRODUCTS.items()):
            if i > 0:
                time.sleep(random.uniform(2, 5))  # 每款之間隔幾秒
            page = context.new_page()
            try:
                status, why = check(page, url, baseline)
            except Exception as e:
                status, why = None, f"讀取失敗 ({str(e)[:80]})"
            finally:
                page.close()
            label = {True: "有貨！", False: "缺貨", None: "無法判斷"}[status]
            print(f"{name}: {label} - {why}")
            lines.append(f"{name}: {label}\n  {why}")
            if status is True:
                notify(f"🍵 有貨了！{name}\n趕快下單：{url}", url)
        browser.close()
    if IS_TEST:
        notify("測試結果 ✅（瀏覽器版）\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
