const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

const urls = [
  ['加拿大', 'https://www.amazon.ca/'],
  ['美国', 'https://www.amazon.com/'],
  ['墨西哥', 'https://www.amazon.com.mx/'],
];

for (const [region, url] of urls) {
  console.log('='.repeat(70));
  console.log(`${region}  ${url}`);
  try {
    const res = await fetch(url, {
      redirect: 'follow',
      headers: {
        'user-agent': UA,
        accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9',
      },
      signal: AbortSignal.timeout(30000),
    });
    const body = await res.text();
    console.log('HTTP     :', res.status, res.statusText);
    console.log('finalUrl :', res.url);
    const hdrs = {};
    for (const [k, v] of res.headers) {
      if (/^(server|content-type|content-length|location|set-cookie|x-amz-|cache-control|via|x-cache)/i.test(k)) {
        hdrs[k] = k.toLowerCase() === 'set-cookie' ? '(present)' : v.slice(0, 100);
      }
    }
    console.log('headers  :', JSON.stringify(hdrs, null, 2));
    console.log('bodyLen  :', body.length);
    const title = (body.match(/<title[^>]*>([\s\S]*?)<\/title>/i) || [, ''])[1].replace(/\s+/g, ' ').trim();
    console.log('title    :', title);
    console.log('snippet  :', body.replace(/\s+/g, ' ').slice(0, 300));
    const markers = {
      'captcha/验证码': /captcha|Enter the characters you see/i.test(body),
      'robot check': /Robot Check|api-services-support@amazon/i.test(body),
      '正常首页(搜索框)': /id="twotabsearchtextbox"|id="nav-search"/i.test(body),
      '页面为空': body.length === 0,
    };
    console.log('特征判定 :', JSON.stringify(markers));
  } catch (e) {
    console.log('ERROR    :', e.message, e.cause?.code || '');
  }
  console.log('');
}
