import re
# Check eq-rows still working
html = open('Artificial_Intelligence_Systems_and_Technologies.html','r',encoding='utf-8').read()
eq_count = len(re.findall(r'class="[^"]*eq-row[^"]*"', html))
print('AIST eq-row:', eq_count)
# Check sidebar active-navigation prevention
has_prevent = 'classList.contains' in open('Computer_Science.html','r',encoding='utf-8').read()
print('Has active-link prevention:', has_prevent)
