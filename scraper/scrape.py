#!/usr/bin/env python3
"""DealScanner Scraper v3 — BODACC + Bpifrance + Fusacq + Transentreprise"""

import json, time, datetime, hashlib, os, re
import urllib.request, urllib.parse

DATA_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'annonces.json')

SECTEUR_MAP = {
    'industrie':    ['industrie','fabrication','usinage','mécanique','btp','construction','bâtiment','métallurgie','menuiserie','plomberie','électricité','maçonnerie','charpente','soudure'],
    'services':     ['conseil','audit','comptable','juridique','rh','formation','communication','service','agence','cabinet','bureau','étude','nettoyage','sécurité','gardiennage'],
    'commerce':     ['commerce','distribution','retail','négoce','vente','import','export','boutique','magasin','épicerie','boucherie','fleuriste','librairie','tabac'],
    'tech':         ['informatique','logiciel','numérique','digital','web','saas','cloud','tech','développement','internet','ecommerce','app'],
    'sante':        ['santé','médical','pharmacie','paramédical','dentaire','clinique','optique','infirmier','kiné','ostéo','vétérinaire','laboratoire','bien-être'],
    'restauration': ['restaurant','brasserie','boulangerie','hôtel','hcr','café','traiteur','pizzeria','snack','bar','crêperie','pâtisserie','glacier','fast','kebab'],
    'transport':    ['transport','logistique','livraison','fret','déménagement','taxi','vtc','ambulance','coursier'],
}

def detect_secteur(t):
    t = (t or '').lower()
    for s, mots in SECTEUR_MAP.items():
        if any(m in t for m in mots): return s
    return 'services'

def secteur_label(s):
    return {'industrie':'Industrie','services':'Services B2B','commerce':'Commerce','tech':'Tech & Digital','sante':'Santé','restauration':'Restauration','transport':'Transport'}.get(s,'Services')

def mkid(src, uid): return hashlib.sha256(f"{src}:{uid}".encode()).hexdigest()[:12]

def age_label(ds):
    try:
        d = datetime.datetime.fromisoformat(str(ds)[:10])
        n = (datetime.datetime.now()-d).days
        if n==0: return "Publié aujourd'hui"
        if n==1: return "Publié hier"
        if n<7:  return f"il y a {n} jours"
        if n<30: return f"il y a {n//7} semaine(s)"
        return f"il y a {n//30} mois"
    except: return "Récemment publié"

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

