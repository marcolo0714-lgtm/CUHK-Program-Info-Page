import re
html = open('HB_Minor_Programme_in_Entrepreneurship_and_Innovation.html','r',encoding='utf-8').read()
# Find all tr elements containing CSCI
for m in re.finditer(r'<tr[^>]*>(?:\s*<td>CSCI \d+</td>.*?)</tr>', html, re.DOTALL):
    code = re.search(r'<td>(CSCI \d+)</td>', m.group())
    has_eq = 'eq-row' in m.group()
    if code:
        print('E&I: ' + code.group(1) + ' eq=' + str(has_eq))
