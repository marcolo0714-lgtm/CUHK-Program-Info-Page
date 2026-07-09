import re
# Check Public History for eq-row on HIST 2500
html = open('Public_History.html','r',encoding='utf-8').read()
# Find tr elements containing HIST 2500
for m in re.finditer(r'<tr[^>]*>(?:\s*<td>HIST 2500</td>.*?</tr>)', html, re.DOTALL):
    print(m.group()[:150])
    if 'eq-row' in m.group():
        print('  HAS eq-row')
    print()
