# 北美线站点可访问性测试报告

测试时间: 2026/9/18 13:54:51  (北京时间)

测试方式: Node.js v24.19.0 fetch / OpenSSL 直连,超时 30s,失败重试 2 次,并发 6,跟随重定向,桌面 Chrome UA。

| # | 线路 | 站点 | URL | 结论 | HTTP | 耗时 | 跳转后最终地址 | 页面标题 |
|---|------|------|-----|------|------|------|----------------|----------|
| 1 | 北美线-加拿大 | Amazon | https://www.amazon.ca/ | O 可访问 | 202 | 2.85s |  |  |
| 2 | 北美线-加拿大 | Brick | https://www.thebrick.com/ | O 可访问 | 200 | 2.74s |  | Furniture Store, Mattresses & Appliances - The Brick |
| 3 | 北美线-加拿大 | Leon's | https://www.leons.ca/ | O 可访问 | 200 | 1.43s |  | Leon&#39;s - Canada&#39;s Leading Furniture Store |
| 4 | 北美线-美国 | Amazon | https://www.amazon.com | O 可访问 | 200 | 6.53s |  | &nbsp; |
| 5 | 北美线-墨西哥 | Amazon | https://www.amazon.com.mx/ | O 可访问 | 202 | 0.62s |  |  |
| 6 | 北美线-墨西哥 | Sams | https://www.sams.com.mx/ | O 可访问 | 200 | 5.45s | https://www.sams.com.mx/blocked?url=Lw==&uuid=6718c832-b325-11f1-a05a-729a462dcb5e&vid=&g=b | Verify Your Identity |
| 7 | 北美线-墨西哥 | Palacio | https://www.elpalaciodehierro.com/buscar?q=tv | △ 可连但被拒 | 403 | 1.54s |  | Attention Required! \| Cloudflare |
| 8 | 北美线-加拿大 | BestBuy | https://www.bestbuy.ca/en-ca | X 不可达 | ERR | - |  |  |
| 9 | 北美线-加拿大 | Canadian Tire | https://www.canadiantire.ca/en.html | X 不可达 | ERR | - |  |  |
| 10 | 北美线-加拿大 | Costco | https://www.costco.ca/ | X 不可达 | ERR | - |  |  |
| 11 | 北美线-加拿大 | Visions | https://www.visions.ca/ | X 不可达 | ERR | - |  |  |
| 12 | 北美线-加拿大 | Walmart | https://www.walmart.ca/en | X 不可达 | ERR | - |  |  |
| 13 | 北美线-美国 | Best Buy | https://www.bestbuy.com | X 不可达 | ERR | - |  |  |
| 14 | 北美线-美国 | Costco | https://www.costco.com | X 不可达 | ERR | - |  |  |
| 15 | 北美线-美国 | Walmart | https://www.walmart.com | X 不可达 | ERR | - |  |  |
| 16 | 北美线-墨西哥 | Coppel | https://www.coppel.com/sd/TV | X 不可达 | ERR | - |  |  |
| 17 | 北美线-墨西哥 | Liverpool | https://www.liverpool.com.mx/tienda/home | X 不可达 | ERR | - |  |  |
| 18 | 北美线-墨西哥 | Walmart | https://www.walmart.com.mx/search?q=TV | X 不可达 | ERR | - |  |  |

## 失败 / 异常明细

### 北美线-墨西哥 / Palacio — https://www.elpalaciodehierro.com/buscar?q=tv
- 结论: △ 可连但被拒
- HTTP: 403 Forbidden
- 耗时: 1536ms
- 标题: Attention Required! | Cloudflare
- 响应头: server=cloudflare; content-type=text/html; charset=UTF-8; set-cookie=(present)
- 判定说明: TCP/TLS 与 HTTP 层均连通,但服务器以反爬/风控策略拒绝了本次请求(常见于 Akamai / Cloudflare / PerimeterX),真实浏览器通常可正常打开。

### 北美线-加拿大 / BestBuy — https://www.bestbuy.ca/en-ca
- 结论: X 不可达
- HTTP: 无响应
- 耗时: -
- 错误: `UND_ERR_CONNECT_TIMEOUT: Connect Timeout Error (attempted addresses: 23.214.168.234:443, timeout: 10000ms)`
- DNS 解析: 23.61.244.225, 23.35.110.247
- 判定说明: 请求未获得任何 HTTP 响应(连接/超时/TLS 层失败)。

