import json
import os
from collections import OrderedDict

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
raw_path = os.path.join(base, 'app', 'static', 'colombia_raw.json')
out_path = os.path.join(base, 'app', 'static', 'colombia_cities.json')

data = json.load(open(raw_path, 'r', encoding='utf-8'))

deps = OrderedDict()
for d in data:
    dep = d['dpto'].strip()
    mun = d['nom_mpio'].strip()
    if dep not in deps:
        deps[dep] = []
    if mun not in deps[dep]:
        deps[dep].append(mun)

for dep in deps:
    deps[dep].sort()

result = []
for dep in sorted(deps.keys()):
    result.append({'departamento': dep, 'ciudades': deps[dep]})

with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f'Departamentos: {len(result)}')
for r in result[:5]:
    print(f"  {r['departamento']}: {len(r['ciudades'])} ciudades")
bog = [r for r in result if 'BOG' in r['departamento']]
print(f'Bogota: {bog}')
print(f'Total ciudades: {sum(len(r["ciudades"]) for r in result)}')