"""Contact sheet of owned app captures; no synthetic product screenshot."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
directory = ROOT/'build/phase10-production-preview-v2'
names = ['home','chats','projects','research','spatial','devices','media','automations',
         'connectors','security','history','activity','tools','voice','artifacts','plugins','settings']
font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 18)
sheet = Image.new('RGB', (1360, 5*310), '#101723'); draw = ImageDraw.Draw(sheet)
for index, name in enumerate(names):
    with Image.open(directory/(name+'.png')) as capture:
        capture.load(); preview = capture.convert('RGB'); preview.thumbnail((440, 276))
    x,y = (index%3)*453, (index//3)*310
    # Six rows for seventeen routes.
    if y+310 > sheet.height:
        expanded = Image.new('RGB', (1360, y+310), '#101723'); expanded.paste(sheet); sheet=expanded; draw=ImageDraw.Draw(sheet)
    draw.text((x+8,y+3), name, font=font, fill='#f5f8fc'); sheet.paste(preview, (x+4,y+29))
target = directory/'contact-sheet.png'; sheet.save(target); print(target)
