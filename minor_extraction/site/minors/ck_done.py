import re
# Biochemistry
html = open('Biochemistry.html','r',encoding='utf-8').read()
count = len(re.findall(r'class="eq-row"', html))
print('Biochem eq-row classes:', count)
# Show eq-row codes
for m in re.finditer(r'<tr class="[^"]*eq-row[^"]*"><td>([^<]+)', html):
    print('  eq:', m.group(1))
print()

# AIST - check nf eq-row
html2 = open('Artificial_Intelligence_Systems_and_Technologies.html','r',encoding='utf-8').read()
for m in re.finditer(r'<tr class="[^"]*nf[^"]*"><td>([^<]+)', html2):
    cls = re.search(r'class="([^"]+)"', m.group())
    print('AIST nf: ' + m.group(1) + ' class=' + (cls.group(1) if cls else '?'))
