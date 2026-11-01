"""Reference-led A4 publication: typeset text, native diagrams, original figures."""
from pathlib import Path
from collections import OrderedDict
import argparse
import hashlib
import html
import json
import re
from PIL import Image
from pypdf import PdfReader, PdfWriter
from playwright.sync_api import sync_playwright
from content_base import load_screens
from screen_editorial import apply_editorial
from editorial_content import COMPANY, CHAPTERS
from reference_content import COMPANY_EXTRA, CHAPTER_EXTRA, SCREEN_CONTEXT
from screen_sequence import SEQUENCE

HERE=Path(__file__).resolve().parent
OUT=HERE.parent/'Mosaic-Product-Book.pdf'

def plain(value): return html.unescape(re.sub('<[^>]+>',' ',value))
def count(value): return len(plain(value).split())
def brand(): return '<span class="brand"><img src="brand/weirwood-logo-512.png" alt="Weirwood logo">WEIRWOOD</span>'
def header(label): return f'<header class="running">{brand()}<span class="running-label">{label}</span></header>'
def footer(n,label='Mosaic / Product book'): return f'<footer class="foot"><span>{label}</span><span class="folio">{n:02}</span></footer>'
def title(text): return f'<h1 class="{"long" if len(text)>31 else ""}">{text}</h1>'
def block(heading,text,num=''):
    prefix=f'<span class="subnum">{num}</span>' if num else ''
    return f'<section class="block"><h2>{prefix}{heading}</h2><p>{text}</p></section>'
def columns(blocks,section=''):
    # Balance by text length while preserving reading order within each column.
    weights=[count(t)+15 for _,t in blocks]
    split=min(range(1,len(blocks)),key=lambda i:abs(sum(weights[:i])-sum(weights[i:]))) if len(blocks)>1 else 1
    rendered=[block(a,b,f'{section}.{i}' if section else '') for i,(a,b) in enumerate(blocks,1)]
    return '<div class="text-columns"><div class="text-column">'+''.join(rendered[:split])+'</div><div class="text-column">'+''.join(rendered[split:])+'</div></div>'

def icon(name):
    shapes={
      'database':'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 10c0 4 16 4 16 0M4 15c0 4 16 4 16 0"/>',
      'lock':'<rect x="4" y="10" width="16" height="12" rx="1"/><path d="M7 10V6a5 5 0 0110 0v4M12 14v4"/>',
      'file':'<path d="M5 2h10l4 4v16H5zM15 2v5h4M8 11h8M8 15h8M8 19h6"/>',
      'network':'<circle cx="12" cy="4" r="3"/><circle cx="4" cy="19" r="3"/><circle cx="20" cy="19" r="3"/><path d="M10.5 7L5 16M13.5 7l5.5 9M7 19h10"/>',
      'shield':'<path d="M12 2L3 6v6c0 5 4 8 9 10 5-2 9-5 9-10V6zM7 12l3 3 7-7"/>',
      'server':'<rect x="5" y="2" width="14" height="20" rx="1"/><path d="M8 7h8M8 11h8M8 15h8M8 19h3"/>',
      'cloud':'<path d="M6 19a5 5 0 010-10 7 7 0 0113-1 5.5 5.5 0 010 11z"/>',
      'clock':'<circle cx="12" cy="12" r="10"/><path d="M12 5v8l5 3"/>'}
    return f'<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">{shapes[name]}</svg>'

