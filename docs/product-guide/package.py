"""Create a portable source package and a six-page preview of the product guide."""
import importlib.metadata
import json
import zipfile
from pathlib import Path
from PIL import Image,ImageDraw
from pypdf import PdfReader,PdfWriter
from pypdf.generic import NameObject

HERE=Path(__file__).resolve().parent
DOCS=HERE.parent

def main():
    report=json.loads((HERE/'validation.json').read_text(encoding='utf-8'))
    assert report['pages_rendered']==30 and report['original_screenshot_pixels_verified']==22
    requirements=[f'{d}=={importlib.metadata.version(d)}' for d in ('playwright','pypdf','Pillow','pypdfium2')]
    (HERE/'requirements.txt').write_text('\n'.join(requirements)+'\n',encoding='utf-8')
    pages=[1,2,3,5,7,14,18,23,29]
    sheet=Image.new('RGB',(1458,2088),'#c7d1d6');draw=ImageDraw.Draw(sheet)
    for i,n in enumerate(pages):
        with Image.open(HERE/'previews'/'final'/f'page-{n:02}.png') as source:
            im=source.convert('RGB');im.thumbnail((470,665),Image.Resampling.LANCZOS)
            x=12+(i%3)*482;y=12+(i//3)*692;sheet.paste(im,(x,y));draw.text((x,y+670),f'Mosaic / page {n:02}',fill='#34424a')
    sheet.save(DOCS/'Mosaic-Product-Guide-Preview.jpg',quality=94,subsampling=0)
    reader=PdfReader(DOCS/'Mosaic-Product-Guide.pdf');writer=PdfWriter()
    for p in reader.pages[:6]:
        page=writer.add_page(p)
        if '/Annots' in page: del page[NameObject('/Annots')]
    writer.add_metadata({'/Title':'Mosaic — Product Guide Preview','/Author':'Weirwood'})
    with (DOCS/'Mosaic-Product-Guide-Preview.pdf').open('wb') as f:writer.write(f)
    names=['content.py','build.py','measure.py','prepare_sources.py','verify.py','package.py','guide.css','reference.css','guide.html','manuscript.md','README.md','requirements.txt','coverage.json','coverage.md','provenance.json','validation.json']
    assets=[HERE/n for n in names]
    for d in ('shots','brand','fonts','assets'):assets+=list((HERE/d).glob('*'))
    target=DOCS/'Mosaic-Product-Guide-Source.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(assets):
            assert p.is_file(),p
            z.write(p,Path('product-guide')/p.relative_to(HERE))
        z.write(DOCS/'Mosaic-Product-Guide-Preview.jpg','Mosaic-Product-Guide-Preview.jpg')
    with zipfile.ZipFile(target) as z:assert z.testzip() is None
    print(f'Packaged {len(assets)} source files and assets: {target.stat().st_size/1e6:.1f} MB.')

if __name__=='__main__':main()
