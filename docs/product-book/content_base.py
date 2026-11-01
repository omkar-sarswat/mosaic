"""Build the offline, one-screenshot-per-page Mosaic product book and validate it.

Run from any directory: python docs/product-book/build.py
Requires playwright, pypdf and Pillow. Uses locally installed Chrome by default.
"""
from pathlib import Path
from collections import OrderedDict
import html
import json
import re
import hashlib
from PIL import Image
from playwright.sync_api import sync_playwright
from pypdf import PdfReader, PdfWriter
from details import ADDITIONS, EXTRAS, EXAMPLES

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'Mosaic-Product-Book.pdf'
SECTIONS = {'01':'01 · Workspace','02':'01 · Workspace','03':'02 · Cases and evidence','19':'02 · Cases and evidence',
 '04':'03 · Leads','05':'04 · Alerts','06':'05 · Watchlist','07':'06 · Network','08':'07 · Dossier','09':'08 · Money trail',
 '10':'09 · Connections','11':'10 · Map','12':'11 · Explorer','13':'12 · Data studio','14':'13 · Review matches',
 '15':'14 · Face search','16':'15 · Disaster map','17':'16 · Oversight','18':'17 · Administration'}

def para(s): return f'<p>{s}</p>' if s else ''
def header(section, title): return f'<div class="kicker">{section}</div><h1>{title}</h1>'
def footer(n):
    return f'<footer class="foot"><span class="identity"><img alt="" src="brand/weirwood-logo-512.png">WEIRWOOD · MOSAIC</span><span>PRODUCT BOOK · OCTOBER 2026</span><span class="num">{n:03}</span></footer>'
def grid(items): return '<div class="feature-grid">'+''.join(f'<div><h3>{a}</h3><p>{b}</p></div>' for a,b in items)+'</div>'
def brand(light=False):
    return f'<div class="brand"><img alt="Weirwood logo" src="brand/weirwood-logo-{"light-" if light else ""}512.png">WEIRWOOD</div>'