def visual(idx):
    if idx==1:
        entries=[('Financial','Accounts, transactions and counterparties'),('Communications','Phones, call records and device links'),('People and assets','Identities, companies, vehicles and property'),('Events and places','Incidents, travel and observations')]
        return '<div class="visual"><div class="source-types">'+''.join(f'<div class="source-type"><strong>{a}</strong>{b}</div>' for a,b in entries)+'</div><div class="source-summary">The analytical task: reconcile identifiers, compare time and retain the source behind each relationship.</div></div>'
    if idx==2:
        return f'''<div class="visual"><div class="architecture"><div class="layer">{icon('database')}<strong>Source material</strong><small>Authorised extracts<br>Case records<br>Public reference data</small></div><div class="arrow">→</div><div class="layer core">{icon('network')}<strong>Mosaic record model</strong><small>Preparation and matching<br>Objects and relationships<br>Source references and policy</small></div><div class="arrow">→</div><div class="layer">{icon('file')}<strong>Working views</strong><small>Search and analysis<br>Case management<br>Evidence and reporting</small></div></div><p class="visual-caption">Conceptual product structure. Source availability and access remain subject to configuration and authority.</p></div>'''
    if idx==3:
        stages=[('Prepare records','Profile, clean and map authorised material.'),('Examine evidence','Search, compare and inspect relationships.'),('Develop the case','Coordinate leads and review proposals.'),('Record decisions','Approve, reject and preserve the reason.'),('Report and retain','Release reviewed material; manage its lifecycle.')]
        return '<div class="visual"><div class="workflow">'+''.join(f'<div class="stage"><div class="stage-number">{n}</div><strong>{a}</strong>{b}</div>' for n,(a,b) in enumerate(stages,1))+'</div><div class="workflow-note">Case context, source references and recorded activity accompany the workflow.</div></div>'
    if idx==4:
        rows=[('Investigating officer','Examine records and develop the case','Search, dossiers, leads, exhibits and reports'),('Supervisor','Review eligible requests and proposals','Approve or reject with a recorded reason'),('Analyst / steward','Examine relationships and source quality','Network analysis, matching and intake review'),('Oversight auditor','Inspect recorded system activity','Audit filters, chain verification and alerts'),('Administrator','Maintain product and source context','Detector documentation and quality issues')]
        return '<div class="visual"><table class="role-table"><thead><tr><th>Role</th><th>Responsibility</th><th>Typical work</th></tr></thead><tbody>'+''.join(f'<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>' for a,b,c in rows)+'</tbody></table></div>'
    if idx==5:
        cells=[('lock','Scoped access','Identity, role, agency, case and purpose.'),('file','Recorded decisions','Actor, reason, context and outcome.'),('shield','Evidence integrity','Exhibit fingerprints and custody events.'),('clock','Retention','Eligibility, legal holds and purge records.')]
        return '<div class="visual"><div class="control-grid">'+''.join(f'<div class="control-cell">{icon(i)}<div><strong>{a}</strong>{b}</div></div>' for i,a,b in cells)+'</div></div>'
    if idx==6:
        return f'''<div class="visual"><div class="deployment"><div>{icon('server')}<span><strong>Application environment</strong>React / TypeScript interface<br>Python FastAPI service<br>SQLite or PostgreSQL</span></div><div>{icon('network')}<span><strong>Configured integrations</strong>OIDC identity and policy<br>Permitted source extracts<br>Maps and reference services</span></div></div><p class="visual-caption">Infrastructure, capacity, connectivity and operating arrangements are established for the intended installation.</p></div>'''
    if idx==7:
        return '<div class="capability-strip"><div><strong>Company context</strong>Purpose, scope and operating model</div><div><strong>Product chapters</strong>Workflow explanations and real screens</div><div><strong>Reference access</strong>Linked contents, bookmarks and index</div></div>'
    return ''

def company(p):
    idx=p['company_index'];num=idx+1
    body=header(f'{num:02} / {p["title"]}')+f'<div class="section-number">{num:02}</div>'+title(p['title'])
    blocks=p['blocks']+[COMPANY_EXTRA[idx]]
    # The role table carries the role summaries; the prose develops operating
    # responsibilities and configuration without repeating its first two rows.
    if idx==4: blocks=blocks[2:]
    if idx==3: blocks=[(re.sub(r'^\d+\s+', '',a),b) for a,b in blocks]
    if idx==0:
        mini='<aside class="mini-contents"><strong>In this section</strong>'+''.join(f'<div>{num}.{i} &nbsp; {a}</div>' for i,(a,_) in enumerate(blocks,1))+'</aside>'
        body+='<div class="section-overview"><p class="lead">'+p['lead']+'</p>'+mini+'</div>'
    else: body+='<p class="lead">'+p['lead']+'</p>'+visual(idx)
    if idx in (2,3):
        # Narrative-first reading: compact figure, two balanced continuous columns.
        return body+'<div class="flow-columns">'+''.join(block(a,b,f'{num}.{i}') for i,(a,b) in enumerate(blocks,1))+'</div>'
    return body+columns(blocks,str(num))

