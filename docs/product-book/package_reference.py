"""Package only the current edition and its used assets; exclude research PDFs."""
from pathlib import Path
import importlib.metadata
import json
import shutil
import zipfile
from PIL import Image,ImageDraw,ImageFont
from pypdf import PdfReader,PdfWriter
from pypdf.generic import NameObject

HERE=Path(__file__).resolve().parent
DOCS=HERE.parent
report=json.loads((HERE/'validation.json').read_text(encoding='utf-8'))
assert report['pages_actual']==120 and report['pages_rendered']==120
assert report['original_screenshot_dimensions_preserved'] and report['strict_pdf_parse']

requirements=[]
for dist in ('playwright','pypdf','Pillow','pypdfium2'):
    requirements.append(dist+'=='+importlib.metadata.version(dist))
(HERE/'requirements.txt').write_text('\n'.join(requirements)+'\n',encoding='utf-8')

previews=HERE/'previews/final-pdf'
sheet=Image.new('RGB',(1458,2088),'#c7d1d6')
draw=ImageDraw.Draw(sheet)
for index,n in enumerate(range(1,10)):
    with Image.open(previews/f'page-{n:03}.png') as source:
        im=source.convert('RGB');im.thumbnail((470,665),Image.Resampling.LANCZOS)
        x=12+(index%3)*482;y=12+(index//3)*692
        sheet.paste(im,(x,y))
        draw.text((x,y+670),f'{n:02} / '+['Cover','Contents','Company overview','Institutional problem','Product architecture','Operating workflow','Roles and responsibilities','Information integrity','Deployment and integration'][index],fill='#34424a')
sheet.save(DOCS/'Mosaic-Product-Book-Preview.jpg',quality=94,subsampling=0)

reader=PdfReader(DOCS/'Mosaic-Product-Book.pdf')
preview=PdfWriter()
for p in reader.pages[:12]:
    page=preview.add_page(p)
    # The short preview does not include every destination in the full contents.
    if '/Annots' in page: del page[NameObject('/Annots')]
preview.add_metadata({'/Title':'Mosaic — Opening pages preview','/Author':'Weirwood'})
with (DOCS/'Mosaic-Product-Book-Preview.pdf').open('wb') as f:preview.write(f)

# A compact review copy contains exactly the pages whose figures were retaken.
retakes=json.loads((HERE/'graph-recapture.json').read_text(encoding='utf-8'))
retaken={s['image']+'.png' for s in retakes['screens']}
review=PdfWriter()
for s in report['screens']:
    if s['file'] not in retaken: continue
    page=review.add_page(reader.pages[s['page']-1])
    if '/Annots' in page: del page[NameObject('/Annots')]
    review.add_outline_item(f"Page {s['page']} / {s['title']}",len(review.pages)-1)
assert len(review.pages)==16
review.add_metadata({'/Title':'Mosaic — Revised graph and light-mode pages','/Author':'Weirwood'})
with (DOCS/'Mosaic-Graph-Review.pdf').open('wb') as f:review.write(f)

source_files=['build.py','build_reference.py','package_reference.py','verify_pdf.py','reference.css','editorial_content.py','reference_content.py','screen_editorial.py','screen_sequence.py','content_base.py','screens.json','details.py','book-reference.html','README.md','RESEARCH.md','coverage.md','page-manifest.json','validation.json','graph-recapture.json','requirements.txt']
assets=[HERE/f for f in source_files]
assets += [HERE/'shots'/s['file'] for s in report['screens']]
assets += [HERE/'brand'/'weirwood-logo-512.png']
assets += list((HERE/'assets').glob('*'))
assets += [HERE/'fonts'/name for name in ('heros-regular.otf','heros-bold.otf','GUST-FONT-LICENSE.txt')]
assets += list(previews.glob('contact-*.jpg'))
target=DOCS/'Mosaic-Product-Book-Source.zip'
with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for path in sorted(set(assets)):
        assert path.is_file(),path
        z.write(path,Path('product-book')/path.relative_to(HERE))
    z.write(DOCS/'Mosaic-Product-Book-Preview.jpg','Mosaic-Product-Book-Preview.jpg')
    z.write(DOCS/'Mosaic-Graph-Review.pdf','Mosaic-Graph-Review.pdf')
with zipfile.ZipFile(target) as z:
    assert z.testzip() is None
    assert not any('/research/' in name or 'admin-tests' in name for name in z.namelist())
print(f'Packaged {len(assets)} assets. Source: {target.stat().st_size/1e6:.1f} MB. Preview image and 12-page PDF created.')
