"""测试不同公司号的 REL 搜索。"""
import sys, os, time
sys.path.insert(0, ".")
os.environ["OVERSEAS_PROXY"] = "http://127.0.0.1:7877"

from overseas.compintel.ic_ised_crawler import IcedCrawler

crawler = IcedCrawler(proxy="http://127.0.0.1:7877")

# 逐个测试公司号(每次重置 cookie)
for num in ["20770", "649L", "5871A", "649A", "649B"]:
    crawler.jar.clear()
    crawler.opener = __import__("urllib.request", fromlist=["build_opener"]).build_opener(
        __import__("http.cookiejar", fromlist=["CookieJar"]).CookieJar.__module__ and
        __import__("urllib.request", fromlist=["HTTPCookieProcessor"]).HTTPCookieProcessor(crawler.jar))
    crawler.opener.add_handler(
        __import__("urllib.request", fromlist=["ProxyHandler"]).ProxyHandler(
            {"http": "http://127.0.0.1:7877", "https": "http://127.0.0.1:7877"}))
    try:
        recs = crawler.search_rel(company_number=num, max_pages=1)
        print(f"  {num:8} → {len(recs)} 条")
    except Exception as e:
        print(f"  {num:8} → 失败: {e}")
    time.sleep(1)
