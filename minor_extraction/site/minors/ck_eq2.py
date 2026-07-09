import re
html = open('Artificial_Intelligence_Systems_and_Technologies.html','r',encoding='utf-8').read()
tables = re.findall(r'<details class=.course-details.*?</details>', html, re.DOTALL)
for i, tbl in enumerate(tables):
    has_eq = 'eq-row' in tbl
    print('Table ' + str(i) + ': has eq-row=' + str(has_eq))
    if has_eq:
        for m in re.finditer(r'<tr[^>]*eq-row.*?</tr>', tbl, re.DOTALL):
            code = re.search(r'<td>([^<]+)', m.group())
            if code:
                print('  eq: ' + code.group(1))
