"""Independently render and validate the separate product guide."""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw
from pypdf import PdfReader
import pypdfium2 as pdfium

HERE=Path(__file__).resolve().parent

def main():
    report=json.loads((HERE/'validation.json').read_text(encoding='utf-8'))
    path=HERE.parent/'Mosaic-Product-Guide.pdf'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==report['pdf_sha256']
    reader=PdfReader(path,strict=True)
    assert len(reader.pages)==report['pages_actual']==30
    refs={p.indirect_reference.idnum for p in reader.pages}
    links=0
    for i,p in enumerate(reader.pages,1):
        assert abs(float(p.mediabox.width)-595.276)<1
        assert abs(float(p.mediabox.height)-841.89)<1
        assert len(p.extract_text().split())>20
        for ref in p.get('/Annots',[]):
            a=ref.get_object();dest=a.get('/Dest') or a.get('/A',{}).get('/D')
            if dest:
                if isinstance(dest,str): assert dest in reader.named_destinations
                else: assert dest[0].idnum in refs
                links+=1
    assert links==28, links
    exact=0
    for s in report['screens']:
        source=HERE/'shots'/s['file']
        assert hashlib.sha256(source.read_bytes()).hexdigest()==s['sha256']
        with Image.open(source) as original:
            original=original.convert('RGB')
            matches=[im.image for im in reader.pages[s['page']-1].images if list(im.image.size)==s['pixels']]
            assert matches, (s['page'],'Screenshot dimensions changed')
            assert any(im.convert('RGB').tobytes()==original.tobytes() for im in matches), (s['page'],'Screenshot pixels changed')
            exact+=1
    provenance=json.loads((HERE/'provenance.json').read_text())
    book=HERE.parent/provenance['reference_pdf']
    if book.exists():
        assert hashlib.sha256(book.read_bytes()).hexdigest()==provenance['reference_sha256'], 'Original book changed'
    dest=HERE/'previews'/'final';dest.mkdir(parents=True,exist_ok=True)
    pdf=pdfium.PdfDocument(str(path));thumbs=[]
    for i in range(len(pdf)):
        p=pdf[i];bitmap=p.render(scale=1.5);im=bitmap.to_pil().convert('RGB')
        assert im.getextrema()!=((255,255),(255,255),(255,255))
        im.save(dest/f'page-{i+1:02}.png')
        im.thumbnail((250,354));thumbs.append((i+1,im.copy()))
        bitmap.close();p.close()
    pdf.close()
    for start in range(0,len(thumbs),12):
        chunk=thumbs[start:start+12]
        sheet=Image.new('RGB',(1040,((len(chunk)+3)//4)*380),'#d5dcdf');draw=ImageDraw.Draw(sheet)
        for j,(n,im) in enumerate(chunk):
            x=(j%4)*260+5;y=(j//4)*380+20;sheet.paste(im,(x,y));draw.text((x,y-16),f'Page {n:02}',fill='#141719')
        sheet.save(dest/f'contact-{start//12+1:02}.jpg',quality=94)
    report.update(strict_pdf_parse=True,pages_rendered=30,independent_renderer='PDFium',
                  internal_links_verified=links,original_screenshot_pixels_verified=exact,
                  original_screenshot_dimensions_preserved=True)
    (HERE/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'PDFium rendered 30 A4 pages; {links} internal links verified; all {exact} screenshots match original decoded pixels.')

if __name__=='__main__':main()
