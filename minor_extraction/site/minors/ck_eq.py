import re
for f in ['Artificial_Intelligence_Systems_and_Technologies.html','HB_Minor_Programme_in_Entrepreneurship_and_Innovation.html','Physics.html']:
    html = open(f,'r',encoding='utf-8').read()
    count = len(re.findall(r'<tr class="eq-row"', html))
    print(f + ': eq-row trs=' + str(count))
