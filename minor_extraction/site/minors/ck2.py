import re
html = open('Public_History.html','r',encoding='utf-8').read()
count = html.count('eq-row')
print('Public History eq-row:', count)
# Show eq-row courses
for m in re.finditer(r'<tr class=.eq-row.*?</tr>', html, re.DOTALL):
    code = re.search(r'<td>([^<]+)', m.group())
    if code: print('  eq:', code.group(1))
print()
# Check AIST
html2 = open('Artificial_Intelligence_Systems_and_Technologies.html','r',encoding='utf-8').read()
count2 = html2.count('eq-row')
print('AIST eq-row:', count2)
for m in re.finditer(r'<tr class=.eq-row.*?</tr>', html2, re.DOTALL):
    code = re.search(r'<td>([^<]+)', m.group())
    if code: print('  eq:', code.group(1))
