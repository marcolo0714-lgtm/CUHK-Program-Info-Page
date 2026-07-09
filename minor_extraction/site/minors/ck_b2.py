import re
html = open('History.html','r',encoding='utf-8').read()
# Find eq-row entries and show the course codes
for m in re.finditer(r'<tr[^>]*>.*?</tr>', html, re.DOTALL):
    if 'eq-row' in m.group():
        code = re.search(r'<td>([^<]+)', m.group())
        if code:
            print('eq-row:', code.group(1))
    elif 'HIST 1002' in m.group() or 'HIST 1001' in m.group():
        code = re.search(r'<td>([^<]+)', m.group())
        if code:
            print('row:', code.group(1))
