"""Build the independent A4 product guide. Never writes the 120-page book."""
import argparse
import hashlib
import html
import json
import re
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright
from pypdf import PdfReader, PdfWriter
from content import PAGES

HERE=Path(__file__).resolve().parent
OUT=HERE.parent/'Mosaic-Product-Guide.pdf'
esc=html.escape

def brand():
    return '<span class="brand"><img src="brand/weirwood-logo-512.png" alt="Weirwood logo">WEIRWOOD</span>'

def header(label):
    return f'<header class="running">{brand()}<span class="running-label">{esc(label)}</span></header>'

def footer(n):
    return f'<footer class="foot"><span>Mosaic / Product and capabilities guide</span><span class="folio">{n:02}</span></footer>'

def rich(t):
    """Escape text, then turn **phrase** into a highlighted phrase."""
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', esc(t))

def block(h,t):
    return f'<section class="block"><h2>{esc(h)}</h2><p>{rich(t)}</p></section>'

def keys(items):
    if not items: return ''
    return '<div class="keys">'+''.join(f'<div class="key"><span class="key-n">{i:02}</span><p>{rich(t)}</p></div>' for i,t in enumerate(items,1))+'</div>'

def visual(kind):
    if kind=='model':
        entries=[('Authorised sources','FIRs, bank statements, call records, registries and seized documents'),('One connected record model','People, money, phones, places and events, every fact linked to its source'),('Investigation and action','Leads, decisions, sealed evidence and court-ready reports')]
        return '<div class="visual"><div class="architecture">'+ '<div class="arrow">→</div>'.join(f'<div class="layer {"core" if i==1 else ""}"><strong>{h}</strong><small>{t}</small></div>' for i,(h,t) in enumerate(entries))+'</div></div>'
    if kind=='problem':
        entries=[('Fragmented inputs','Police, bank, telecom and registry records, each in its own format and with its own identifiers'),('Uncertain identity','The same person under many spellings and scripts; different people under one name'),('Disconnected work','Analysis in spreadsheets, decisions in files, evidence in cupboards'),('Difficult handover','Conclusions passed on without the records and reasoning behind them')]
        return '<div class="visual"><div class="source-types">'+''.join(f'<div class="source-type"><strong>{h}</strong>{t}</div>' for h,t in entries)+'</div></div>'
    if kind=='missions':
        entries=[('Investigation','FIRs, suspects, networks, sealed evidence and the case diary'),('Financial analysis','Accounts, shell companies, laundering typologies and money trails'),('Operational response','Disaster alerts, affected districts, hospitals and dispatches'),('Institutional review','Approvals, source quality, audit trail and transparency')]
        return '<div class="visual"><div class="source-types">'+''.join(f'<div class="source-type"><strong>{h}</strong>{t}</div>' for h,t in entries)+'</div></div>'
    if kind=='workflow':
        entries=[('Establish','Identity, case and purpose'),('Prepare','Sources, matches and publication'),('Examine','Dossiers, graphs, money and places'),('Coordinate','Leads, decisions and exhibits'),('Report','Release, closure and retention')]
        return '<div class="visual"><div class="workflow">'+''.join(f'<div class="stage"><div class="stage-number">{i}</div><strong>{h}</strong>{t}</div>' for i,(h,t) in enumerate(entries,1))+'</div><div class="workflow-note">Source context and recorded decisions connect the stages.</div></div>'
    if kind=='deployment':
        return '<div class="visual"><div class="capability-strip"><div><strong>Institution</strong>Officers, roles, agencies, approvals and oversight, mapped to the access model</div><div><strong>Information</strong>Authorised sources, reviewed intakes and a register of quality issues</div><div><strong>Environment</strong>Offline laptop or state data centre, SQLite or PostgreSQL, backed up</div></div></div>'
    return ''

