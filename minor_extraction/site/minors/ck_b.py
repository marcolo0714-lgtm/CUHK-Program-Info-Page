import re
html = open('Artificial_Intelligence_Systems_and_Technologies.html','r',encoding='utf-8').read()
# Count eq-row occurrences
count = html.count('eq-row')
print('AIST eq-row count:', count)
# Check the CSS variables used
print('Has tbl-border:', 'tbl-border' in html)
print('Has tbl-border-light:', 'tbl-border-light' in html)
# Check Cultural Heritage for "or" pairs
html2 = open('Cultural_Heritage_Studies.html','r',encoding='utf-8').read()
count2 = html2.count('eq-row')
print('CH eq-row count:', count2)
# Check History for "or" pairs
html3 = open('History.html','r',encoding='utf-8').read()
count3 = html3.count('eq-row')
print('History eq-row count:', count3)