### 北美线-加拿大 / Canadian Tire — https://www.canadiantire.ca/en.html
- 结论: X 不可达
- HTTP: 无响应
- 耗时: -
- 错误: `UND_ERR_CONNECT_TIMEOUT: Connect Timeout Error (attempted address: www.canadiantire.ca:443, timeout: 10000ms)`
- DNS 解析: 23.58.104.5
- 判定说明: 请求未获得任何 HTTP 响应(连接/超时/TLS 层失败)。

### 北美线-加拿大 / Costco — https://www.costco.ca/
- 结论: X 不可达
- HTTP: 无响应
- 耗时: -
- 错误: `UND_ERR_CONNECT_TIMEOUT: Connect Timeout Error (attempted address: www.costco.ca:443, timeout: 10000ms)`
- DNS 解析: 199.232.163.52
- 判定说明: 请求未获得任何 HTTP 响应(连接/超时/TLS 层失败)。

### 北美线-加拿大 / Visions — https://www.visions.ca/
- 结论: X 不可达
- HTTP: 无响应
- 耗时: -
- 错误: `UND_ERR_CONNECT_TIMEOUT: Connect Timeout Error (attempted addresses: 172.66.159.158:443, timeout: 10000ms)`
- DNS 解析: 172.66.159.158, 104.20.16.13
- 判定说明: 请求未获得任何 HTTP 响应(连接/超时/TLS 层失败)。

### 北美线-加拿大 / Walmart — https://www.walmart.ca/en
- 结论: X 不可达
- HTTP: 无响应
- 耗时: -
- 错误: `UND_ERR_CONNECT_TIMEOUT: Connect Timeout Error (attempted address: www.walmart.ca:443, timeout: 10000ms)`
- DNS 解析: 23.215.189.63
- 判定说明: 请求未获得任何 HTTP 响应(连接/超时/TLS 层失败)。

### 北美线-美国 / Best Buy — https://www.bestbuy.com
- 结论: X 不可达
- HTTP: 无响应
- 耗时: -
- 错误: `UND_ERR_CONNECT_TIMEOUT: Connect Timeout Error (attempted address: www.bestbuy.com:443, timeout: 10000ms)`
- DNS 解析: 23.55.96.189
- 判定说明: 请求未获得任何 HTTP 响应(连接/超时/TLS 层失败)。

### 北美线-美国 / Costco — https://www.costco.com
- 结论: X 不可达
- HTTP: 无响应
- 耗时: -
- 错误: `UND_ERR_CONNECT_TIMEOUT: Connect Timeout Error (attempted address: www.costco.com:443, timeout: 10000ms)`
- DNS 解析: 23.56.26.27
- 判定说明: 请求未获得任何 HTTP 响应(连接/超时/TLS 层失败)。

### 北美线-美国 / Walmart — https://www.walmart.com
- 结论: X 不可达
- HTTP: 无响应
- 耗时: -
- 错误: `UND_ERR_CONNECT_TIMEOUT: Connect Timeout Error (attempted address: www.walmart.com:443, timeout: 10000ms)`
- DNS 解析: 23.55.96.134
- 判定说明: 请求未获得任何 HTTP 响应(连接/超时/TLS 层失败)。

### 北美线-墨西哥 / Coppel — https://www.coppel.com/sd/TV
- 结论: X 不可达
- HTTP: 无响应
- 耗时: -
- 错误: `UND_ERR_CONNECT_TIMEOUT: Connect Timeout Error (attempted address: www.coppel.com:443, timeout: 10000ms)`
- DNS 解析: 23.55.98.137
- 判定说明: 请求未获得任何 HTTP 响应(连接/超时/TLS 层失败)。

### 北美线-墨西哥 / Liverpool — https://www.liverpool.com.mx/tienda/home
- 结论: X 不可达
- HTTP: 无响应
- 耗时: -
- 错误: `UND_ERR_CONNECT_TIMEOUT: Connect Timeout Error (attempted address: www.liverpool.com.mx:443, timeout: 10000ms)`
- DNS 解析: 23.58.105.5
- 判定说明: 请求未获得任何 HTTP 响应(连接/超时/TLS 层失败)。

### 北美线-墨西哥 / Walmart — https://www.walmart.com.mx/search?q=TV
- 结论: X 不可达
- HTTP: 无响应
- 耗时: -
- 错误: `UND_ERR_CONNECT_TIMEOUT: Connect Timeout Error (attempted address: www.walmart.com.mx:443, timeout: 10000ms)`
- DNS 解析: 23.55.98.174
- 判定说明: 请求未获得任何 HTTP 响应(连接/超时/TLS 层失败)。
