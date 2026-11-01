"""Build and validate the A4 portrait edition of the Mosaic product book."""
from pathlib import Path
import argparse
import hashlib
import html
import json
import re
from collections import OrderedDict
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright
from pypdf import PdfReader, PdfWriter
from content_base import load_screens
from editorial_content import COMPANY, CHAPTERS
from screen_editorial import apply_editorial

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'Mosaic-Product-Book.pdf'

def plain(s):
    return html.unescape(re.sub('<[^>]+>', '', s))

def footer(n, label='Company and product overview'):
    return f'<footer class="foot"><span>WEIRWOOD / MOSAIC</span><span class="middle">{label}</span><span class="folio">{n:03}</span></footer>'

def header(label, title, right='Product documentation'):
    long=' long' if len(plain(title))>38 else ''
    return f'<div class="running"><span class="imprint">Weirwood / Mosaic</span><span>{label}</span><span>{right}</span></div><h1 class="page-title{long}">{title}</h1>'

def block(pair):
    return f'<div class="block"><h2>{pair[0]}</h2><p>{pair[1]}</p></div>'

def article(p):
    ischapter=p['kind']=='chapter'
    label=f'Chapter {p["number"]}' if ischapter else p['label']
    result=header(label,p['title'])
    if ischapter: result+=f'<div class="chapter-num">{p["number"]}</div>'
    lead=f'<div><div class="article-label">{"Purpose and scope" if ischapter else "Overview"}</div><p class="lead">{p["lead"]}</p>'
    if ischapter:
        lead+=f'<div class="scope">Illustrated reference<br>{p["figure_count"]} views · Figures {p["first_figure"]:02}–{p["last_figure"]:02}</div>'
    lead+='</div>'
    if ischapter:
        body=''.join(block(b) for b in p['blocks'])
    else:
        middle=(len(p['blocks'])+1)//2
        body='<div>'+''.join(block(b) for b in p['blocks'][:middle])+'</div><div>'+''.join(block(b) for b in p['blocks'][middle:])+'</div>'
    return result+f'<div class="article-grid">{lead}<div class="article-body">{body}</div></div>'

def control(t, i):
    return f'<p class="control"><span class="number">{i:02}</span>{t}</p>'

def render_screen(p):
    n=p['figure']
    lead=p['text']
    controls=p['items']
    words=len(plain(lead+' '+' '.join(controls)).split())
    portrait=p['image'].startswith('19-')
    dense=not portrait and (words>190 or len(controls)>5)
    p['layout']='portrait' if portrait else 'dense' if dense else 'standard'
    content=header(p['chapter_title'], p['title'], f'Figure {n:02}')
    figure=f'<figure><img class="figure-image" alt="{html.escape(p["title"])}" src="shots/{p["image"]}.png"><figcaption class="figure-caption"><span>Figure {n:02} / {p["title"]}</span><span>Synthetic demonstration</span></figcaption></figure>'
    aside=f'<div class="annotation-label">Screen explanation</div><p>{lead}</p>' if lead else ''
    split=3 if dense else len(controls)
    if controls: aside+='<div class="control-list">'+''.join(control(t,i) for i,t in enumerate(controls[:split],1))+'</div>'
    note=f'<div class="operation-note"><span class="label">Workflow example</span><p>{p["note"]}</p></div>' if p['note'] else ''
    under='<div class="under-controls">'+''.join(control(t,i) for i,t in enumerate(controls[split:],split+1))+'</div>' if dense else ''
    if portrait: aside+=note; note=''
    content+=f'<div class="figure-layout"><div>{figure}{under}{note}</div><div class="annotation">{aside}</div></div>'
    return content

