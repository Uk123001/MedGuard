import json
im=json.load(open("assets/images.json"))
s=open("template.html").read()
for k in ["LOGO","FAV","OVERVIEW","MAP","CAPSULE","DOC","SEARCH","PLUS"]:
    s=s.replace("__%s__"%k,im[k])
assert "__" not in s.replace("__pending","").replace("__proto__",""), [x for x in s.split("__")[1:3]]
open("index.html","w").write(s)
print(len(s))
