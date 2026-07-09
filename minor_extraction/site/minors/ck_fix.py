import re
# Biochemistry slash pairs
html = open('Biochemistry.html','r',encoding='utf-8').read()
count = len(re.findall(r'<tr class="eq-row"', html))
print('Biochemistry eq-row:', count)
# Show eq-row codes
for m in re.finditer(r'<tr class="eq-row"><td>([^<]+)', html):
    print('  eq:', m.group(1))
print()

# AIST - check nf rows with eq-row
html2 = open('Artificial_Intelligence_Systems_and_Technologies.html','r',encoding='utf-8').read()
for m in re.finditer(r'<tr class="nf[^"]*"><td>([^<]+)', html2):
    has_eq = 'eq-row' in m.group()
    print('AIST nf: ' + m.group(1) + ' eq=' + str(has_eq))
