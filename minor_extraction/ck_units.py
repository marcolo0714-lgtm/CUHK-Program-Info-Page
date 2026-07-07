import json
for m in ['Music','Earth_and_Environmental_Sciences','Molecular_Biotechnology','HB_Minor_Programme_in_Entrepreneurship_and_Innovation']:
    d = json.load(open('minor_json/'+m+'.json','r',encoding='utf-8'))
    print('=== ' + m + ' ===')
    for s in ['required','elective']:
        sec = d[s]
        total = 0
        for r in sec['rows']:
            u = r.get('units','')
            if u.strip():
                try: total += int(u.strip())
                except: pass
        print(s + ': label=' + repr(sec['label']) + ' units=' + repr(sec['units']) + ' row_sum=' + str(total))
        for r in sec['rows']:
            print('  row: text=' + r['text'][:80] + ' units=' + repr(r['units']))
    print()
