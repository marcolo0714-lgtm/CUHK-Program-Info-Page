import re
html = open('Artificial_Intelligence_Systems_and_Technologies.html','r',encoding='utf-8').read()
# Check for or-pair eq-rows (not slash pairs)
# Look for AIST3010 row
for m in re.finditer(r'<tr[^>]*>(?:\s*<td>AIST 3010</td>.*?</tr>)', html, re.DOTALL):
    print(m.group()[:120])
    if 'eq-row' in m.group():
        print('  HAS eq-row')
    print()
