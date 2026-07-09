import re
html = open('Public_History.html','r',encoding='utf-8').read()
# Show lines with eq-row
for m in re.finditer(r'eq-row', html):
    start = max(0, m.start()-30)
    end = min(len(html), m.end()+50)
    print(re.sub(r'\s+',' ',html[start:end]))