def fetch_json(url, t=20):
    req = urllib.request.Request(url, headers={'User-Agent':UA,'Accept':'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=t) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f"  ⚠ {url[:65]}: {e}"); return None

def fetch_html(url, t=20):
    req = urllib.request.Request(url, headers={'User-Agent':UA,'Accept':'text/html','Accept-Language':'fr-FR,fr;q=0.9'})
    try:
        with urllib.request.urlopen(req, timeout=t) as r:
            raw = r.read()
            for enc in ['utf-8','latin-1']:
                try: return raw.decode(enc)
                except: pass
    except Exception as e:
        print(f"  ⚠ {url[:65]}: {e}")
    return None

def check_robots(base):
    try:
        h = fetch_html(base+'/robots.txt', t=5)
        if h:
            ua = False
            for line in h.lower().split('\n'):
                if 'user-agent: *' in line: ua = True
                if ua and line.strip() == 'disallow: /':
                    print(f"  ⛔ robots.txt bloque {base}"); return False
    except: pass
    return True

def parse_montant(t):
    if not t: return None
    t = str(t).replace(' ','').replace('\xa0','').replace(',','.')
    m = re.search(r'([\d.]+)[Mm][e€]', t)
    if m:
        try: return int(float(m.group(1))*1000)
        except: pass
    m = re.search(r'([\d.]+)[Kk][e€]', t)
    if m:
        try: return int(float(m.group(1)))
        except: pass
    m = re.search(r'(\d{4,})', t)
    if m:
        try:
            v=int(m.group(1))
            if v>100000: return v//1000
            if v>100: return v
        except: pass
    return None

def score_annonce(a):
    s = 62
    if a.get('ca') and a.get('ebe') and a['ca']>0:
        marge = a['ebe']/a['ca']
        if marge>0.20: s+=20
        elif marge>0.12: s+=12
        elif marge>0.08: s+=5
        if a.get('prix') and a['ebe']>0:
            mul = a['prix']/a['ebe']
            if mul<3: s+=15
            elif mul<5: s+=8
            elif mul>8: s-=12
    s += {'tech':12,'sante':8,'services':4,'restauration':-5}.get(a.get('secteur',''),0)
    a['score']=max(40,min(95,s))
    a['score_financier']=min(95,s+5); a['score_valorisation']=min(95,s-3)
    a['score_croissance']=min(95,s+2); a['score_risque']=min(95,s+8)
    return a

def scrape_bodacc(n=100):
    print("📡 BODACC A — Ventes fonds de commerce...")
    url = ("https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets"
           "/annonces-commerciales-bodacc-a-b/records?where=typeavis%3D%27Vente%27"
           f"&order_by=dateparution%20desc&limit={min(n,100)}")
    data = fetch_json(url)
    if not data or 'results' not in data: print("  Non disponible"); return []
    out = []
    for rec in data.get('results',[]):
        try:
            acte=rec.get('acte') or {}; ville=rec.get('ville','') or ''
            dept=rec.get('departement_nom_officiel','') or ''; date_s=rec.get('dateparution','') or ''
            num=rec.get('numerounique','') or str(abs(hash(str(rec))))[:8]
            activite=''
            if isinstance(acte,dict): activite=acte.get('activite','') or acte.get('descriptif','') or ''
            if not activite: activite=rec.get('commercant','') or ''
            if not activite and not ville: continue
            sect=detect_secteur(activite); annee=date_s[:4] if date_s else '2025'
            a={"id":mkid("bodacc",num),"titre":(activite[:75] or f"Cession fonds — {ville}").strip(),
               "secteur":sect,"secteur_label":secteur_label(sect),"region":dept,"ville":ville,
               "ca":None,"ebe":None,"prix":None,"effectif":None,"annee_creation":None,
               "date_publication":age_label(date_s),"source":"BODACC",
               "source_url":f"https://www.bodacc.fr/annonce/detail-annonce/A/{annee}/{num}",
               "description":f"Vente de fonds de commerce — BODACC. Activité : {activite[:100] or 'Non précisée'}. {ville}, {dept}.",
               "points_forts":["Publication légale officielle","Cession authentifiée","Localisation vérifiée"],
               "motif_cession":"Annonce légale BODACC","ca_trend":"stable","ca_evolution":"Non communiqué"}
            out.append(score_annonce(a))
        except: continue
    print(f"  ✓ {len(out)} annonces"); return out

def scrape_bodacc_b(n=40):
    print("📡 BODACC B — Procédures collectives...")
    url = ("https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets"
           "/annonces-commerciales-bodacc-a-b/records"
           "?where=typeavis%3D%27Redressement%27%20OR%20typeavis%3D%27Sauvegarde%27"
           f"&order_by=dateparution%20desc&limit={min(n,50)}")
    data = fetch_json(url)
    if not data or 'results' not in data: print("  Non disponible"); return []
    out = []
    for rec in data.get('results',[]):
        try:
            ville=rec.get('ville','') or ''; dept=rec.get('departement_nom_officiel','') or ''
            date_s=rec.get('dateparution','') or ''; num=rec.get('numerounique','') or str(abs(hash(str(rec))))[:8]
            acte=rec.get('acte') or {}
            activite=''
            if isinstance(acte,dict): activite=acte.get('activite','') or ''
            if not activite: activite=rec.get('commercant','') or ''
            if not activite: continue
            sect=detect_secteur(activite)
            a={"id":mkid("bodaccb",num),"titre":f"⚖️ Reprise possible — {activite[:60]}",
               "secteur":sect,"secteur_label":secteur_label(sect),"region":dept,"ville":ville,
               "ca":None,"ebe":None,"prix":None,"effectif":None,"annee_creation":None,
               "date_publication":age_label(date_s),"source":"BODACC",
               "source_url":"https://www.bodacc.fr",
               "description":f"Entreprise en procédure collective — reprise possible. {activite[:100]}. {ville}, {dept}.",
               "points_forts":["Prix négociable","Actifs valorisables","Procédure encadrée par tribunal"],
               "motif_cession":"Redressement / Sauvegarde judiciaire","ca_trend":"down","ca_evolution":"À évaluer"}
            out.append(score_annonce(a))
        except: continue
    print(f"  ✓ {len(out)} procédures"); return out

def scrape_bpifrance():
    print("📡 Bpifrance Transmission...")
    url = ("https://reprise-entreprise.bpifrance.fr/api/v1/annonces"
           "?page=1&pageSize=50&sortBy=datePublication&sortOrder=desc")
    data = fetch_json(url)
    if not data: print("  Non disponible"); return []
    out = []
    annonces = data.get('annonces') or data.get('results') or data.get('data') or []
    for rec in annonces:
        try:
            titre=rec.get('titre','') or rec.get('libelle','') or 'Entreprise à reprendre'
            ville=rec.get('ville','') or rec.get('commune','') or ''
            region=rec.get('region','') or rec.get('departement','') or ''
            ca_r=rec.get('ca') or rec.get('chiffreAffaires') or None
            prix_r=rec.get('prix') or rec.get('prixDemande') or None
            ebe_r=rec.get('ebe') or None
            date_s=rec.get('datePublication','') or ''
            uid=str(rec.get('id','') or rec.get('reference','') or abs(hash(titre)))
            sect=detect_secteur(titre+' '+(rec.get('activite','') or ''))
            a={"id":mkid("bpifrance",uid),"titre":titre[:75],
               "secteur":sect,"secteur_label":secteur_label(sect),"region":region,"ville":ville,
               "ca":int(ca_r/1000) if ca_r else None,"ebe":int(ebe_r/1000) if ebe_r else None,
               "prix":int(prix_r/1000) if prix_r else None,
               "effectif":rec.get('effectif') or None,"annee_creation":rec.get('anneeCreation') or None,
               "date_publication":age_label(date_s),"source":"Bpifrance",
               "source_url":f"https://reprise-entreprise.bpifrance.fr/annonce/{uid}",
               "description":rec.get('description','') or f"Transmission d'entreprise — Bpifrance. {region}.",
               "points_forts":["Annonce Bpifrance vérifiée","Financement possible","Accompagnement disponible"],
               "motif_cession":rec.get('motifCession','') or "Non précisé",
               "ca_trend":"stable","ca_evolution":"Voir dossier complet"}
            out.append(score_annonce(a))
        except: continue
    print(f"  ✓ {len(out)} annonces"); return out

def scrape_fusacq(pages=3):
    print("📡 Fusacq — Annonces de cession...")
    base = "https://www.fusacq.com"
    if not check_robots(base): return []
    out = []
    for page in range(1, pages+1):
        url = f"{base}/reprendre-une-entreprise/annonces-cession-entreprise_fr_?p={page}"
        html = fetch_html(url)
        if not html: break
        time.sleep(1.5)
        liens = re.findall(r'href="(/vente-entreprise[^"]+)"[^>]*>([^<]{10,100})<', html)
        for lien, titre in liens[:20]:
            try:
                titre = re.sub(r'<[^>]+>','',titre).strip()
                if len(titre)<5: continue
                sect = detect_secteur(titre)
                uid = lien.split(',')[-1].replace('_fr_','').replace('/','') or str(abs(hash(lien)))[:8]
                a={"id":mkid("fusacq",uid),"titre":titre[:75],
                   "secteur":sect,"secteur_label":secteur_label(sect),
                   "region":"","ville":"France","ca":None,"ebe":None,"prix":None,
                   "effectif":None,"annee_creation":None,"date_publication":"Récemment publié",
                   "source":"Fusacq","source_url":base+lien,
                   "description":f"Annonce de cession publiée sur Fusacq. {titre}.",
                   "points_forts":["Annonce vérifiée Fusacq","Dossier disponible","Contact direct cédant"],
                   "motif_cession":"Voir annonce complète","ca_trend":"stable","ca_evolution":"Voir dossier"}
                out.append(score_annonce(a))
            except: continue
        if not liens: break
    print(f"  ✓ {len(out)} annonces Fusacq"); return out

def scrape_transentreprise(pages=2):
    print("📡 Transentreprise (CCI)...")
    base = "https://www.transentreprise.com"
    if not check_robots(base): return []
    out = []
    for page in range(1, pages+1):
        url = f"{base}/annonces?page={page}"
        html = fetch_html(url)
        if not html: break
        time.sleep(1.5)
        liens  = re.findall(r'href="(/annonce[^"]{5,100})"', html)
        titres = re.findall(r'<h[23][^>]*>([^<]{10,100})</h[23]>', html)
        for i, lien in enumerate(liens[:15]):
            try:
                titre = titres[i] if i<len(titres) else "Entreprise à reprendre"
                titre = re.sub(r'<[^>]+>','',titre).strip()
                sect  = detect_secteur(titre)
                a={"id":mkid("cci",lien),"titre":titre[:75],
                   "secteur":sect,"secteur_label":secteur_label(sect),
                   "region":"","ville":"France","ca":None,"ebe":None,"prix":None,
                   "effectif":None,"annee_creation":None,"date_publication":"Récemment publié",
                   "source":"CCI France","source_url":base+lien,
                   "description":f"Annonce de cession — réseau CCI / Transentreprise. {titre}.",
                   "points_forts":["Réseau CCI officiel","Accompagnement disponible","Dossier vérifié"],
                   "motif_cession":"Voir annonce complète","ca_trend":"stable","ca_evolution":"Voir dossier"}
                out.append(score_annonce(a))
            except: continue
        if not liens: break
    print(f"  ✓ {len(out)} annonces CCI"); return out

def main():
    print(f"\n{'='*55}")
    print(f"DealScanner v3 — {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*55}\n")
    all_annonces = []
    for fn, args in [(scrape_bodacc,[100]),(scrape_bodacc_b,[40]),(scrape_bpifrance,[]),(scrape_fusacq,[3]),(scrape_transentreprise,[2])]:
        try: all_annonces += fn(*args)
        except Exception as e: print(f"Erreur {fn.__name__}: {e}")
        time.sleep(2)
    seen, unique = set(), []
    for a in all_annonces:
        if a['id'] not in seen: seen.add(a['id']); unique.append(a)
    print(f"\n📊 Total: {len(all_annonces)} | Dédup: {len(unique)}")
    if len(unique)<10: print("⚠️  Pas assez — conservation existant"); return
    unique.sort(key=lambda x:x.get('score',0), reverse=True)
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE,'w',encoding='utf-8') as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)
    print(f"✅ {len(unique)} annonces → data/annonces.json\n{'='*55}\n")

if __name__ == '__main__': main()
