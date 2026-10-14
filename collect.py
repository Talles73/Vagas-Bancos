#!/usr/bin/env python3
"""Coleta vagas de bancos, corretoras e cooperativas via API da Adzuna (Brasil)
e grava docs/vagas.json. Roda todo dia pelo GitHub Actions."""
import json, os, re, sys, time, unicodedata
from datetime import datetime, timezone
import requests

APP_ID = os.environ.get("ADZUNA_APP_ID")
APP_KEY = os.environ.get("ADZUNA_APP_KEY")
API = "https://api.adzuna.com/v1/api/jobs/br/search/{page}"
PAGES = 2            # páginas por busca (50 vagas cada)
MAX_DAYS_OLD = 45    # ignora vagas mais antigas que isso

# Instituições: (nome exibido, tipo, termos que identificam a empresa no anúncio)
INST = [
 ("Banco do Brasil","Banco",["banco do brasil"]),("Caixa","Banco",["caixa economica","caixa econômica"]),
 ("Itaú","Banco",["itau","itaú"]),("Bradesco","Banco",["bradesco"]),("Santander","Banco",["santander"]),
 ("BTG Pactual","Banco",["btg"]),("Safra","Banco",["safra"]),("Banrisul","Banco",["banrisul"]),
 ("Banco do Nordeste","Banco",["banco do nordeste"]),("Banco da Amazônia","Banco",["banco da amazonia"]),
 ("Banestes","Banco",["banestes"]),("Banpará","Banco",["banpara"]),("BRB","Banco",["brb banco","banco de brasilia"]),
 ("Banco Inter","Banco",["banco inter","inter&co"]),("C6 Bank","Banco",["c6 bank","c6bank"]),
 ("Nubank","Banco",["nubank","nu pagamentos"]),("Banco Pan","Banco",["banco pan"]),("Banco BV","Banco",["banco bv","votorantim"]),
 ("Daycoval","Banco",["daycoval"]),("Banco Original","Banco",["banco original"]),("BMG","Banco",["banco bmg"]),
 ("ABC Brasil","Banco",["banco abc"]),("Sofisa","Banco",["sofisa"]),("Banco Mercantil","Banco",["banco mercantil","mercantil do brasil"]),
 ("XP","Corretora",["xp inc","xp investimentos"]),("Rico","Corretora",["rico investimentos","rico corretora"]),
 ("Clear","Corretora",["clear corretora"]),("Ágora","Corretora",["agora investimentos","ágora"]),
 ("Genial","Corretora",["genial"]),("Warren","Corretora",["warren"]),("Modal","Corretora",["modal"]),
 ("Órama","Corretora",["orama","órama"]),("Toro","Corretora",["toro investimentos","toro corretora"]),
 ("Guide","Corretora",["guide investimentos"]),("Ativa","Corretora",["ativa investimentos"]),
 ("Terra Investimentos","Corretora",["terra investimentos"]),("Necton","Corretora",["necton"]),
 ("Nu Invest","Corretora",["nu invest"]),("Avenue","Corretora",["avenue securities","avenue"]),
 ("Sicredi","Cooperativa",["sicredi"]),("Sicoob","Cooperativa",["sicoob"]),("Cresol","Cooperativa",["cresol"]),
 ("Unicred","Cooperativa",["unicred"]),("Ailos","Cooperativa",["ailos","viacredi"]),("Credisis","Cooperativa",["credisis"]),
 ("Cooperforte","Cooperativa",["cooperforte"]),("Coopcentral","Cooperativa",["coopcentral"]),
 ("Credicitrus","Cooperativa",["credicitrus"]),("Grupo Valure","Cooperativa",["valure"]),
]

# Buscas genéricas (profissão/certificação) + uma busca por instituição
GENERIC = ["CPA-20","CPA-10","CEA ANBIMA","assessor de investimentos","gerente de relacionamento banco",
           "gerente de negócios","agente de atendimento banco","assistente de negócios","caixa bancário",
           "analista de crédito banco","estágio banco","trainee banco","jovem aprendiz banco",
           "cooperativa de crédito","corretora de valores","agente comercial banco","operações backoffice banco"]
QUERIES = GENERIC + [n for n,_,_ in INST]

UF = {"Acre":"AC","Alagoas":"AL","Amapá":"AP","Amazonas":"AM","Bahia":"BA","Ceará":"CE","Distrito Federal":"DF",
 "Espírito Santo":"ES","Goiás":"GO","Maranhão":"MA","Mato Grosso":"MT","Mato Grosso do Sul":"MS","Minas Gerais":"MG",
 "Pará":"PA","Paraíba":"PB","Paraná":"PR","Pernambuco":"PE","Piauí":"PI","Rio de Janeiro":"RJ",
 "Rio Grande do Norte":"RN","Rio Grande do Sul":"RS","Rondônia":"RO","Roraima":"RR","Santa Catarina":"SC",
 "São Paulo":"SP","Sergipe":"SE","Tocantins":"TO"}

