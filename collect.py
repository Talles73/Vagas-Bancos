#!/usr/bin/env python3
"""Coleta vagas de bancos, corretoras e cooperativas direto do GUPY (portal.gupy.io).
Só entram vagas cuja página fica no próprio Gupy (descrição + candidatura ali mesmo),
publicadas recentemente, com prazo em aberto e com a página confirmada no ar.
Grava docs/vagas.json. Não precisa de chave nem de cadastro."""
import json, os, re, sys, time, unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, date, timedelta
from urllib.parse import urlparse
import requests

PAGE_SIZE = 50
PAGES = 3                 # até 150 resultados por busca
MAX_DIAS = 60             # ignora vagas publicadas há mais de 60 dias
UA = {"User-Agent": "Mozilla/5.0 (compatible; vagas-bancos/1.0)"}
# A Gupy mudou de endereço/parâmetro ao longo do tempo: o script testa as variações em ordem.
ENDPOINTS = [("https://portal.api.gupy.io/api/v1/jobs", "jobName"),
             ("https://portal.api.gupy.io/api/job", "name")]

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


GENERIC = ["CPA-20","CPA-10","CEA ANBIMA","assessor de investimentos","gerente de relacionamento",
           "gerente de negócios","agente de atendimento","assistente de negócios","caixa bancário",
           "analista de crédito","estágio banco","trainee banco","jovem aprendiz banco",
           "cooperativa de crédito","corretora de valores","agente comercial","backoffice financeiro"]
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

def _local_antigo(item):
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


def local_de(item):
    cidade = (item.get("city") or "").strip()
    est = (item.get("state") or "").strip()
    uf = UF_N.get(norm(est), est.upper() if len(est) == 2 else "")
    return cidade, uf

def pede_cpa(item):
    txt = norm((item.get("name") or "") + " " + (item.get("description") or ""))
    return bool(re.search(r"\bcpa[- ]?(10|20)\b|\bcea\b|\bc-?pro\b|anbima", txt))

def host_gupy(url):
    h = (urlparse(url or "").hostname or "").lower()
    return h == "gupy.io" or h.endswith(".gupy.io")

def converter(item):
    empresa = item.get("careerPageName") or item.get("companyName") or ""
    inst = match_inst(empresa)
    url = item.get("jobUrl") or ""
    if not inst or not host_gupy(url): return None
    pub = (item.get("publishedDate") or "")[:10]
    prazo = (item.get("applicationDeadline") or "")[:10]
    hoje = date.today()
    try:
        if pub and date.fromisoformat(pub) < hoje - timedelta(days=MAX_DIAS): return None
        if prazo and date.fromisoformat(prazo) < hoje: return None
    except ValueError: pass
    cidade, uf = local_de(item)
    titulo = (item.get("name") or "").strip()
    desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", item.get("description") or "")).strip()
    return {"id": str(item.get("id") or url), "cargo": titulo, "empresa": empresa, "instituicao": inst[0],
            "tipo": inst[1], "cidade": cidade, "uf": uf, "area": area_de(titulo), "nivel": nivel_de(titulo),
            "cpa": pede_cpa(item), "data": pub, "prazo": prazo, "resumo": desc[:400],
            "remoto": bool(item.get("isRemoteWork")), "fonte": "Gupy", "url": url}

def buscar(endpoint, param, termo, offset):
    r = requests.get(endpoint, headers=UA, timeout=30,
                     params={param: termo, "limit": PAGE_SIZE, "offset": offset})
    r.raise_for_status()
    js = r.json()
    dados = js.get("data") if isinstance(js, dict) else js
    return dados if isinstance(dados, list) else []

def escolher_endpoint():
    for ep, par in ENDPOINTS:
        try:
            if buscar(ep, par, "banco", 0): return ep, par
        except Exception as ex:
            print(f"[aviso] {ep} ({par}): {ex}", file=sys.stderr)
    return None

def no_ar(vaga):
    """True = página existe; False = fora do ar/redirecionada; None = não deu para confirmar."""
    try:
        r = requests.get(vaga["url"], headers=UA, timeout=20, allow_redirects=True)
    except Exception:
        return None
    if r.status_code in (404, 410): return False
    if r.status_code != 200: return None
    if not host_gupy(r.url) or "/job" not in urlparse(r.url).path: return False
    return True

def main():
    ep = escolher_endpoint()
    if not ep: sys.exit("Nenhum endereço da Gupy respondeu. Veja os avisos acima.")
    print("Usando", ep)
    vagas, erros = {}, 0
    for q in QUERIES:
        for p in range(PAGES):
            try: res = buscar(ep[0], ep[1], q, p * PAGE_SIZE)
            except Exception as ex:
                erros += 1; print(f"[aviso] '{q}': {ex}", file=sys.stderr); break
            for it in res:
                v = converter(it)
                if v and v["url"] not in {x["url"] for x in vagas.values()}: vagas[v["id"]] = v
            time.sleep(0.3)
            if len(res) < PAGE_SIZE: break
    cand = list(vagas.values())
    with ThreadPoolExecutor(8) as ex: status = list(ex.map(no_ar, cand))
    lista = [v for v, s in zip(cand, status) if s is not False]
    removidas = len(cand) - len(lista)
    lista.sort(key=lambda v: v["data"], reverse=True)
    out = {"atualizado_em": datetime.now(timezone.utc).isoformat(timespec="minutes"), "fonte": "Gupy",
           "total": len(lista), "vagas": lista}
    os.makedirs("docs", exist_ok=True)
    with open("docs/vagas.json", "w", encoding="utf-8") as f: json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"{len(lista)} vagas gravadas; {removidas} descartadas (página fora do ar); {erros} erros de busca.")
    if not lista and erros: sys.exit(1)

if __name__ == "__main__": main()