FRONT = [
dict(kind='cover',section='Weirwood · Mosaic',title='Mosaic'),
dict(kind='contents',section='Read the book',title='The whole product.<br>One screen at a time.'),
dict(kind='text',section='The company',title='Weirwood.<br>A clearer picture.',body='''
<p class="opening">We build software that helps investigators connect scattered records, understand relationships and keep the evidence behind every decision in view.</p>
<div class="columns"><div><h3>What we build</h3><p>Mosaic is Weirwood’s investigation and intelligence workspace for Indian public institutions. It brings people, organisations, accounts, phones, vehicles, places and events into one connected record of a case.</p><p>The work moves from an initial reference to a dossier, a network, a money trail and a report without repeatedly assembling the same facts in separate tools.</p></div>
<div><h3>Why Mosaic</h3><p>One transfer, one call or one vehicle read rarely tells the whole story. Their value grows when an investigator can put the pieces together and inspect the source of each connection.</p><p>Mosaic gives that method a workspace: search for the pieces, connect them, question them and preserve the reasoning behind the next step.</p></div>
<div><h3>Our mark</h3><p>The Weirwood tree is formed from distinct pieces. The red element gives the mark its point of emphasis: a reminder of the detail that changes how the rest of the picture is understood.</p></div>
<div><h3>Our commitment</h3><p>Make complex records readable. Keep the active case visible. Explain machine proposals. Give people explicit decisions and preserve their reasons.</p></div></div>
<div class="statement">Every record has context.<br>Every connection invites a question.<br>Every decision belongs to a person.</div>'''),
dict(kind='text',section='The problem',title='The records exist.<br>The picture takes work.',body='''
<p class="opening">Investigations cross systems. The officer has to cross them too—unless the records can be read together.</p>'''+grid([
('Scattered sources','Case records, bank statements, call records, travel bookings and vehicle reads arrive from different owners, in different formats. A relevant relationship can remain hidden between them.'),
('Names that do not line up','Scripts, spellings, initials and incomplete identifiers make exact text matching insufficient. A proposed identity link needs an explanation and a route to human review.'),
('Patterns across records','A sequence of transfers or repeated movement becomes visible only when records can be compared across time, entities and sources.'),
('Context lost in hand-offs','A lead, its approval and the evidence behind it should travel together. Separate notes and spreadsheets can detach a conclusion from the facts that support it.'),
('A report that can be checked','Reviewers need to know the source of a statement, the version exported and the handling conditions attached to the copy.'),
('Power that remains accountable','Access needs a role, a case and a purpose. Sensitive actions need reasons; oversight needs a trail that can be inspected independently.')
])+'''<div class="statement">Mosaic brings the records, the investigative tools and the decision trail into the same working context.</div>'''),
dict(kind='text',section='The product',title='From source record<br>to reviewed action.',body='''
<p class="opening">A connected workflow for preparing data, finding relationships and turning a reviewed finding into the next case action.</p>'''+grid([
('01 / Prepare','The data studio profiles an extract, suggests cleaning and field mapping, explains matching and shows proposed changes before another officer approves publication.'),
('02 / Understand','Dossiers combine the relevant record views. Search, Explorer, networks, connections, money trails and maps let the investigator ask different questions of the same case.'),
('03 / Follow','Pattern leads and typology alerts identify records worth examining. Watches and saved searches bring newly available case-relevant material back to the work queue.'),
('04 / Decide','People confirm or reject proposed matches, request cases, approve intakes and record the reasons for sensitive actions. Their decisions remain visible in the workflow.'),
('05 / Preserve','Files are sealed as exhibits, custody events are recorded and reports combine source-backed facts with the officer’s narrative.'),
('06 / Account','Access checks, handling marks, release clearances, retention and independent audit inspection connect each action to its operating context.')
])+'''<h3>The connected record</h3><p>People and organisations link to accounts, phones, vehicles, documents, locations, incidents and other objects. Each relationship carries its evidence status. Corroborated, single-source and machine-suggested links remain distinct.</p>'''),
dict(kind='text',section='The people',title='One workspace.<br>Different responsibilities.',body='''
<p class="intro">The active identity, agency and case determine what work is available. The product models agency-specific mission tracks without implying that those agencies are customers.</p>'''+grid([
('Investigating officers','Search records, examine dossiers, follow connections, create leads, seal exhibits and prepare reports within the case.'),
('Supervisors','Review eligible requests, approve another officer’s intake, authorise case-board leads and record decisions with reasons.'),
('Analysts and data stewards','Investigate relationships, compare proposed identity matches and inspect the preparation and quality of incoming records.'),
('Independent oversight','Inspect the audit trail and insider-threat alerts without receiving the investigative case-data workspace.'),
('Control-room operators','Read ingested disaster alerts, affected districts and nearby hospitals, then record resource dispatches.'),
('Administrators','Inspect the detector library, diagnostic tools and source issues. Administration is a separate responsibility from unrestricted case access.')
])+'''<h3>Agency context</h3><p>The model includes state police, cybercrime, financial-crime, narcotics, national-security and disaster-response missions. Agency and case restrictions continue to apply as the user moves between screens.</p><h3>Demonstration context</h3><p>This edition illustrates a synthetic demonstration. People, accounts and case narratives shown are demonstration records; geographic reference data and public alert material may retain real place or agency names. The screenshots are not evidence of customer deployments or operational outcomes.</p>'''),
dict(kind='text',section='Safeguards',title='Accountability is part<br>of the workflow.',body=grid([
('Purpose and scope','Personal-record requests are evaluated against the acting user, role, agency, case and permitted purpose. A graph layout or deeper visual exploration does not grant wider access.'),
('Separate decisions','Case requests, intake publication and face-match confirmation include two-person checks in their respective workflows. The actor and decision reason stay with the action.'),
('Protected values','Policy can mask fields or withhold records. An unmask request requires permission and a reason; a value never stored in full cannot be recovered by revealing it.'),
('Traceable evidence','Source references connect a displayed fact to its origin. Exhibits use cryptographic hashes and recorded custody events to support later integrity checks.'),
('Independent inspection','A hash-chained audit trail can be checked for integrity. Sealing and separately publishing a daily root creates an external reference for later verification.'),
('Controlled release and retention','Exports identify their recipient and clearance. Closed-case retention, legal holds and purge records provide distinct steps for managing case-bound data.')
])+'''<div class="statement">The software proposes and records.<br>The authorised person reviews and decides.</div><h3>Boundaries are visible</h3><p>Missing records, source limitations and uncertain matches affect the picture. The interface keeps withheld values, machine proposals and recorded facts distinguishable so that an officer can assess the evidence actually available.</p>'''),
]