def compose():
    screens=[apply_editorial(p) for p in load_screens()]
    pages=[dict(kind='cover',title='Mosaic'),dict(kind='contents',title='Contents')]+[dict(p) for p in COMPANY]
    fig=0
    for source in CHAPTERS:
        chapter=dict(source)
        group=[p for p in screens if p['section'].startswith(chapter['number'])]
        chapter.update(figure_count=len(group),first_figure=fig+1,last_figure=fig+len(group))
        pages.append(chapter)
        for p in group:
            fig+=1
            p.update(figure=fig,chapter_title=chapter['title'],chapter_number=chapter['number'])
            pages.append(p)
    screen_index=[(p,n) for n,p in enumerate(pages,1) if p['kind']=='screen']
    for start in range(0,len(screen_index),22):
        pages.append(dict(kind='index',title='Screen index',entries=screen_index[start:start+22],part=start//22+1))
    pages.append(dict(kind='colophon',title='Publication information'))
    for n,p in enumerate(pages,1): p['page']=n
    return pages,screens,screen_index

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--preview',action='store_true',help='Validate HTML and render representative pages without replacing the PDF')
    args=parser.parse_args()
    pages,screens,screen_index=compose()
    contents=[p for p in pages if p['kind'] in ('article','chapter')]
    first_index=next(p['page'] for p in pages if p['kind']=='index')
    sections=[]
    for p in pages:
        n=p['page'];kind=p['kind']
        if kind=='cover':
            body='''<div class="cover-brand"><img src="brand/weirwood-logo-512.png" alt="Weirwood logo"><span>WEIRWOOD</span></div><div class="edition">Product publication / October 2026</div><h1>Mosaic</h1><p class="cover-subtitle">Investigation and intelligence workspace</p><span class="cover-red"></span><div class="cover-description"><p>Company and product overview</p><p>A detailed guide to the operating model, analytical capabilities and institutional controls of Mosaic.</p></div><figure class="cover-figure"><img src="shots/07-network.png" alt="Mosaic network workspace"><figcaption>Network workspace / Synthetic demonstration</figcaption></figure>'''
        elif kind=='contents':
            body=header('Document navigation','Contents','October 2026')
            intro='<div class="contents-intro"><p>Company context, product explanation and illustrated reference.</p><p class="contents-note">Each feature chapter begins with its purpose and operating workflow. Figure pages then explain the associated screens and controls.<br><br>Use the linked entries, PDF bookmarks or screen index to navigate.</p></div>'
            def row(q):
                prefix=f'<span class="toc-number">{q["number"]}</span>' if q['kind']=='chapter' else ''
                return f'<a class="toc-row" href="#page-{q["page"]}"><span>{prefix}{q["title"]}</span><span class="num">{q["page"]:03}</span></a>'
            col1='<div class="toc-column"><p class="toc-label">Company and product</p>'+''.join(row(q) for q in contents[:8])+'<p class="toc-label" style="margin-top:7mm">Illustrated product reference</p>'+''.join(row(q) for q in contents[8:12])+'</div>'
            col2='<div class="toc-column"><p class="toc-label">Illustrated product reference</p>'+''.join(row(q) for q in contents[12:])+f'<a class="toc-row" href="#page-{first_index}"><span>Screen index</span><span class="num">{first_index:03}</span></a></div>'
            body+='<div class="contents-grid">'+intro+col1+col2+'</div>'
        elif kind in ('article','chapter'): body=article(p)
        elif kind=='screen': body=render_screen(p)
        elif kind=='index':
            body=header('Reference navigation','Screen index',f'Part {p["part"]:02} / 04')
            intro='<div class="index-intro"><p>Direct access to every illustrated view.</p><p class="contents-note">Each entry links to its figure page. Chapter introductions provide the operating context and explain how the individual views relate to one another.</p></div>'
            rows=''.join(f'<a class="index-row" href="#page-{pn}"><span><small>FIGURE {q["figure"]:02} / CHAPTER {q["chapter_number"]}</small>{q["title"]}</span><span class="num">{pn:03}</span></a>' for q,pn in p['entries'])
            body+='<div class="index-layout">'+intro+'<div class="index-rows">'+rows+'</div></div>'
        else:
            body=header('Publication record','Publication information','Revised edition')+'''<div class="article-grid"><div><div class="article-label">Weirwood / Mosaic</div><p class="lead">Company and product overview.<br><br>October 2026<br>Revised editorial edition</p></div><div class="article-body"><div><div class="block"><h2>Editorial basis</h2><p>Descriptions are based on the inspected Mosaic application and its demonstration workflows. The publication includes 17 feature chapters and 88 individually explained screen views. Diagnostic test-result screenshots are excluded.</p></div><div class="block"><h2>Design and reproduction</h2><p>The A4 portrait format uses a consistent column grid, restrained colour and TeX Gyre Heros typography. Original screenshots retain their pixel dimensions. The editable source includes the text, layout, figures, build scripts and validation record.</p></div><div class="block"><h2>Typeface</h2><p>TeX Gyre Heros is used under the GUST Font License, included with the source. Its use does not imply an affiliation with the reference publishers.</p></div></div><div class="source-list"><h2>Selected design references</h2><p><a href="https://www.lars-mueller-publishers.com/neue-grafiknew-graphic-designgraphisme-actuel-1958-1965">Neue Grafik, 1958–1965</a><br>Lars Müller Publishers. Editorial alignment, image scale and modular composition.</p><p><a href="https://www.swisstypefaces.com/media/ul/fonts/pdf/2020-11-26_swisstypefaces_Suisse.pdf">Suisse technical documentation</a><br>Swiss Typefaces. Typographic hierarchy and technical annotation.</p><p><a href="https://niggli.ch/en/products/der-typografische-raster">The Typographic Grid</a><br>Hans Rudolf Bosshard, Niggli. Shared proportions across varied page structures.</p><p><a href="https://www.nasa.gov/wp-content/uploads/2015/01/nasa_graphics_manual_nhb_1430-2_jan_1976.pdf">Graphics Standards Manual, 1976</a><br>NASA. Supporting reference for formal institutional documentation.</p><p>The research notes in the source package record the full reference study. Reference publications are not redistributed with the book.</p></div></div></div>'''
        classes='page '+kind+(' '+p.get('layout','') if kind=='screen' else '')
        label=p.get('chapter_title','Company and product overview')
        sections.append(f'<section class="{classes}" id="page-{n}" data-page="{n}">{body}{footer(n,label)}</section>')
    doc='<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Mosaic — Weirwood Company and Product Overview</title><link rel="stylesheet" href="swiss.css"></head><body>'+''.join(sections)+'</body></html>'
    (HERE/'book.html').write_text(doc,encoding='utf-8')
    report={'edition':'A4 portrait editorial edition','page_mm':[210,297],'pages_expected':len(pages),'screen_pages':len(screens),'chapters':{q['title']:q['page'] for q in contents},'screens':[]}
    for p,n in screen_index:
        path=HERE/'shots'/f'{p["image"]}.png'
        with Image.open(path) as im: size=list(im.size)
        report['screens'].append(dict(page=n,figure=p['figure'],title=p['title'],file=path.name,pixels=size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),layout=p['layout']))
    representative=[1,2,3,5,11,12,21,30,52,67,90,110,116,120]
    with sync_playwright() as pw:
        b=pw.chromium.launch(channel='chrome')
        pg=b.new_page(viewport={'width':794,'height':1123},device_scale_factor=1)
        pg.route('http://**/*',lambda r:r.abort());pg.route('https://**/*',lambda r:r.abort())
        pg.goto((HERE/'book.html').as_uri(),wait_until='load')
        pg.evaluate('document.fonts.ready');pg.emulate_media(media='print')
        checks=pg.evaluate('''() => {
          const broken=[...document.images].filter(x=>!x.complete||!x.naturalWidth).map(x=>x.src), over=[];
          for(const p of document.querySelectorAll('.page')) {
            const r=p.getBoundingClientRect(), limit=p.querySelector('.foot').getBoundingClientRect().top-16;
            for(const e of p.querySelectorAll('*')) {
              if(e.closest('.foot')) continue;
              const q=e.getBoundingClientRect();
              if(q.height && (q.bottom>limit || q.right>r.right-48 || q.left<r.left+48))
                over.push({page:p.dataset.page,element:e.tagName,cls:e.className,text:e.textContent.slice(0,75),bottom:Math.round(q.bottom-r.top),limit:Math.round(limit-r.top)});
            }
          }
          const imageCounts=[...document.querySelectorAll('.screen')].map(p=>p.querySelectorAll('.figure-image').length);
          return {broken,overflow:over,fontLoaded:document.fonts.check('400 12px Heros')&&document.fonts.check('700 12px Heros'),one_image_per_screen:imageCounts.every(x=>x===1),htmlScreens:imageCounts.length};
        }''')
        report.update(checks)
        preview=HERE/'previews/swiss';preview.mkdir(parents=True,exist_ok=True)
        for n in representative:
            if n<=len(pages): pg.locator(f'#page-{n}').screenshot(path=str(preview/f'page-{n:03}.png'))
        (HERE/'validation-swiss.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if checks['broken'] or checks['overflow'] or not checks['fontLoaded']:
            print(json.dumps(checks,ensure_ascii=False,indent=2))
            raise RuntimeError('Layout or asset check failed; see validation-swiss.json')
        if args.preview:
            print(f'Preview ready: {len(pages)} pages; {len(screens)} figures; no overflow.');b.close();return
        raw=HERE/'rendered-swiss.pdf'
        pg.pdf(path=str(raw),print_background=True,prefer_css_page_size=True,tagged=True)
        b.close()
    reader=PdfReader(raw)
    assert len(reader.pages)==len(pages),(len(reader.pages),len(pages))
    writer=PdfWriter(clone_from=reader)
    writer.add_metadata({'/Title':'Mosaic — Weirwood Company and Product Overview','/Author':'Weirwood','/Subject':'Company, operating model and illustrated product reference','/Keywords':'Mosaic, Weirwood, investigation, intelligence, product documentation'})
    for q in contents:
        label=(q['number']+' / ' if q['kind']=='chapter' else '')+q['title']
        parent=writer.add_outline_item(label,q['page']-1)
        if q['kind']=='chapter':
            for p,n in screen_index:
                if p['chapter_number']==q['number']: writer.add_outline_item(f'{p["figure"]:02} / {p["title"]}',n-1,parent=parent)
    writer.add_outline_item('Screen index',first_index-1)
    writer.add_outline_item('Publication information',len(pages)-1)
    writer.page_mode='/UseOutlines'
    with OUT.open('wb') as f:writer.write(f)
    final=PdfReader(OUT)
    texts=[p.extract_text() for p in final.pages]
    assert not any('\ufffd' in t for t in texts),'Replacement characters in PDF'
    blank=[i+1 for i,t in enumerate(texts) if len(t.strip())<30]
    assert not blank,blank
    report.update(pages_actual=len(final.pages),blank_pages=blank,pdf_bytes=OUT.stat().st_size,pdf_sha256=hashlib.sha256(OUT.read_bytes()).hexdigest(),narrative_words=sum(len(plain(p.get('lead','')+' '+' '.join(a+' '+b for a,b in p.get('blocks',[]))).split()) for p in pages),total_pdf_words=sum(len(t.split()) for t in texts))
    (HERE/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (HERE/'coverage.md').write_text('# Illustrated screen coverage\n\n88 figure pages across 17 chapters. All figures retain original PNG dimensions. Diagnostic test-result screens are excluded.\n\n'+'\n'.join(f'- Page {n:03} · Figure {p["figure"]:02}: {p["chapter_title"]} — {p["title"]} (`{p["image"]}.png`)' for p,n in screen_index)+'\n',encoding='utf-8')
    print(f'Built {OUT}: {len(final.pages)} pages; {len(screens)} figures; {report["total_pdf_words"]:,} extracted words; {OUT.stat().st_size/1e6:.1f} MB.')

if __name__=='__main__':main()