def chapter(p):
    body=header(f'Product reference / {p["number"]}')+f'<div class="section-number">{p["number"]}</div>'+title(p['title'])+'<p class="lead">'+p['lead']+'</p>'
    blocks=p['blocks']+[CHAPTER_EXTRA[p['number']]]
    body+=f'<div class="capability-strip"><div><strong>Feature chapter</strong>{p["title"]}</div><div><strong>Illustrated views</strong>{p["figure_count"]} individual screens</div><div><strong>Figure range</strong>{p["first_figure"]:02}–{p["last_figure"]:02}</div></div>'
    body+=columns(blocks,p['number'])
    return body

def screen(p):
    extra=SCREEN_CONTEXT[p['image']]
    sequence=SEQUENCE.get(p['image'],'')
    p['word_count']=count(p['text']+' '+' '.join(p['items'])+' '+p['note']+' '+extra[1]+' '+sequence)
    portrait=p['image'].startswith('19-')
    p['layout']='portrait' if portrait else 'dense' if p['word_count']>200 else 'standard'
    body=header(f'{p["chapter_number"]} / {p["chapter_title"]}')+title(p['title'])+f'<p class="screen-subtitle">Figure {p["figure"]:02} / Illustrated product reference</p>'
    figure=f'<figure class="screen-figure"><img src="shots/{p["image"]}.png" alt="{html.escape(p["title"])}"><figcaption><span>Figure {p["figure"]:02} · {p["title"]}</span><span>Synthetic demonstration</span></figcaption></figure>'
    explanation=block('Purpose and operation',p['text'])
    guidance=block(*extra)
    sequence_block=block('Working sequence',sequence) if sequence else ''
    controls='<section class="block"><h2>Controls and workflow</h2><div class="control-list">'+''.join(f'<p><span class="control-number">{i:02}</span>{t}</p>' for i,t in enumerate(p['items'],1))+'</div></section>' if p['items'] else ''
    note=f'<p class="workflow-example"><strong>Example.</strong>{p["note"]}</p>' if p['note'] else ''
    if portrait:
        body+=f'<div class="portrait-layout">{figure}<div>{explanation}{sequence_block}</div></div><div class="text-columns"><div class="text-column">{guidance}</div><div class="text-column">{controls}{note}</div></div>'
    else:
        # Distribute longer control lists across columns, never shrink text to fit.
        if len(p['items'])>=4:
            split=(len(p['items'])+1)//2
            leftcontrols='<section class="block"><h2>Controls and workflow</h2><div class="control-list">'+''.join(f'<p><span class="control-number">{i:02}</span>{t}</p>' for i,t in enumerate(p['items'][:split],1))+'</div></section>'
            rightcontrols='<section class="block"><h2>Controls continued</h2><div class="control-list">'+''.join(f'<p><span class="control-number">{i:02}</span>{t}</p>' for i,t in enumerate(p['items'][split:],split+1))+'</div></section>'
            left=explanation+leftcontrols;right=rightcontrols+guidance+sequence_block+note
        else:
            left=explanation+controls;right=guidance+sequence_block+note
        body+=figure+f'<div class="text-columns"><div class="text-column">{left}</div><div class="text-column">{right}</div></div>'
    return body

