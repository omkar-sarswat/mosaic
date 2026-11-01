"""Read-only browser checks for the investigation UI. Requires Python Playwright and a running app."""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('DRISHTI_UI_URL', 'http://127.0.0.1:5173')
OUTPUT = Path(__file__).resolve().parents[1] / 'var' / 'ui-review'
OUTPUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={'width': 1600, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(BASE + '/?user=ed.dd&view=home')
    expect(page.get_by_role('heading', name='Investigation overview')).to_be_visible(timeout=20000)
    expect(page.locator('.network-count')).to_contain_text('16 of')
    page.wait_for_timeout(700)
    page.screenshot(path=str(OUTPUT / 'overview-dark.png'))
    page.keyboard.press('Control+k')
    expect(page.get_by_role('textbox', name='Search records')).to_be_focused()
    page.keyboard.press('Escape')
    page.get_by_role('button', name='Open network', exact=True).click()
    expect(page.get_by_role('heading', name='Network analysis', exact=True)).to_be_visible()
    expect(page.locator('.network-count')).to_contain_text('32 of')
    page.wait_for_timeout(600)
    page.screenshot(path=str(OUTPUT / 'network-grouped.png'))

    # Select a real, directed transfer from the authorized API result.
    case_id = page.get_by_label('Active case', exact=True).input_value()
    result = page.request.get(BASE + '/api/intel/cases/' + case_id + '/network', headers={'X-DRISHTI-User': 'ed.dd', 'X-DRISHTI-Case': case_id}).json()
    transfer = next(edge for edge in result['edges'] if edge['type'] == 'transferred_to' and edge['source'] != edge['target'])
    labels = {node['id']: node['label'] for node in result['nodes']}
    page.get_by_role('button', name='Toggle record list').click()
    for node_id in [transfer['source'], transfer['target']]:
        page.get_by_label('Find a record in this graph').fill(labels[node_id])
        page.locator('.record-list button').first.click()
    expect(page.locator('.network-selection')).to_contain_text('2 selected')
    page.get_by_role('button', name='Toggle record list').click()
    page.locator('.graph-view-options summary').click()
    page.get_by_label('Path method', exact=True).select_option('money')
    page.locator('.graph-view-options summary').click()
    page.get_by_role('button', name='Find path', exact=True).click()
    expect(page.locator('.graph-msg')).to_contain_text('1 connections')
    page.screenshot(path=str(OUTPUT / 'network-transfer-path.png'))
    page.get_by_role('button', name='Dismiss graph message').click()
    page.get_by_role('button', name='Clear graph selection').click()

    page.get_by_role('button', name='Analyze', exact=True).click()
    expect(page.locator('.analysis-metrics')).to_be_visible(timeout=15000)
    expect(page.locator('.analysis-metrics')).to_contain_text(str(len(result['nodes'])))
    page.screenshot(path=str(OUTPUT / 'network-analysis.png'))
    page.get_by_role('button', name='Close network analysis').click()
    page.get_by_label('Network layout', exact=True).select_option('communities')
    page.wait_for_timeout(300)
    page.get_by_label('Network layout', exact=True).select_option('force')
    page.wait_for_timeout(1600)
    page.get_by_label('Network layout', exact=True).select_option('types')
    page.get_by_label('Filter graph by record type', exact=True).select_option('Vehicle')
    expect(page.locator('.network-count')).to_contain_text('2 of')
    page.get_by_role('button', name='Reset view', exact=True).click()
    page.get_by_label('Relationship layer', exact=True).select_option('money')
    page.get_by_role('button', name='Reset view', exact=True).click()
    page.get_by_role('button', name='Switch to light theme').click()
    expect(page.locator('html')).to_have_attribute('data-theme', 'light')
    page.screenshot(path=str(OUTPUT / 'network-light.png'))
    page.get_by_role('button', name='Switch to dark theme').click()

    for label in ['Overview', 'Cases', 'Leads', 'Alerts', 'Dossier', 'Connections', 'Financial flows', 'Geospatial', 'Explorer', 'Face search', 'Disaster COP', 'Resolve', 'Oversight']:
        page.get_by_role('navigation', name='Applications').get_by_role('button', name=label, exact=True).click()
        page.wait_for_timeout(500)
        assert page.locator('.view-content').inner_text().strip() or page.locator('.view-content canvas').count(), f'{label}: empty screen'
        print('screen:', label, flush=True)

    for width, height in [(1024, 900), (390, 844)]:
        page.set_viewport_size({'width': width, 'height': height})
        if width < 641:
            page.get_by_role('button', name='Toggle navigation').click()
        page.get_by_role('navigation', name='Applications').get_by_role('button', name='Overview', exact=True).click()
        expect(page.get_by_role('heading', name='Investigation overview')).to_be_visible()
        page.wait_for_timeout(350)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), f'Page overflow at {width}px'
        assert page.locator('.stage').evaluate('(el) => el.scrollWidth <= el.clientWidth + 1'), f'Overview overflow at {width}px'
        page.screenshot(path=str(OUTPUT / f'overview-{width}.png'))
        page.get_by_role('button', name='Open network', exact=True).click()
        expect(page.locator('.network-count')).to_contain_text('32 of')
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), f'Graph overflow at {width}px'
        page.screenshot(path=str(OUTPUT / f'network-{width}.png'))

    # Empty case and failed request states stay navigable.
    page.set_viewport_size({'width': 1600, 'height': 1000})
    page.get_by_label('Active case', exact=True).select_option('')
    expect(page.get_by_role('heading', name='Select a case to begin')).to_be_visible()
    page.get_by_label('Active case', exact=True).select_option(case_id)
    expect(page.locator('.network-count')).to_contain_text('32 of')
    page.route('**/api/intel/cases/*/network', lambda route: route.fulfill(status=503, content_type='application/json', body='{"detail":"Temporary test failure"}'))
    page.get_by_role('button', name='Reload', exact=True).click()
    expect(page.get_by_role('heading', name='Network unavailable')).to_be_visible()
    page.unroute('**/api/intel/cases/*/network')
    page.get_by_role('button', name='Try again', exact=True).click()
    expect(page.locator('.network-count')).to_contain_text('32 of')
    assert not errors, json.dumps(errors, indent=2)
    print(json.dumps({'status': 'passed', 'runtime_errors': errors, 'screenshots': str(OUTPUT)}, indent=2))
    browser.close()
