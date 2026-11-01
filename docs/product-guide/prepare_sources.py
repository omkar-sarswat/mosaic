"""Copy approved assets into this independent publication without editing the book."""
import hashlib
import json
import shutil
from pathlib import Path
from content import PAGES, coverage_page

HERE=Path(__file__).resolve().parent
BOOK=HERE.parent/'product-book'

def prepare():
    for folder in ('shots','brand','assets','fonts'):
        (HERE/folder).mkdir(exist_ok=True)
    assets=[('brand','weirwood-logo-512.png'),('assets','cover-city-network.png')]
    assets += [('fonts',n) for n in ('heros-regular.otf','heros-bold.otf','GUST-FONT-LICENSE.txt')]
    assets += [('shots',p['image']+'.png') for p in PAGES if p['image']]
    for folder,name in assets:
        shutil.copy2(BOOK/folder/name,HERE/folder/name)
    shutil.copy2(BOOK/'reference.css',HERE/'reference.css')
    original=json.loads((BOOK/'validation.json').read_text(encoding='utf-8'))
    inventory=[]
    for s in original['screens']:
        owner=coverage_page(Path(s['file']).stem)
        assert 3<=owner<=len(PAGES)+2
        inventory.append(dict(workflow=s['title'],reference_page=s['page'],reference_image=s['file'],
                              guide_page=owner,guide_section=PAGES[owner-3]['title']))
    assert len(inventory)==88
    (HERE/'coverage.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    book_pdf=HERE.parent/'Mosaic-Product-Book.pdf'
    provenance=dict(reference_pdf='Mosaic-Product-Book.pdf',
                    reference_sha256=hashlib.sha256(book_pdf.read_bytes()).hexdigest(),
                    description='Approved product book and selected-entity graph revision; source assets copied without alteration.',
                    prepared_date='2026-10-22')
    (HERE/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    print(f'Copied {len(assets)} approved assets; mapped {len(inventory)} workflows to {len(PAGES)+2} guide pages.')

if __name__=='__main__': prepare()