def compose():
    screens=[apply_editorial(p) for p in load_screens()]
    pages=[dict(kind='cover',title='Mosaic'),dict(kind='contents',title='Contents')]
    pages.extend(dict(p,company_index=i) for i,p in enumerate(COMPANY))
    fig=0
    for q in CHAPTERS:
        p=dict(q);group=[s for s in screens if s['section'].startswith(q['number'])]
        p.update(figure_count=len(group),first_figure=fig+1,last_figure=fig+len(group));pages.append(p)
        for s in group:
            fig+=1;s.update(figure=fig,chapter_title=q['title'],chapter_number=q['number']);pages.append(s)
    screen_index=[(p,n) for n,p in enumerate(pages,1) if p['kind']=='screen']
    for start in range(0,len(screen_index),22): pages.append(dict(kind='index',title='Screen index',part=start//22+1,entries=screen_index[start:start+22]))
    pages.append(dict(kind='colophon',title='Publication information'))
    for n,p in enumerate(pages,1):p['page']=n
    return pages,screens,screen_index

def toc(pages):
    body=header('Contents')+title('Contents')
    groups=[('A','Company and product',[p for p in pages if p['kind']=='article']),('B','Product reference',[p for p in pages if p['kind']=='chapter']),('C','Reference',[next(p for p in pages if p['kind']=='index'),pages[-1]])]
    for letter,label,entries in groups:
        body+=f'<div class="toc-group"><div class="toc-heading"><span class="letter">{letter}</span><span>{label}</span><span class="n">{entries[0]["page"]:02}</span></div>'
        for i,p in enumerate(entries,1):
            body+=f'<a class="toc-row" href="#page-{p["page"]}"><span class="num">{i:02}</span><span>{p["title"]}</span><span class="n">{p["page"]:02}</span></a>'
        body+='</div>'
    return body+'<p class="toc-note">Select an entry to open its chapter. PDF bookmarks also link to individual figures.</p>'

def colophon():
    blocks=[
    ('Publication', 'Mosaic: Company and product book. Weirwood, October 2026. Reference-led A4 edition. The publication contains eight company and product sections, 17 feature introductions and 88 individually explained screenshots. All investigative identities and scenarios shown belong to the synthetic demonstration.'),
    ('Product material', 'The descriptions are based on the inspected application and available source. Original screenshots are embedded at their source pixel dimensions. Diagnostic test-result screenshots and benchmark tables are excluded. Geographic references and public alert material can retain real names; their presence does not imply a deployment or customer relationship.'),
    ('Typography and production', 'The document is typeset in TeX Gyre Heros, used under the GUST Font License included with the source. Text remains selectable, diagrams are native vector or layout elements and navigation links are embedded in the PDF. The accompanying source contains the original figures, editable content, layout rules and reproducible build scripts.'),
    ('Cover illustration', 'The cover city image was generated with OpenAI’s built-in image-generation tool for this publication. The red network is a conceptual illustration, not a representation of an operational monitoring system. The company logo and all product screenshots are supplied assets. The image-generation prompt is included in the source package.'),
    ('Editorial references', '<a href="https://www.lars-mueller-publishers.com/neue-grafiknew-graphic-designgraphisme-actuel-1958-1965">Neue Grafik, Lars Müller Publishers</a>; <a href="https://www.swisstypefaces.com/media/ul/fonts/pdf/2020-11-26_swisstypefaces_Suisse.pdf">Suisse technical documentation, Swiss Typefaces</a>; <a href="https://niggli.ch/en/products/der-typografische-raster">The Typographic Grid, Hans Rudolf Bosshard / Niggli</a>; and <a href="https://www.nasa.gov/wp-content/uploads/2015/01/nasa_graphics_manual_nhb_1430-2_jan_1976.pdf">NASA Graphics Standards Manual, 1976</a>. The user-provided nine-page visual reference determined this edition’s portrait composition, compact headers and red section markers.'),
    ('Source and review', 'The source package includes the full research notes and production validation. Reference publications are linked rather than redistributed. Each delivered page is checked for text overflow, missing assets and original screenshot dimensions, and the final PDF is independently rendered for review. These production checks remain outside the product explanations.')]
    return header('Publication information')+'<div class="section-number">Reference</div>'+title('Publication information')+'<p class="lead">Weirwood / Mosaic<br>Company and product book · October 2026</p>'+columns(blocks)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--preview',action='store_true');args=parser.parse_args()
    pages,screens,screen_index=compose();sections=[]
    for p in pages:
        kind=p['kind'];n=p['page']
        if kind=='cover':
            body='<img class="cover-panel" src="assets/cover-city-network.png" alt="Conceptual city and record network illustration"><div class="cover-left">'+brand()+'''<h1>Mosaic</h1><p class="descriptor">Investigation and intelligence workspace</p><div class="red-rule"></div><p class="positioning">Connected records.<br>Structured investigation.<br>Accountable decisions.</p><div class="cover-meta">Company and product book<br>Reference edition<br>October 2026</div></div><div class="panel-label">Investigate<br>Understand<br>Review</div>'''
        elif kind=='contents':body=toc(pages)
        elif kind=='article':body=company(p)
        elif kind=='chapter':body=chapter(p)
        elif kind=='screen':body=screen(p)
        elif kind=='index':
            body=header(f'Reference / Screen index {p["part"]:02}')+title('Screen index')+'<p class="index-intro">Select a view to open its illustrated explanation.</p><div class="index-rows">'
            for q,pn in p['entries']:body+=f'<a class="index-row" href="#page-{pn}"><span class="figure">{q["figure"]:02}</span><span>{q["title"]}<small>{q["chapter_number"]} / {q["chapter_title"]}</small></span><span class="n">{pn:02}</span></a>'
            body+='</div>'
        else:body=colophon()
        cls=('company'+(' overview' if p.get('company_index')==0 else '')) if kind=='article' else kind
        if kind=='screen':cls+=' '+p['layout']
        sections.append(f'<article class="page {cls}" id="page-{n}" data-page="{n}">{body}{footer(n) if kind!="cover" else ""}</article>')
    doc='<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Mosaic — Weirwood Company and Product Book</title><link rel="stylesheet" href="reference.css"></head><body>'+''.join(sections)+'</body></html>'
    (HERE/'book-reference.html').write_text(doc,encoding='utf-8')
    report={'edition':'Reference-led A4 portrait edition','page_mm':[210,297],'pages_expected':len(pages),'screen_pages':len(screens),'chapters':{p['title']:p['page'] for p in pages if p['kind'] in ('article','chapter')},'screens':[]}
    for p,n in screen_index:
        asset=HERE/'shots'/f'{p["image"]}.png'
        with Image.open(asset) as im:sz=list(im.size)
        report['screens'].append(dict(page=n,figure=p['figure'],title=p['title'],file=asset.name,pixels=sz,sha256=hashlib.sha256(asset.read_bytes()).hexdigest(),words=p['word_count']))
    previews=HERE/'previews/reference';previews.mkdir(parents=True,exist_ok=True)
    representatives=[1,2,3,4,5,6,7,8,9,10,11,12,21,22,30,36,37,39,52,67,90,110,116,120]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='chrome')
        pg=browser.new_page(viewport={'width':794,'height':1123},device_scale_factor=1.5)
        pg.route('http://**/*',lambda r:r.abort());pg.route('https://**/*',lambda r:r.abort())
        pg.goto((HERE/'book-reference.html').as_uri(),wait_until='load');pg.evaluate('document.fonts.ready');pg.emulate_media(media='print')
        # Choose a column break from actual font metrics. Reading order remains
        # down the left column, then down the right. No type scaling is applied.
        pg.evaluate('''() => {
          for(const row of document.querySelectorAll('.screen:not(.portrait) .text-columns')) {
            const cols=[...row.children],atoms=cols.flatMap(c=>[...c.children]);
            if(atoms.length<3)continue;
            let best=1,height=Infinity;
            for(let split=1;split<atoms.length;split++) {
              cols[0].replaceChildren(...atoms.slice(0,split));cols[1].replaceChildren(...atoms.slice(split));
              const value=Math.max(cols[0].getBoundingClientRect().height,cols[1].getBoundingClientRect().height);
              if(value<height){height=value;best=split;}
            }
            cols[0].replaceChildren(...atoms.slice(0,best));cols[1].replaceChildren(...atoms.slice(best));
          }
        }''')
        checks=pg.evaluate('''() => {
          const broken=[...document.images].filter(x=>!x.complete||!x.naturalWidth).map(x=>x.src), overflow=[];
          for(const p of document.querySelectorAll('.page')) {
            if(p.classList.contains('cover'))continue;
            const r=p.getBoundingClientRect(),limit=p.querySelector('.foot').getBoundingClientRect().top-12;
            for(const e of p.querySelectorAll('*')) {
              if(e.closest('.foot')||e.closest('svg'))continue;
              const q=e.getBoundingClientRect();
              if(q.height&&(q.bottom>limit||q.right>r.right-48||q.left<r.left+48))
                overflow.push({page:+p.dataset.page,tag:e.tagName,cls:e.className,text:e.textContent.slice(0,65),bottom:Math.round(q.bottom-r.top),limit:Math.round(limit-r.top)});
            }
          }
          return {broken,overflow,fontLoaded:document.fonts.check('400 12px Heros')&&document.fonts.check('700 12px Heros'),one_image_per_screen:[...document.querySelectorAll('.screen')].every(p=>p.querySelectorAll('.screen-figure img').length===1)};
        }''')
        report.update(checks)
        for n in representatives:
            if n<=len(pages):pg.locator(f'#page-{n}').screenshot(path=str(previews/f'page-{n:03}.png'))
        (HERE/'validation-reference.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if checks['broken'] or checks['overflow'] or not checks['fontLoaded']:
            print(json.dumps({'broken':checks['broken'],'overflow_pages':sorted(set(x['page'] for x in checks['overflow'])),'details':[x for x in checks['overflow'] if x['cls'] in ('text-columns','flow-columns','index-rows','portrait-layout')]},ensure_ascii=False,indent=2));raise RuntimeError('Page validation failed')
        if args.preview:
            print(f'Preview validated: {len(pages)} A4 pages, 88 original screenshots.');browser.close();return
        # Persist the same balanced reading layout used in the PDF for offline review.
        (HERE/'book-reference.html').write_text(pg.content(),encoding='utf-8')
        raw=HERE/'rendered-reference.pdf'
        pg.pdf(path=str(raw),print_background=True,prefer_css_page_size=True,tagged=True)
        browser.close()
    reader=PdfReader(raw);assert len(reader.pages)==len(pages)
    writer=PdfWriter(clone_from=reader)
    writer.add_metadata({'/Title':'Mosaic — Weirwood Company and Product Book','/Author':'Weirwood','/Subject':'Company, product capabilities and illustrated operating workflows','/Keywords':'Mosaic, Weirwood, investigation, intelligence, product book'})
    for q in pages:
        if q['kind'] in ('article','chapter'):
            parent=writer.add_outline_item(q['title'],q['page']-1)
            if q['kind']=='chapter':
                for p,n in screen_index:
                    if p['chapter_number']==q['number']:writer.add_outline_item(f'{p["figure"]:02} / {p["title"]}',n-1,parent=parent)
    writer.add_outline_item('Screen index',next(p['page']-1 for p in pages if p['kind']=='index'))
    writer.add_outline_item('Publication information',len(pages)-1);writer.page_mode='/UseOutlines'
    with OUT.open('wb') as f:writer.write(f)
    final=PdfReader(OUT);texts=[p.extract_text() for p in final.pages]
    assert all(len(t.strip())>30 for t in texts)
    assert not any('\ufffd' in t for t in texts)
    report.update(pages_actual=len(final.pages),pdf_bytes=OUT.stat().st_size,pdf_sha256=hashlib.sha256(OUT.read_bytes()).hexdigest(),total_pdf_words=sum(len(t.split()) for t in texts),blank_pages=[])
    (HERE/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (HERE/'page-manifest.json').write_text(json.dumps([{'page':p['page'],'kind':p['kind'],'title':p['title']} for p in pages],indent=2),encoding='utf-8')
    (HERE/'coverage.md').write_text('# Illustrated screen coverage\n\n88 original screenshot pages across 17 product chapters.\n\n'+'\n'.join(f'- Page {n:03}, figure {p["figure"]:02}: {p["chapter_title"]} — {p["title"]} (`{p["image"]}.png`)' for p,n in screen_index),encoding='utf-8')
    print(f'Built {OUT}: {len(pages)} A4 pages; {report["total_pdf_words"]:,} words; {OUT.stat().st_size/1e6:.1f} MB.')

if __name__=='__main__':main()
