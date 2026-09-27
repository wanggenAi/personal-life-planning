import json
import subprocess
from urllib.parse import urlsplit


ALLOWED_HOSTS = {"xz.ke.com", "xz.esf.fang.com", "xuzhou.anjuke.com"}
MARKER = "PROPERTY_DISCOVERY_JSON:"


def validate_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username or parsed.password or parsed.port is not None):
        raise ValueError("Only configured HTTPS public listing hosts are allowed")
    if parsed.query or parsed.fragment:
        raise ValueError("Queries/fragments are not accepted; do not store session tokens")
    allowed_paths = {
        "xz.ke.com": ("/ershoufang/", "/xiaoqu/", "/chengjiao/"),
        "xz.esf.fang.com": ("/house/", "/chushou/"),
        "xuzhou.anjuke.com": ("/sale/",),
    }
    if not parsed.path.startswith(allowed_paths[parsed.hostname]):
        raise ValueError("URL is not a public listing/community path")
    return parsed.hostname


def read_page(url, script, timeout=65):
    """Normal Chrome navigation only. No cookies, tokens, APIs or challenge actions."""
    validate_url(url)
    # Each extraction checks for gates before returning only allowlisted DOM fields.
    program = ("import json, time\n"
               f"new_tab({url!r})\nwait_for_load()\n"
               f"payload = json.loads(js({script!r}))\n")
    if '/xiaoqu/' in urlsplit(url).path:
        # Click only normal public map tabs. On Retina displays use CDP CSS pixels.
        program += COMMUNITY_MAP_PROGRAM
    program += f"print({MARKER!r} + json.dumps(payload, ensure_ascii=False))\n"
    try:
        result = subprocess.run(["browser-harness"], input=program, text=True,
                                capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "browser_error", "reason": type(exc).__name__}
    lines = [line[len(MARKER):] for line in result.stdout.splitlines()
             if line.startswith(MARKER)]
    if result.returncode or not lines:
        return {"status": "browser_error", "reason": "harness_failed_or_no_payload"}
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError:
        return {"status": "browser_error", "reason": "invalid_payload"}
    if not isinstance(payload, dict):
        return {"status": "browser_error", "reason": "unexpected_payload_type"}
    return payload


COMMUNITY_MAP_PROGRAM = r'''
if payload.get('status') == 'ok':
    payload['map_access'] = []
    for label, category in [('医疗', 'medical'), ('教育', 'education'), ('购物', 'shopping')]:
        try:
            if not page_info()['url'].startswith('https://xz.ke.com/xiaoqu/'):
                payload['status'], payload['reason'] = 'blocked', 'map_redirect_access_limit'
                break
            nodes = cdp('Accessibility.getFullAXTree')['nodes']
            node = next(n for n in nodes if n.get('name', {}).get('value') == label and n.get('backendDOMNodeId'))
            cdp('DOM.scrollIntoViewIfNeeded', backendNodeId=node['backendDOMNodeId'])
            cdp('Page.bringToFront')
            time.sleep(0.4)
            rect = json.loads(js("JSON.stringify((()=>{const e=document.querySelector('#around li[data-bl=" + category + "]');if(!e)return null;const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})())"))
            if not rect:
                raise ValueError('map_tab_missing')
            cdp('Input.dispatchMouseEvent', type='mouseMoved', x=rect['x'], y=rect['y'])
            cdp('Input.dispatchMouseEvent', type='mousePressed', x=rect['x'], y=rect['y'], button='left', buttons=1, clickCount=1)
            cdp('Input.dispatchMouseEvent', type='mouseReleased', x=rect['x'], y=rect['y'], button='left', buttons=0, clickCount=1)
            time.sleep(2)
            if not page_info()['url'].startswith('https://xz.ke.com/xiaoqu/'):
                payload['status'], payload['reason'] = 'blocked', 'map_redirect_access_limit'
                break
            result = json.loads(js("JSON.stringify({selected:document.querySelector('#around .selectTag')?.getAttribute('data-bl'),items:Array.from(document.querySelectorAll('#mapListContainer li')).slice(0,10).map(li=>({name:li.querySelector('.itemTitle')?.innerText,distance_text:li.querySelector('.itemdistance')?.innerText,type:li.getAttribute('data-index')}))})"))
            if result.get('selected') != category:
                raise ValueError('map_tab_did_not_switch')
            # Do not mislabel stale map results from the previous category.
            prefixes = {'medical': ('hospital', 'pharmacy'), 'education': ('kindergarten', 'primary-school', 'middle-school', 'University'), 'shopping': ('mall', 'supermarket', 'market')}
            items = [dict(item, source_url=payload['url']) for item in result['items'] if (item.get('type') or '').startswith(prefixes[category])]
            payload.setdefault('surroundings', {})[category] = items
            payload['map_access'].append({'category': category, 'status': 'ok' if items else 'empty'})
        except Exception as exc:
            payload['map_access'].append({'category': category, 'status': 'unavailable', 'reason': str(exc)[:100]})
'''
