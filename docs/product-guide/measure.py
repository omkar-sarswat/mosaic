"""Report how much free space is left at the foot of every guide page (after build.py --preview)."""
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
with sync_playwright() as pw:
    b = pw.chromium.launch(channel='chrome', headless=True)
    pg = b.new_page(viewport={'width': 794, 'height': 1123})
    pg.goto((HERE / 'guide.html').as_uri(), wait_until='load')
    pg.evaluate('document.fonts.ready')
    pg.emulate_media(media='print')
    rows = pg.evaluate('''() => [...document.querySelectorAll('.page.guide')].map(p => {
        const r = p.getBoundingClientRect(), limit = p.querySelector('.foot').getBoundingClientRect().top - 14;
        let bottom = 0, ceiling = limit;
        const quote = p.querySelector('.page.narrative .quote');
        if (quote) ceiling = quote.getBoundingClientRect().top - 12;
        for (const e of p.querySelectorAll('.block p, .block h2, .keys, figure, .visual'))
            for (const q of e.getClientRects()) bottom = Math.max(bottom, q.bottom);
        const free = ceiling - bottom;
        return [+p.dataset.page, Math.round(free * 25.4 / 96 * 10) / 10];
        const cols = [...p.querySelectorAll('.feature-columns, .editorial-columns')];
        return [+p.dataset.page, Math.round((limit - bottom) * 25.4 / 96 * 10) / 10];
    })''')
    b.close()
for n, free in rows:
    flag = 'OVER' if free < 0 else ('ok' if free < 9 else 'space')
    print(f'page {n:02}: {free:6.1f} mm free  {flag}')
