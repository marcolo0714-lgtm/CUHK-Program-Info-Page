import re
for f in ['Artificial_Intelligence_Systems_and_Technologies.html','HB_Minor_Programme_in_Entrepreneurship_and_Innovation.html','Molecular_Biotechnology.html','Biochemistry.html','Physics.html']:
    html = open(f,'r',encoding='utf-8').read()
    count = len(re.findall(r'<tr class="eq-row"', html))
    print(f + ': eq-row=' + str(count))
# Show E&I eq-row codes
print()
html = open('HB_Minor_Programme_in_Entrepreneurship_and_Innovation.html','r',encoding='utf-8').read()
for m in re.finditer(r'<tr class="eq-row"><td>([^<]+)', html):
    print('E&I eq:', m.group(1))