def norm(t): return unicodedata.normalize("NFD", t or "").encode("ascii","ignore").decode().lower()
UF_N = {norm(k):v for k,v in UF.items()}

def match_inst(company):
    c = norm(company)
    for nome, tipo, termos in INST:
        if any(norm(t) in c for t in termos): return nome, tipo
    return None

def area_de(titulo):
    t = norm(titulo)
    rules = [("Assessor de investimentos",["assessor de invest","financial advisor","assessor de investimento"]),
             ("Estágio",["estagi"]),("Trainee / Jovem aprendiz",["trainee","aprendiz"]),
             ("Gerente de relacionamento",["relacionamento","gerente de agencia","gerente de pa","gerente de unidade"]),
             ("Atendimento / Caixa",["atendimento","caixa","assistente de negocios","assistente de agencia"]),
             ("Comercial / Vendas",["gerente de negocios","comercial","vendas","agente comercial","prospec"]),
             ("Crédito / Cobrança",["credito","cobranca"]),("Risco / Compliance",["risco","compliance","pld","fraude"]),
             ("Tesouraria / Mesa",["tesouraria","mesa de operac"]),
             ("Tecnologia",["desenvolvedor","engenheiro de software","dados","tecnologia","ti "]),
             ("Operações / Backoffice",["operac","backoffice","administrativ","analista"])]
    for nome, kws in rules:
        if any(k in t for k in kws): return nome
    return "Outras"

def nivel_de(titulo):
    t = norm(titulo)
    if any(k in t for k in ["estagi","aprendiz","trainee","junior","jr","assistente","agente","atendimento","caixa","auxiliar"]): return "Entrada"
    return "Com experiência"

def local_de(item):
    area = (item.get("location") or {}).get("area") or []
    uf = ""; cidade = ""
    if len(area) > 1: uf = UF_N.get(norm(area[1]), "")
    if len(area) > 2: cidade = area[-1]
    if not uf:  # tenta pelo texto livre
        disp = (item.get("location") or {}).get("display_name", "")
        for nome, sig in UF.items():
            if nome.lower() in disp.lower(): uf = sig; break
    return cidade, uf

def pede_cpa(item):
    txt = norm((item.get("title") or "") + " " + (item.get("description") or ""))
    return bool(re.search(r"\bcpa[- ]?(10|20)\b|\bcea\b|\bc-?pro\b|anbima", txt))

def converter(item):
    inst = match_inst((item.get("company") or {}).get("display_name", ""))
    if not inst: return None
    cidade, uf = local_de(item)
    return {"id": str(item.get("id")), "cargo": item.get("title","").strip(), "empresa": (item.get("company") or {}).get("display_name",""),
            "instituicao": inst[0], "tipo": inst[1], "cidade": cidade, "uf": uf,
            "area": area_de(item.get("title","")), "nivel": nivel_de(item.get("title","")),
            "cpa": pede_cpa(item), "data": (item.get("created") or "")[:10],
            "salario": item.get("salary_min"), "url": item.get("redirect_url")}

def buscar(query, page):
    r = requests.get(API.format(page=page), timeout=30, params={
        "app_id": APP_ID, "app_key": APP_KEY, "results_per_page": 50, "what": query,
        "sort_by": "date", "max_days_old": MAX_DAYS_OLD, "content-type": "application/json"})
    r.raise_for_status()
    return r.json().get("results", [])

def main():
    if not APP_ID or not APP_KEY:
        sys.exit("Defina ADZUNA_APP_ID e ADZUNA_APP_KEY.")
    vagas, vistos, erros = {}, set(), 0
    for q in QUERIES:
        for p in range(1, PAGES + 1):
            try: res = buscar(q, p)
            except Exception as ex:
                erros += 1; print(f"[aviso] '{q}' pág {p}: {ex}", file=sys.stderr); break
            for it in res:
                v = converter(it)
                if v and v["id"] not in vagas: vagas[v["id"]] = v
            time.sleep(0.4)
            if len(res) < 50: break
    lista = sorted(vagas.values(), key=lambda v: v["data"], reverse=True)
    out = {"atualizado_em": datetime.now(timezone.utc).isoformat(timespec="minutes"), "total": len(lista), "vagas": lista}
    os.makedirs("docs", exist_ok=True)
    with open("docs/vagas.json", "w", encoding="utf-8") as f: json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"{len(lista)} vagas gravadas ({erros} erros de busca).")
    if not lista and erros: sys.exit(1)  # não sobrescreve com lista vazia por falha de API

if __name__ == "__main__": main()
