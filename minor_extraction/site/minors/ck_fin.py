import re
html = open('Artificial_Intelligence_Systems_and_Technologies.html','r',encoding='utf-8').read()
# Show all nf rows
for m in re.finditer(r'<tr[^>]*nf[^>]*>.*?</tr>', html, re.DOTALL):
    code = re.search(r'<td>([^<]+)', m.group())
    cls = re.search(r'class="([^"]+)"', m.group())
    print('nf: ' + (code.group(1) if code else '?') + ' class=' + (cls.group(1) if cls else '?'))
print()
# Test Biochemistry eq-rows
html2 = open('Biochemistry.html','r',encoding='utf-8').read()
count = len(re.findall(r'class="eq-row"', html2))
print('Biochem eq-row:', count)
