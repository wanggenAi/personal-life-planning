(() => {
  const clean = value => (value || '').replace(/\s+/g, ' ').trim();
  const text = selector => clean(document.querySelector(selector)?.innerText);
  const sanitize = value => clean(value).replace(/(?:\+?86[- ]?)?1[3-9]\d{9}|400[- ]?\d{3}[- ]?\d{4}(?:\s*转\s*\d+)?/g, '[联系方式已移除]');
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
      coordinates: Array.from(document.scripts).filter(s => !s.src).map(s =>
        s.textContent.match(/resblockPosition\s*:\s*['"]([\d.]+),([\d.]+)['"]/))
        .filter(Boolean).map(m => ({longitude: Number(m[1]), latitude: Number(m[2]), crs: 'BD-09', level: 'community_reference_point'}))[0] || null,
      history: Array.from(document.querySelectorAll('.frameDealListItem li')).slice(0,10).map(li => ({
        url: li.querySelector('.frameDealTitle')?.href || null,
        layout: clean(li.querySelector('.frameDealTitle')?.innerText),
        floor: clean(li.querySelector('.frameDealFloor')?.innerText),
        built_year: clean(li.querySelector('.frameDealResblock')?.innerText),
        area_text: clean(li.querySelector('.frameDealArea')?.innerText),
        deal_date: clean(li.querySelector('.frameDealDate')?.innerText),
        total_text: clean(li.querySelector('.frameDealPrice')?.innerText),
        unit_text: clean(li.querySelector('.frameDealUnitPrice')?.innerText),
        source_url: pageUrl, record_type: 'historical_transaction'
      })),
      surroundings: {traffic: Array.from(document.querySelectorAll('#mapListContainer li')).slice(0,10).map(li => ({
        name: clean(li.querySelector('.itemTitle')?.innerText),
        distance_text: clean(li.querySelector('.itemdistance')?.innerText),
        type: li.getAttribute('data-index'), source_url: pageUrl
      }))},
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
      overview: text('.houseInfo'),
      features: Object.fromEntries(Array.from(document.querySelectorAll('.baseattribute')).map(el =>
        [clean(el.querySelector('.name')?.innerText), sanitize(el.querySelector('.content')?.innerText)]).filter(([key]) => key)),
      feedback: Array.from(document.querySelectorAll('.daikan_list .des')).slice(0,5).map(el => sanitize(el.innerText)),
      rooms: Array.from(document.querySelectorAll('#infoList .row')).map(el =>
        Array.from(el.querySelectorAll('.col')).map(col => clean(col.innerText))),
      images: Array.from(document.querySelectorAll('.overview img, .smallImg img, .listImg img')).map(img =>
        img.getAttribute('data-original') || img.src).filter(src => /^https:\/\/[^/]+\.ljcdn\.com\//.test(src)
        && !/logo|blank|share|loading|avatar|agent/.test(src)
        && !/(?<!\d)1[3-9]\d{9}(?!\d)/.test(src)).filter((src,index,all) => all.indexOf(src) === index).slice(0,3),
      base, transaction});
  }
  if (host === 'xz.ke.com') {
    const rows = Array.from(document.querySelectorAll('li.clear')).filter(li => li.querySelector('.title a')).map(li => {
      const a = li.querySelector('.title a');
      return {url: a.href, title: clean(a.innerText), community: clean(li.querySelector('.positionInfo')?.innerText),
        community_url: li.querySelector('.positionInfo a[href*="/xiaoqu/"]')?.href || null,
        info: clean(li.querySelector('.houseInfo')?.innerText),
        price_text: clean(li.querySelector('.totalPrice')?.innerText),
        unit_text: clean(li.querySelector('.unitPrice')?.innerText),
        image_url: li.querySelector('img')?.getAttribute('data-original') || li.querySelector('img')?.src || null,
        location_hint: clean(li.querySelector('img')?.alt)};
    });
    const next = Array.from(document.querySelectorAll('.page-box a')).find(a => clean(a.innerText) === '下一页');
    return JSON.stringify({status: rows.length ? 'ok' : 'empty', reason: rows.length ? null : 'no_listing_cards',
      kind: 'list', url: pageUrl, rows, next_url: next?.href || null,
      search_links: Array.from(document.querySelectorAll('a')).filter(a =>
        a.href.startsWith('https://xz.ke.com/ershoufang/') && !/\d{8,}\.html/.test(a.href))
        .map(a => ({name: clean(a.innerText), url: a.href})).filter(a => a.name),
      range_templates: Array.from(document.querySelectorAll('.customFilter')).map(el =>
        ({type: el.getAttribute('data-role'), template: el.querySelector('.btn-range')?.getAttribute('data-url')}))});
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
