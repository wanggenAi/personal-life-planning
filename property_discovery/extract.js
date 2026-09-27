(() => {
  const clean = value => (value || '').replace(/\s+/g, ' ').trim();
  const text = selector => clean(document.querySelector(selector)?.innerText);
  const host = location.hostname;
  // Read only gate indicators. Never persist page body, account widgets or chats.
  const gateText = clean(document.body?.innerText).slice(0, 800);
  const gated = /captcha|verify|passport|login|waf/.test(location.pathname + host)
    || /人机验证|安全验证|访问验证|请输入验证码|疑似使用网页抓取工具|访问过于频繁/.test(gateText);
  const pageUrl = location.origin + location.pathname;
  if (gated) return JSON.stringify({status: 'blocked', reason: 'verification_or_login_wall', url: pageUrl});
  if (/登录后查看|请先登录|登录后才能/.test(gateText)) {
    return JSON.stringify({status: 'blocked', reason: 'login_wall', url: pageUrl});
  }
  const attributes = selector => Object.fromEntries(
    Array.from(document.querySelectorAll(selector)).map(li => {
      const label = li.querySelector('.label');
      if (!label) return null;
      const clone = li.cloneNode(true);
      clone.querySelectorAll('.label, .link, .icon-box').forEach(el => el.remove());
      return [clean(label.innerText), clean(clone.textContent)];
    }).filter(Boolean)
  );
  if (host === 'xz.ke.com' && location.pathname.startsWith('/xiaoqu/')) {
    const heading = document.querySelector('h1');
    return JSON.stringify({status: heading ? 'ok' : 'empty', url: pageUrl, kind: 'community',
      community: clean(heading?.innerText), address: text('.title .sub'),
      attributes: Object.fromEntries(Array.from(document.querySelectorAll('.xiaoquInfoItem')).map(el => {
        const label = el.querySelector('.xiaoquInfoLabel');
        const content = el.querySelector('.xiaoquInfoContent');
        return [clean(label?.innerText), clean(content?.innerText)];
      }).filter(([label]) => label))});
  }
  if (host === 'xz.ke.com' && /\/ershoufang\/\d+\.html$/.test(location.pathname)) {
    const base = attributes('.introContent .base li');
    const transaction = attributes('.introContent .transaction li');
    const link = document.querySelector('.communityName a[href*="/xiaoqu/"]');
    return JSON.stringify({status: Object.keys(transaction).length ? 'ok' : 'empty',
      reason: Object.keys(transaction).length ? null : 'missing_public_transaction_fields',
      url: pageUrl, kind: 'detail', title: text('.title h1') || text('h1'),
      community: clean(link?.innerText), community_url: link?.href || null,
      region: text('.areaName .info') || text('.areaName'),
      price_text: text('.price .total'), unit_text: text('.price .unitPriceValue'),
      base, transaction});
  }
  if (host === 'xz.ke.com') {
    const rows = Array.from(document.querySelectorAll('li.clear')).filter(li => li.querySelector('.title a')).map(li => {
      const a = li.querySelector('.title a');
      return {url: a.href, title: clean(a.innerText), community: clean(li.querySelector('.positionInfo')?.innerText),
        info: clean(li.querySelector('.houseInfo')?.innerText),
        price_text: clean(li.querySelector('.totalPrice')?.innerText),
        unit_text: clean(li.querySelector('.unitPrice')?.innerText),
        location_hint: clean(li.querySelector('img')?.alt)};
    });
    const next = Array.from(document.querySelectorAll('.page-box a')).find(a => clean(a.innerText) === '下一页');
    return JSON.stringify({status: rows.length ? 'ok' : 'empty', reason: rows.length ? null : 'no_listing_cards',
      kind: 'list', url: pageUrl, rows, next_url: next?.href || null});
  }
  if (host === 'xz.esf.fang.com' && location.pathname.startsWith('/house/')) {
    const rows = Array.from(document.querySelectorAll('dl')).filter(dl => dl.querySelector('h4 a[href*="/chushou/"]')).map(dl => {
      const a = dl.querySelector('h4 a');
      // tel_shop may contain an agent name; whitelist only layout, area and floor.
      const info = clean(dl.querySelector('.tel_shop')?.innerText).split('|').slice(0, 3).join(' | ');
      return {url: a.href, title: clean(a.innerText), community: clean(dl.querySelector('.add_shop a')?.innerText),
        address: clean(dl.querySelector('.add_shop span')?.innerText), info,
        price_text: clean(dl.querySelector('.price_right .red')?.innerText),
        unit_text: clean(dl.querySelector('.price_right')?.lastElementChild?.innerText)};
    });
    return JSON.stringify({status: rows.length ? 'ok' : 'empty', reason: rows.length ? null : 'no_listing_cards',
      kind: 'list', url: pageUrl, rows, next_url: null});
  }
  return JSON.stringify({status: 'unsupported', reason: 'no_verified_dom_adapter', url: pageUrl});
})()
