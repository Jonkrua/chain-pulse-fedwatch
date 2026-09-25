"""Visit the official parent page normally; fail closed on incomplete data."""
import asyncio
import json
import pathlib
import re
import time
from playwright.async_api import async_playwright
from parse_cme import parse_view, validate_snapshot

SOURCE = 'https://www.cmegroup.cn/fed-watch/'


async def collect():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(locale='en-US', viewport={'width': 1440, 'height': 1100})
            response = await page.goto(SOURCE, wait_until='domcontentloaded', timeout=60000)
            if response and response.status >= 400:
                raise RuntimeError(f'CME returned HTTP {response.status}')
            target = None
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                for frame in page.frames:
                    if not frame.url.startswith('https://cmegroup-tools.quikstrike.net/'):
                        continue
                    text = await frame.locator('body').inner_text(timeout=5000)
                    if re.search(r'access denied|captcha|verify you are human', text, re.I):
                        raise RuntimeError('Source requires verification; not bypassed')
                    if 'PROBABILITIES' in text and 'Data as of' in text:
                        target = frame
                        break
                if target:
                    break
                await asyncio.sleep(2)
            if target is None:
                raise RuntimeError('No complete CME probability component loaded')
            tabs = target.locator('a[id*="lbMeeting"]')
            labels = [s.strip() for s in await tabs.all_inner_texts()]
            if not 1 <= len(labels) <= 24 or len(labels) != len(set(labels)):
                raise RuntimeError('Invalid meeting tab inventory')
            views = []
            for i, label in enumerate(labels):
                await tabs.nth(i).click()
                deadline = time.monotonic() + 20
                last_error = None
                while time.monotonic() < deadline:
                    try:
                        text = await target.locator('body').inner_text(timeout=5000)
                        parsed = parse_view(text, label)
                        views.append({'tabLabel': label, 'text': text})
                        print(json.dumps({'date': parsed['date'], 'ease': parsed['ease'], 'hold': parsed['hold'], 'hike': parsed['hike'], 'sourceAsOf': parsed['sourceAsOf']}))
                        break
                    except (ValueError, RuntimeError) as error:
                        last_error = error
                        await asyncio.sleep(.5)
                else:
                    raise RuntimeError(f'Invalid or unswitched meeting {label}: {last_error}')
            if len(views) != len(labels):
                raise RuntimeError('Not all meetings collected')
            return validate_snapshot(views)
        finally:
            await browser.close()


if __name__ == '__main__':
    snapshot = asyncio.run(collect())
    output = pathlib.Path('result')
    output.mkdir(exist_ok=True)
    (output / 'latest.json').write_text(json.dumps(snapshot, indent=2))
    print(f"Validated {len(snapshot['meetings'])} meetings. Source timestamps are preserved.")
