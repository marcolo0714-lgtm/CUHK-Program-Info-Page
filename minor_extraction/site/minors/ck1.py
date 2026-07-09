import re
# Check Japanese Language prereq overflow
html = open('Japanese_Language.html','r',encoding='utf-8').read()
# Find a long prereq
for m in re.finditer(r'<td>[^<]{100,}</td>', html):
    print(m.group()[:200])
    print()
    break