PLATFORM = dict(kind='text',section='Platform',title='Built around records<br>the agency can examine.',body='''
<p class="opening">Open-source components and an explicit data model make the workspace inspectable and adaptable to the institution’s operating context.</p>'''+grid([
('Application','Mosaic combines a React and TypeScript interface with a Python FastAPI service. The repository is licensed under Apache 2.0.'),
('Storage','The application supports SQLite and PostgreSQL. Choosing the deployment topology, backup process and capacity is part of preparing an operational installation.'),
('Identity and policy','Deployment sign-in uses configured OIDC authentication, with Keycloak configuration supplied in the repository. Policy checks can use Open Policy Agent or the built-in policy implementation.'),
('Geography','Maps use the configured basemap and reference data. Local records can be examined without a public data service; external map tiles and feeds require connectivity or a suitable local service.'),
('Source preparation','Connectors and intake workflows work with the formats represented in the repository. Availability of a connector does not imply automatic access to a government source system.'),
('Operational fit','The synthetic demonstration shows workflows. Agency connections, production controls, records agreements and deployment capacity are established for the actual operating environment.')
])+'''<h3>The original record remains important</h3><p>Mosaic helps bring records together and explain their relationships. The investigator still needs to examine source quality, time, completeness and the basis for each proposed link.</p>''')

def load_screens():
    pages=json.loads((HERE/'screens.json').read_text(encoding='utf-8'))
    for image,title,text,items,example in ADDITIONS:
        pages.append(dict(kind='screen',section=SECTIONS[image[:2]],image=image,title=title,text=text,items=items,example=example))
    pages.append(dict(kind='screen',section=SECTIONS['17'],image='17-transparency',title='Transparency and retention, together.',
       text='The public transparency view presents aggregate activity by action, outcome, purpose and source. It can be read without granting access to the detailed audit trail. Authorised roles also see the retention panel.',
       items=['Due now, scheduled and on legal hold distinguish different retention states. A hold carries its reason.',
              'Administrators and supervisors can run the purge action when cases are eligible. The panel records completed purges and their manifest references.',
              'Aggregate counts describe the demonstration’s activity. They are operational summaries, not product test results or evidence of a deployment.']))
    # Keep original reading order within each chapter, then place additional views next to their parent.
    ordering={s:i for i,s in enumerate(dict.fromkeys(SECTIONS.values()))}
    after={
      '01-account-menu':'01-light-theme','01-role-refused':'01-account-menu','03-case-close':'03-case-board-5',
      '03-case-evidence':'03-case-evidence-form','03-report-editor-2':'03-report-editor','03-report-editor-3':'03-report-editor-2',
      '06-watchlist-search':'06-watch-dialog','07-network-list':'07-network','07-network-types':'07-network-list',
      '07-network-community':'07-network-analysis','08-dossier-overview-2':'08-dossier-overview',
      '08-dossier-unmask':'08-dossier-overview-2','08-dossier-network':'08-dossier-financials',
      '09-money-in':'09-money','09-money-accounts':'09-money-in','10-connect-start':None,
      '11-globe-zoom':'11-globe','11-area-panel':'11-globe-zoom','11-area-results-2':'11-area-results',
      '12-explore':None,'13-studio-changes':'13-studio-checks','13-studio-diary':'13-studio-tagging',
      '13-studio-proposed':'13-studio-diary','13-studio-review':'13-studio-proposed',
      '14-review-pair':'14-review','15-faces-empty':None,'15-faces-found':'15-faces-empty',
      '15-faces-confirm':'15-faces-candidates','16-cop-dispatch':'16-cop-flood',
      '17-oversight-filtered':'17-oversight','17-transparency':'17-oversight-filtered','18-admin-quality':'18-admin-library'}
    for key,anchor in after.items():
        item=next(p for p in pages if p['image']==key); pages.remove(item)
        if anchor: pos=next(i for i,p in enumerate(pages) if p['image']==anchor)+1
        else: pos=next(i for i,p in enumerate(pages) if p['section']==item['section'])
        pages.insert(pos,item)
    pages.sort(key=lambda p:ordering[p['section']])
    for p in pages:
        p['items'] += EXTRAS.get(p['image'],[])
        p['example']=p.get('example',EXAMPLES[p['image'][:2]])
        if p['image']=='01-overview':
            p['title']='Your day, in one workspace.'
            p['intro']='The overview connects the work queue, active case and everyday investigation tools.'
        if p['image']=='03-case-board': p['title']='The whole case on one board.'
        if p['image']=='04-leads-ncb': p['title']='A pattern, with its evidence.'
        if p['image']=='07-network': p['title']='Read the relationships.'
        if p['image']=='08-dossier-overview':
            p['title']='One person.<br>The connected record.'
            p['intro']='The dossier brings together the source records the active case may read.'
    return pages