def make_html():
    cover='<img class="cover-panel" src="assets/cover-city-network.png" alt="Conceptual city and record network illustration"><div class="cover-left">'+brand()+'''<h1>Mosaic</h1><p class="descriptor">Investigation and intelligence workspace</p><div class="red-rule"></div><p class="positioning">Product purpose.<br>Agency workflows.<br>Complete capabilities.</p><div class="cover-meta">Product and capabilities guide<br>October 2026<br>Weirwood</div></div><div class="panel-label">Investigate<br>Understand<br>Review</div>'''
    sections=[f'<article class="page cover" id="page-1" data-page="1">{cover}</article>']
    toc=header('Contents')+'<h1>Contents</h1>'
    for letter,label,start,end in [('A','Purpose and institutional value',3,6),('B','Product capabilities',7,28),('C','Institutional operation',29,30)]:
        toc+=f'<div class="toc-group"><div class="toc-heading"><span class="letter">{letter}</span><span>{label}</span><span class="n">{start:02}</span></div>'
        for n in range(start,end+1):
            p=PAGES[n-3]
            toc+=f'<a class="toc-row" href="#page-{n}"><span class="num">{n-2:02}</span><span>{esc(p["title"])}</span><span class="n">{n:02}</span></a>'
        toc+='</div>'
    toc+='<p class="toc-note">Select a section to open it. PDF bookmarks provide the same navigation. The companion product book contains the detailed screen reference.</p>'
    sections.append(f'<article class="page contents" id="page-2" data-page="2">{toc}{footer(2)}</article>')
    for n,p in enumerate(PAGES,3):
        body=header(p['group'])+f'<div class="section-number">{n-2:02} / MOSAIC</div><h1 class="{"long" if len(p["title"])>31 else ""}">{esc(p["title"])}</h1><p class="lead">{rich(p["lead"])}</p>'+keys(p.get('keys'))
        if p['image']:
            body+=f'<figure class="screen-figure"><img src="shots/{p["image"]}.png" alt="{esc(p["title"])}"><figcaption><span>Application view / {esc(p["title"])}</span><span>Synthetic demonstration</span></figcaption></figure>'
            body+='<div class="feature-columns">'+''.join(block(*b) for b in p['blocks'])+'</div>'
        else:
            body+=visual(p['visual'])+'<div class="editorial-columns">'+''.join(block(*b) for b in p['blocks'])+'</div>'
            if p.get('quote'): body+=f'<p class="quote">{rich(p["quote"])}</p>'
        sections.append(f'<article class="page guide {"illustrated" if p["image"] else "narrative"}" id="page-{n}" data-page="{n}">{body}{footer(n)}</article>')
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Mosaic — Product and capabilities guide</title><link rel="stylesheet" href="guide.css"></head><body>'+''.join(sections)+'</body></html>'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--preview',action='store_true');args=parser.parse_args()
    assert len(PAGES)==28, len(PAGES)
    if not (HERE/'provenance.json').exists():
        from prepare_sources import prepare
        prepare()
    provenance=json.loads((HERE/'provenance.json').read_text())
    old=HERE.parent/provenance['reference_pdf']
    original_hash=hashlib.sha256(old.read_bytes()).hexdigest() if old.exists() else None
    (HERE/'guide.html').write_text(make_html(),encoding='utf-8')
    report=dict(edition='Product and capabilities guide',date='2026-10-22',page_mm=[210,297],pages_expected=30,screens=[],sections=[])
    manuscript=['# Mosaic\n\nProduct and capabilities guide\n\nWeirwood · October 2026\n']
    for n,p in enumerate(PAGES,3):
        words=len((p['lead']+' '+' '.join(h+' '+t for h,t in p['blocks'])).replace('**','').split())
        assert words>=150, (n,words)
        report['sections'].append(dict(page=n,title=p['title'],words=words))
        manuscript.append(f'\n## Page {n:02} — {p["title"]}\n\n{p["lead"]}\n')
        if p.get('keys'): manuscript.append('\n'+''.join(f'- {k}\n' for k in p['keys']))
        for h,t in p['blocks']: manuscript.append(f'\n### {h}\n\n{t}\n')
        if p['image']:
            path=HERE/'shots'/f'{p["image"]}.png'
            with Image.open(path) as im: pixels=list(im.size)
            report['screens'].append(dict(page=n,file=path.name,pixels=pixels,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            manuscript.append(f'\nFigure: `{p["image"]}.png` — synthetic demonstration.\n')
    (HERE/'manuscript.md').write_text(''.join(manuscript),encoding='utf-8')
    inventory=json.loads((HERE/'coverage.json').read_text(encoding='utf-8'))
    assert len(inventory)==88 and len({s['reference_image'] for s in inventory})==88
    assert set(s['guide_page'] for s in inventory)==set(range(7,29))
    report['reference_workflows_covered']=len(inventory)
    report['capability_areas']=17
    out=HERE/'previews';out.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='chrome',headless=True)
        pg=browser.new_page(viewport={'width':794,'height':1123},device_scale_factor=1.5)
        pg.route('http://**/*',lambda r:r.abort());pg.route('https://**/*',lambda r:r.abort())
        pg.goto((HERE/'guide.html').as_uri(),wait_until='load');pg.evaluate('document.fonts.ready');pg.emulate_media(media='print')
        pg.evaluate('''() => {
          for(const row of document.querySelectorAll('.text-columns')) {
            const cols=[...row.children],atoms=cols.flatMap(c=>[...c.children]);
            let best=1,height=Infinity;
            for(let split=1;split<atoms.length;split++) {
              cols[0].replaceChildren(...atoms.slice(0,split));cols[1].replaceChildren(...atoms.slice(split));
              const v=Math.max(cols[0].getBoundingClientRect().height,cols[1].getBoundingClientRect().height);
              if(v<height){height=v;best=split;}
            }
            cols[0].replaceChildren(...atoms.slice(0,best));cols[1].replaceChildren(...atoms.slice(best));
          }
        }''')
        checks=pg.evaluate('''() => {
          const broken=[...document.images].filter(x=>!x.complete||!x.naturalWidth).map(x=>x.src),overflow=[];
          for(const p of document.querySelectorAll('.page:not(.cover)')) {
            const r=p.getBoundingClientRect(),limit=p.querySelector('.foot').getBoundingClientRect().top-14;
            for(const e of p.querySelectorAll('*')) {
              if(e.closest('.foot'))continue;
              for(const q of e.getClientRects()) if(q.height&&(q.bottom>limit||q.right>r.right-48||q.left<r.left+48))
                overflow.push({page:+p.dataset.page,tag:e.tagName,cls:e.className,text:e.textContent.slice(0,55),bottom:Math.round(q.bottom-r.top),limit:Math.round(limit-r.top)});
            }
          }
          return {broken,overflow,fontLoaded:document.fonts.check('400 12px Heros')&&document.fonts.check('700 12px Heros')};
        }''')
        report.update(checks)
        (HERE/'layout-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        for n in (1,2,3,5,7,9,14,15,22,23,27,29,30):
            pg.locator(f'#page-{n}').screenshot(path=str(out/f'layout-{n:02}.png'))
        if checks['broken'] or checks['overflow'] or not checks['fontLoaded']:
            raise RuntimeError(json.dumps(dict(broken=checks['broken'],overflow_pages=sorted(set(x['page'] for x in checks['overflow'])),details=checks['overflow'][:8]),ensure_ascii=False))
        (HERE/'guide.html').write_text(pg.content(),encoding='utf-8')
        if args.preview:
            browser.close();print('30-page layout validated.');return
        raw=HERE/'rendered.pdf';pg.pdf(path=str(raw),print_background=True,prefer_css_page_size=True,tagged=True)
        browser.close()
    reader=PdfReader(raw);assert len(reader.pages)==30
    writer=PdfWriter(clone_from=reader)
    writer.add_metadata({'/Title':'Mosaic — Product and Capabilities Guide','/Author':'Weirwood','/Subject':'Product purpose, government-agency workflows and complete software capabilities'})
    writer.add_outline_item('Contents',1)
    for n,p in enumerate(PAGES,3):writer.add_outline_item(p['title'],n-1)
    writer.page_mode='/UseOutlines'
    candidate=HERE/'candidate.pdf'
    with candidate.open('wb') as f:writer.write(f)
    final=PdfReader(candidate,strict=True)
    texts=[p.extract_text() for p in final.pages]
    assert all(len(t.strip())>50 for t in texts)
    assert not any('\ufffd' in t for t in texts)
    candidate.replace(OUT)
    if original_hash:
        assert hashlib.sha256(old.read_bytes()).hexdigest()==original_hash
    report.update(pages_actual=30,total_pdf_words=sum(len(t.split()) for t in texts),pdf_bytes=OUT.stat().st_size,
                  pdf_sha256=hashlib.sha256(OUT.read_bytes()).hexdigest(),original_book_unchanged=bool(original_hash and original_hash==provenance['reference_sha256']))
    (HERE/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Built {OUT}: 30 A4 pages, {report["total_pdf_words"]:,} words, {len(report["screens"])} original screenshots.')

if __name__=='__main__': main()
