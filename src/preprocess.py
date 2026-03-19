import json
from config import SABAllowList, STYAllowList

valid_cuis = {}
with open("MRCONSO.RRF", encoding="utf-8") as f:
    for lineno, line in enumerate(f, start=1):
        try:
            fields = line.strip().split("|")
            # CUI | LAT | TS | LUI | STT | SUI | ISPREF | AUI | SAUI | SCUI | SDUI | SAB | TTY | CODE | STR | SRL | SUPPRESS
            cui = fields[0] # concept unique identifier
            lat = fields[1] # language of term
            # ts = fields[2]   # term status
            # lui = fields[3]  # language unique identifier
            # stt = fields[4]  # string type
            # sui = fields[5]  # string unique identifier
            ispref = fields[6]  # preferred term flag
            aui = fields[7]  # atom unique identifier
            # saui = fields[8]  # source asserted atom identifier
            # scui = fields[9]  # source asserted concept identifier
            # sdui = fields[10] # source asserted descriptor identifier
            sab = fields[11]   # source vocab
            tty = fields[12]   # term type
            # code = fields[13]  # code
            txt = fields[14]  # string text
            # srl = fields[15]  # source restriction level
            suppress = fields[16]  # suppressible flag
            if lat == "ENG" and ispref == "Y" and sab in SABAllowList and suppress == "N":
                # print(line, end="")
                if cui not in valid_cuis:
                    valid_cuis[cui] = {"CUI": cui, "AUI": [], "DEF": [], "SAB": [], "STR": [], "STY": [], "TTY": [], "TUI": []}
                valid_cuis[cui]["AUI"].append(aui)
                valid_cuis[cui]["STR"].append(txt)
                valid_cuis[cui]["TTY"].append(tty)
                valid_cuis[cui]["SAB"].append(sab)
        except Exception as e:
            print(f"Error at line {lineno} in MRCONSO.RRF: {e}")
            raise

with open("MRSTY.RRF", encoding="utf-8") as f:
    for lineno, line in enumerate(f, start=1):
        try:
            fields = line.strip().split("|")
            # CUI | TUI | STN | STY | ATUI
            cui = fields[0] # concept unique identifier
            tui = fields[1] # semantic type unique identifier
            # stn = fields[2] # semantic type tree number
            sty = fields[3] # semantic type
            # print(f"Processing CUI: {cui}, STY: {sty}")
            # atui = fields[4] # atom semantic type unique identifier
            if cui in valid_cuis:
                    valid_cuis[cui]["STY"].append(sty)
                    valid_cuis[cui]["TUI"].append(tui)
        except Exception as e:
            print(f"Error at line {lineno} in MRSTY.RRF: {e}")
            raise

to_delete = []
for key, value in valid_cuis.items():
    if set(value['STY']).isdisjoint(STYAllowList):
        to_delete.append(key)

for key in to_delete:
    del valid_cuis[key]
            
with open("MRDEF.RRF", encoding="utf-8") as f:
    for lineno, line in enumerate(f, start=1):
        try:
            fields = line.strip().split("|")
            # CUI | AUI | ATUI | SATUI | SAB | DEF | SUPPRESS
            cui = fields[0] # concept unique identifier
            aui = fields[1] # atom unique identifier
            atui = fields[2] # atom semantic type unique identifier
            # satui = fields[3] # source asserted atom semantic type unique identifier
            # sab = fields[4] # source vocab
            definition = fields[5] # semantic type
            suppress = fields[6] # suppressible flag
            if cui in valid_cuis and suppress == "N":
                valid_cuis[cui]["DEF"].append(definition)
        except Exception as e:
            print(f"Error at line {lineno} in MRDEF.RRF: {e}")
            raise
        
for _, value in valid_cuis.items():
    for field in ["AUI", "STR", "TTY", "SAB", "STY", "TUI"]:
        value[field] = list(set(value[field]))
        
with open("valid_cuis.json", "w", encoding="utf-8") as out:
    json.dump(list(valid_cuis.values()), out, ensure_ascii=False, indent=2)
    
with open("valid_cuis.txt", "w", encoding="utf-8") as out:
    json.dump(list(valid_cuis.keys()), out, ensure_ascii=False, indent=2)