def render_screen(p):
    title=header(p['section'],p['title'])
    intro=para(p.get('intro',''))
    picture=f'<figure class="shot"><img alt="{html.escape(re.sub("<[^>]+>","",p["title"]))}" src="shots/{p["image"]}.png"></figure>'
    controls='<div class="controls">'+''.join(f'<p class="control"><span class="number">{i:02}</span>{t}</p>' for i,t in enumerate(p['items'],1))+'</div>' if p['items'] else ''
    text=f'<div class="explanation">{para(p["text"])}</div>'
    practice=f'<div class="practice"><span class="label">In practice</span><p>{p["example"]}</p></div>'
    if p['image'].startswith('19-'):
        return title+f'<div class="portrait-shot">{picture}<div>{text}{controls}</div></div>'+practice
    return title+f'<div class="intro">{intro}</div>'+picture+'<div class="caption"><span>Mosaic · Synthetic demonstration</span><span>Original screenshot · Zoom to inspect</span></div>'+text+controls+practice

def main():
    screens=load_screens()
    pages=FRONT+screens+[PLATFORM]
    screen_index=[(p,i+1) for i,p in enumerate(pages) if p['kind']=='screen']
    for start in range(0,len(screen_index),16):
        pages.append(dict(kind='index',section='Screen index',title='Find the view you need.',entries=screen_index[start:start+16]))
    pages.append(dict(kind='back',section='Weirwood',title='Every record.<br>One clear picture.'))
    toc=OrderedDict()
    for n,p in enumerate(pages,1):
        if p['kind'] not in ('cover','contents','back'): toc.setdefault(p['section'],n)
    sections=[]
    for n,p in enumerate(pages,1):
        kind=p['kind']
        if kind=='cover':
            body=brand()+'''<div><h1>Mosaic</h1><p class="tagline">See the connections.<br>Understand the case.</p><p class="subline">The Weirwood company and product book.<br>An illustrated guide to the investigation workspace.</p></div><div class="motif" aria-hidden="true">'''+''.join('<span></span>' for _ in range(6))+'''</div><div class="meta"><span>Product book / 2026</span><span>October edition</span></div>'''
        elif kind=='contents':
            body=header(p['section'],p['title'])+'''<p class="intro">Start with the company and the problem. Then follow the workspace through its screens, tabs, dialogs and decisions. Each screenshot has its own page and a detailed explanation.</p><p>Use the linked contents or PDF bookmarks to move between chapters. The screen index at the end lists each illustrated view.</p>'''
            body+='<div class="toc">'+''.join(f'<a href="#page-{pn}"><span>{s}</span><span class="n">{pn:03}</span></a>' for s,pn in toc.items())+'</div>'
            body+='<div class="practice"><span class="label">Reading this edition</span><p>Screens show a synthetic demonstration. Original PNGs are embedded without JPEG conversion. Zoom into an image to read fine interface details. Diagnostic test-result screens are excluded; their purpose is described in the administration chapter.</p></div>'
        elif kind=='text': body=header(p['section'],p['title'])+p['body']
        elif kind=='screen': body=render_screen(p)
        elif kind=='index':
            body=header(p['section'],p['title'])+'<p class="intro">Every entry links directly to its illustrated page.</p><div class="index-list">'
            body+=''.join(f'<a class="index-row" href="#page-{pn}"><span><small>{q["section"]}</small>{q["title"]}</span><span class="n">{pn:03}</span></a>' for q,pn in p['entries'])+'</div>'
        else:
            body=brand(True)+f'<div><div class="line"></div><h1>Mosaic</h1><p>{p["title"]}</p></div><p class="edition">WEIRWOOD · MOSAIC PRODUCT BOOK<br>October 2026 · Illustrated product edition</p>'
        classes='page '+('cover' if kind=='cover' else 'back' if kind=='back' else '')
        sections.append(f'<section id="page-{n}" class="{classes}" data-page="{n}">{body}{footer(n) if kind not in ("cover","back") else ""}</section>')
    doc='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="color-scheme" content="light"><title>Mosaic — Weirwood Product Book</title><link rel="stylesheet" href="book.css"></head><body>'+''.join(sections)+'</body></html>'
    (HERE/'book.html').write_text(doc,encoding='utf-8')
    report={'pages_expected':len(pages),'screen_pages':len(screens),'chapters':dict(toc),'screens':[]}
    for p,n in screen_index:
        path=HERE/'shots'/f'{p["image"]}.png'
        with Image.open(path) as im: size=list(im.size)
        report['screens'].append(dict(page=n,title=re.sub('<[^>]+>',' ',p['title']),file=path.name,pixels=size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    with sync_playwright() as pw:
        b=pw.chromium.launch(channel='chrome')
        pg=b.new_page(viewport={'width':794,'height':1123},device_scale_factor=1)
        # The book deliberately loads no network resources.
        pg.route('http://**/*',lambda r:r.abort())
        pg.route('https://**/*',lambda r:r.abort())
        pg.goto((HERE/'book.html').as_uri(),wait_until='load')
        pg.evaluate('document.fonts.ready')
        pg.emulate_media(media='print')
        checks=pg.evaluate('''() => {
          const broken=[...document.images].filter(x=>!x.complete||!x.naturalWidth).map(x=>x.src);
          const over=[];
          for(const p of document.querySelectorAll('.page')) {
            const r=p.getBoundingClientRect(),foot=p.querySelector('.foot');
            if(!foot) continue;
            const limit=foot.getBoundingClientRect().top-12;
            for(const e of p.querySelectorAll('*')) {
              if(e.closest('.foot')) continue;
              const q=e.getBoundingClientRect();
              if(q.height && (q.bottom>limit || q.right>r.right-35 || q.left<r.left+35))
                over.push({page:p.dataset.page,element:e.tagName,text:e.textContent.slice(0,80),bottom:Math.round(q.bottom-r.top),limit:Math.round(limit-r.top),right:Math.round(q.right-r.left)});
            }
          }
          return {broken,overflow:over,fontLoaded:document.fonts.check('500 12px "Public Sans"'),htmlScreens:document.querySelectorAll('.shot').length};
        }''')
        report.update(checks)
        (HERE/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if checks['broken'] or checks['overflow'] or not checks['fontLoaded']:
            raise RuntimeError('Layout or asset validation failed: '+json.dumps(checks,ensure_ascii=False))
        raw=HERE/'rendered.pdf'
        pg.pdf(path=str(raw),print_background=True,prefer_css_page_size=True,tagged=True)
        preview=HERE/'previews';preview.mkdir(exist_ok=True)
        # Contact sheets allow every page to be checked without shrinking the actual PDF.
        thumbs=[]
        for n in range(1,len(pages)+1):
            path=preview/f'page-{n:03}.png'
            pg.locator(f'#page-{n}').screenshot(path=str(path))
            with Image.open(path) as im:
                th=im.convert('RGB');th.thumbnail((250,354));thumbs.append((n,th.copy()))
        from PIL import ImageDraw
        for start in range(0,len(thumbs),16):
            chunk=thumbs[start:start+16];sheet=Image.new('RGB',(1040,((len(chunk)+3)//4)*385),'#dedbd5');draw=ImageDraw.Draw(sheet)
            for j,(n,im) in enumerate(chunk):
                x=(j%4)*260+5;y=(j//4)*385+22;sheet.paste(im,(x,y));draw.text((x,y-17),f'Page {n:03}',fill='black')
            sheet.save(preview/f'contact-{start//16+1:02}.jpg',quality=90)
        b.close()
    reader=PdfReader(raw)
    if len(reader.pages)!=len(pages): raise RuntimeError(f'Printed page count {len(reader.pages)} != {len(pages)}')
    writer=PdfWriter(clone_from=reader)
    writer.add_metadata({'/Title':'Mosaic — Weirwood Product Book','/Author':'Weirwood','/Subject':'Company introduction and illustrated product walkthrough','/Keywords':'Mosaic, Weirwood, investigation, product book'})
    for title,n in toc.items(): writer.add_outline_item(title,n-1)
    writer.page_mode='/UseOutlines'
    with OUT.open('wb') as f: writer.write(f)
    final=PdfReader(OUT)
    text='\n'.join(p.extract_text() for p in final.pages)
    if '\ufffd' in text: raise RuntimeError('Replacement character in PDF text')
    blank=[i+1 for i,p in enumerate(final.pages) if len(p.extract_text().strip())<30]
    if blank: raise RuntimeError(f'Blank or unreadable pages: {blank}')
    report.update(pages_actual=len(final.pages),blank_pages=blank,pdf_bytes=OUT.stat().st_size,bookmarks=len(toc),pdf_sha256=hashlib.sha256(OUT.read_bytes()).hexdigest())
    (HERE/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (HERE/'coverage.md').write_text('# Illustrated screen coverage\n\n'+f'{len(screens)} screenshot pages across all 17 navigation areas. Diagnostic test-result screenshots are deliberately excluded.\n\n'+'\n'.join(f'- Page {n:03}: {p["section"]} — {re.sub("<[^>]+>"," ",p["title"])} (`{p["image"]}.png`)' for p,n in screen_index)+'\n',encoding='utf-8')
    print(f'Built {OUT}: {len(final.pages)} pages; {len(screens)} screenshot pages; {OUT.stat().st_size/1e6:.1f} MB; no layout overflow or missing assets.')

if __name__=='__main__': main()
