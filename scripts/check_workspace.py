"""Read-only redesign checks against a running app, with screenshots of every workspace."""
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5174'
OUT = Path(__file__).resolve().parents[1] / 'var' / 'ui-review' / 'workbench'
OUT.mkdir(parents=True, exist_ok=True)
VIEWS = ['home', 'cases', 'leads', 'alerts', 'dossier', 'graph', 'money', 'connect', 'globe', 'explore', 'studio', 'review', 'faces', 'cop', 'oversight']

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel='chrome', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 960})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    report = {'screens': [], 'runtime_errors': errors}
    for width, height in [(1440, 960), (1024, 900), (390, 844)]:
        page.set_viewport_size({'width': width, 'height': height})
        for view in VIEWS:
            user = {'oversight': 'auditor.oversight', 'review': 'analyst.scrb'}.get(view, 'crime.pi')
            page.goto(f'{BASE}/?user={user}&view={view}')
            page.locator('.view-content').wait_for(timeout=20000)
            page.locator('.view-content > .app-loading').wait_for(state='hidden', timeout=20000)
            page.wait_for_timeout(1300 if view not in ['globe', 'cop', 'graph'] else 2000)
            page.screenshot(path=str(OUT / f'{view}-{width}.png'))
            overflow = page.locator('.stage').evaluate('(el) => ({width: el.clientWidth, scroll: el.scrollWidth})')
            report['screens'].append({'view': view, 'width': width, 'overflow': overflow['scroll'] > overflow['width'] + 1})
            assert page.locator('.view-content').inner_text().strip(), f'{view}: empty screen'
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(f'Captured all screens at {width}px', flush=True)

    page.set_viewport_size({'width': 1440, 'height': 960})
    page.goto(BASE + '/?user=crime.pi&view=home')
    expect(page.get_by_role('heading', name='Work queue', exact=True)).to_be_visible(timeout=15000)
    page.get_by_role('textbox', name='Filter work queue').fill('not-a-real-reference')
    expect(page.get_by_role('heading', name='No matching items')).to_be_visible()
    page.get_by_role('button', name='Clear filters', exact=True).click()
    page.get_by_role('button', name='Case details', exact=True).click()
    expect(page.locator('.case-popover')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.locator('.case-popover')).not_to_be_visible()
    page.get_by_role('button', name=re.compile('^Account')).click()
    expect(page.get_by_label('Demonstration account')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.locator('.account-popover')).not_to_be_visible()
    page.get_by_role('button', name='New case', exact=True).click()
    expect(page.get_by_role('dialog', name='Open a case')).to_be_visible()
    expect(page.get_by_role('button', name='Open case', exact=True)).to_be_disabled()
    page.get_by_role('button', name='Cancel', exact=True).click()
    page.keyboard.press('Control+k')
    expect(page.get_by_role('combobox', name='Search records')).to_be_focused()
    page.get_by_role('combobox', name='Search records').fill('Nitin')
    expect(page.get_by_role('listbox', name='Search results')).to_be_visible()
    page.wait_for_timeout(600)
    if page.get_by_role('listbox', name='Search results').get_by_role('option').count():
        page.keyboard.press('Enter')
        expect(page.locator('.dossier-head')).to_be_visible(timeout=15000)
    page.get_by_role('navigation', name='Workspace sections').get_by_role('button', name='Workspace', exact=True).click()
    page.get_by_role('navigation', name='Section tools').get_by_role('button', name='Cases', exact=True).click()
    expect(page.get_by_role('tab', name='Case board', exact=True)).to_be_visible()
    page.get_by_role('tab', name='Evidence and exports', exact=True).click()
    expect(page.get_by_role('tab', name='Evidence and exports', exact=True)).to_have_attribute('aria-selected', 'true')
    page.get_by_role('tab', name='Case board', exact=True).focus()
    page.keyboard.press('ArrowRight')
    expect(page.get_by_role('tab', name='Network', exact=True)).to_be_focused()
    page.keyboard.press('Enter')
    page.get_by_role('button', name='Switch to dark theme').click()
    expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
    page.screenshot(path=str(OUT / 'case-dark.png'))
    page.get_by_role('navigation', name='Section tools').get_by_role('button', name='Overview', exact=True).click()
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / 'home-dark.png'))
    page.get_by_role('button', name='Switch to light theme').click()
    page.set_viewport_size({'width': 390, 'height': 844})
    page.get_by_role('button', name='Open navigation').click()
    expect(page.get_by_role('dialog', name='Workspace navigation')).to_be_visible()
    page.screenshot(path=str(OUT / 'navigation-mobile.png'))
    page.keyboard.press('Escape')
    expect(page.get_by_role('dialog', name='Workspace navigation')).not_to_be_visible()
    expect(page.get_by_role('button', name='Open navigation')).to_be_focused()
    page.get_by_role('button', name='Open navigation').click()
    page.get_by_role('dialog', name='Workspace navigation').get_by_role('button', name='Network', exact=True).click()
    expect(page.get_by_role('heading', name='Network analysis', exact=True)).to_be_visible()
    expect(page.get_by_role('dialog', name='Workspace navigation')).not_to_be_visible()
    page.get_by_label('Case', exact=True).select_option('')
    expect(page.get_by_role('heading', name='Select a case to begin')).to_be_visible()
    report['interactions'] = 'passed'
    (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    browser.close()
    assert not errors, errors
    assert not any(screen['overflow'] for screen in report['screens']), 'Horizontal overflow; see report.json'
