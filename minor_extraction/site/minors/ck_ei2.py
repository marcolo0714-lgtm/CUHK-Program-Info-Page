import re
html = open('HB_Minor_Programme_in_Entrepreneurship_and_Innovation.html','r',encoding='utf-8').read()
for m in re.finditer(r'<tr class="eq-row"><td>([^<]+)', html):
    print('eq-row:', m.group(1))
