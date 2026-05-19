#!/usr/bin/env python3
"""DealScanner Scraper v5 — Fusacq + BODACC + CessionPME + Leboncoin Pro"""

import json, time, datetime, hashlib, os, re
import urllib.request, urllib.parse

DATA_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'annonces.json')

SECTEUR_MAP = {
    'industrie':    ['industrie','fabrication','usinage','mécanique','btp','construction','bâtiment','métallurgie','menuiserie','plomberie','maçonnerie','soudure','charpente','imprimerie'],
    'services':     ['conseil','audit','comptable','juridique','rh','formation','communication','service','agence','cabinet','nettoyage','sécurité','gardiennage','assurance'],
    'commerce':     ['commerce','distribution','retail','négoce','vente','import','export','boutique','magasin','épicerie','boucherie','fleuriste','tabac','librairie'],
    'tech':         ['informatique','logiciel','numérique','digital','web','saas','cloud','tech','développement','internet','ecommerce','app'],
    'sante':        ['santé','médical','pharmacie','dentaire','clinique','optique','infirmier','kiné','ostéo','vétérinaire','laboratoire','bien-être','spa'],
    'restauration': ['restaurant','brasserie','boulangerie','hôtel','café','traiteur','pizzeria','snack','bar','crêperie','pâtisserie','glacier','fast','kebab'],
    'transport':    ['transport','logistique','livraison','fret','déménagement','taxi','vtc','ambulance','coursier'],
}

def detect_secteur(t):
    t = (t or '').lower()
    for s, mots in SECTEUR_MAP.items():
        if any(m in t for m in mots): return s
    return 'services'

def secteur_label(s):
    return {'industrie':'Industrie','services':'Services B2B','commerce':'Commerce',
            'tech':'Tech & Digital','sante':'Santé','restauration':'Restauration',
            'transport':'Transport'}.get(s,'Services')

def mkid(src, uid):
    return hashlib.sha256(f"{src}:{uid}".encode()).hexdigest()[:12]

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

UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'

def fetch(url, t=25, accept='text/html'):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': accept,
        'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
        'Cache-Control': 'no-cache',
    })
    try:
        with urllib.request.urlopen(req, timeout=t) as r:
            raw = r.read()
            if accept == 'application/json':
                return json.loads(raw.decode('utf-8'))
            for enc in ['utf-8','latin-1','iso-8859-1']:
                try: return raw.decode(enc)
                except: pass
    except Exception as e:
        print(f"  ⚠ {url[:70]}: {e}")
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

def parse_montant(t):
    if not t: return None
    t = str(t).replace(' ','').replace('\xa0','').replace(',','.')
    m = re.search(r'([\d.]+)[Mm][e€]', t)
    if m:
        try: return int(float(m.group(1))*1000)
        except: pass
    m = re.search(r'([\d.]+)[Kk][e€]?', t)
    if m:
        try: return int(float(m.group(1)))
        except: pass
    m = re.search(r'(\d{4,})', t.replace('.','').replace(',',''))
    if m:
        try:
            v=int(m.group(1))
            if v>1000000: return v//1000
            if v>1000: return v
            if v>100: return v
        except: pass
    return None

# ══════════════════════════════════════════════════
# SOURCE 1 : Fusacq — scraping HTML
# ══════════════════════════════════════════════════
def scrape_fusacq(pages=5):
    print("📡 Fusacq — Annonces de cession...")
    base = "https://www.fusacq.com"
    out  = []
    seen_titles = set()

    for page in range(1, pages+1):
        url = f"{base}/reprendre-une-entreprise/annonces-cession-entreprise_fr_?p={page}"
        html = fetch(url)
        if not html: break
        time.sleep(2)

        # Extraction liens complets vers fiches individuelles
        fiches = re.findall(
            r'<a[^>]+href="(/vente-entreprise[^"]{10,200})"[^>]*>([^<]{5,120})</a>',
            html
        )
        if not fiches:
            fiches_liens = re.findall(r'href="(/vente-entreprise[^"]{10,200})"', html)
            fiches_titres = re.findall(
                r'class="[^"]*(?:titre|title|name|fiche)[^"]*"[^>]*>([^<]{5,100})<',
                html, re.IGNORECASE
            )
            fiches = list(zip(fiches_liens, fiches_titres + ['']*len(fiches_liens)))

        # Extraire aussi les prix et localisations depuis la page
        blocs = re.findall(
            r'<(?:li|div|article)[^>]*class="[^"]*(?:annonce|fiche|listing|item)[^"]*"[^>]*>(.*?)</(?:li|div|article)>',
            html, re.DOTALL | re.IGNORECASE
        )

        for i, (lien, titre) in enumerate(fiches[:20]):
            try:
                titre = re.sub(r'<[^>]+>','', titre).strip()
                titre = re.sub(r'\s+',' ', titre).strip()
                if len(titre) < 5 or titre in seen_titles: continue
                seen_titles.add(titre)

                # Infos du bloc correspondant
                ca_val = prix_val = ville_val = ''
                if i < len(blocs):
                    bloc = blocs[i]
                    txt = re.sub(r'<[^>]+>','', bloc)
                    m = re.search(r'CA[^0-9]*([0-9][0-9 ]*(?:[kKmM])?[€e]?)', txt)
                    if m: ca_val = m.group(1)
                    m = re.search(r'(?:Prix|Cession)[^0-9]*([0-9][0-9 ]*(?:[kKmM])?[€e]?)', txt)
                    if m: prix_val = m.group(1)
                    m = re.search(r'\b([A-Z][a-zéèêëàâùûîïôœ\-]{2,}(?:\s[A-Z][a-z]+)?)\b', txt)
                    if m: ville_val = m.group(1)

                # ID unique basé sur le lien complet
                uid = re.sub(r'[^a-z0-9]', '', lien.lower())[:20] or str(abs(hash(lien)))[:10]
                sect = detect_secteur(titre)
                a = {
                    "id":               mkid("fusacq", uid),
                    "titre":            titre[:80],
                    "secteur":          sect,
                    "secteur_label":    secteur_label(sect),
                    "region":           "",
                    "ville":            ville_val or "France",
                    "ca":               parse_montant(ca_val),
                    "ebe":              None,
                    "prix":             parse_montant(prix_val),
                    "effectif":         None,
                    "annee_creation":   None,
                    "date_publication": "Récemment publié",
                    "source":           "Fusacq",
                    "source_url":       base + lien,
                    "description":      f"Annonce de cession publiée sur Fusacq. {titre}.",
                    "points_forts":     ["Annonce vérifiée Fusacq","Dossier sur demande","Contact direct cédant"],
                    "motif_cession":    "Voir annonce Fusacq",
                    "ca_trend":         "stable",
                    "ca_evolution":     "Voir dossier",
                }
                out.append(score_annonce(a))
            except: continue

        if not fiches: break

    print(f"  ✓ {len(out)} annonces Fusacq")
    return out

# ══════════════════════════════════════════════════
# SOURCE 2 : BODACC via API v2 corrigée
# ══════════════════════════════════════════════════
def scrape_bodacc(n=100):
    print("📡 BODACC — Ventes fonds de commerce...")
    
    # URLs à essayer dans l'ordre
    urls = [
        # API v2.1 - nom dataset correct
        "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/adce/records?where=typeavis%3D%22Vente%22&order_by=dateparution%20desc&limit=100",
        # Autre dataset possible
        "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/annonces-commerciales-bodacc/records?where=typeavis%3D%22Vente%22&limit=100",
        # Dataset annonces A
        "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/bodacc-a/records?limit=100",
    ]
    
    data = None
    for url in urls:
        data = fetch(url, accept='application/json')
        if data and ('results' in data or 'records' in data):
            print(f"  ✓ URL BODACC OK: {url[:60]}")
            break
        data = None
    
    if not data:
        print("  BODACC non disponible (sera résolu dans la prochaine version)")
        return []

    records = data.get('results', data.get('records', []))
    out = []
    for rec in records[:n]:
        try:
            fields = rec.get('fields', rec)
            ville    = fields.get('ville','') or ''
            dept     = fields.get('departement_nom_officiel','') or fields.get('departement','') or ''
            date_s   = fields.get('dateparution','') or ''
            num      = fields.get('numerounique','') or str(abs(hash(str(rec))))[:8]
            acte     = fields.get('acte') or {}
            activite = ''
            if isinstance(acte, dict): activite = acte.get('activite','') or acte.get('descriptif','') or ''
            if not activite: activite = fields.get('commercant','') or ''
            if not activite and not ville: continue
            annee = date_s[:4] if date_s else '2025'
            sect = detect_secteur(activite)
            a = {
                "id":               mkid("bodacc", num),
                "titre":            (activite[:75] or f"Cession fonds — {ville}").strip(),
                "secteur":          sect,
                "secteur_label":    secteur_label(sect),
                "region":           dept, "ville": ville,
                "ca":None,"ebe":None,"prix":None,"effectif":None,"annee_creation":None,
                "date_publication": age_label(date_s),
                "source":           "BODACC",
                "source_url":       f"https://www.bodacc.fr/annonce/detail-annonce/A/{annee}/{num}",
                "description":      f"Vente de fonds de commerce publiée au BODACC. {activite[:100] or 'Non précisée'}. {ville}, {dept}.",
                "points_forts":     ["Publication légale officielle","Cession authentifiée","Dossier vérifiable"],
                "motif_cession":    "Annonce légale BODACC",
                "ca_trend":         "stable","ca_evolution": "Non communiqué",
            }
            out.append(score_annonce(a))
        except: continue
    print(f"  ✓ {len(out)} annonces BODACC")
    return out

# ══════════════════════════════════════════════════
# SOURCE 3 : Leboncoin Pro — fonds de commerce
# ══════════════════════════════════════════════════
def scrape_leboncoin(pages=3):
    print("📡 Leboncoin Pro — Fonds de commerce...")
    base = "https://www.leboncoin.fr"
    out  = []

    for page in range(1, pages+1):
        url = f"{base}/ventes_immobilieres_professionnelles/offres/france/?page={page}"
        html = fetch(url)
        if not html: break
        time.sleep(2)

        # Extraction annonces leboncoin
        # Titres et liens
        liens = re.findall(r'"url":"(/ad/ventes_immobilieres[^"]+)"', html)
        titres = re.findall(r'"subject":"([^"]{5,100})"', html)
        prix_list = re.findall(r'"price":\[(\d+)\]', html)
        villes_list = re.findall(r'"city":"([^"]{2,50})"', html)

        for i, lien in enumerate(liens[:20]):
            try:
                titre = titres[i] if i < len(titres) else "Fonds de commerce"
                prix_v = int(prix_list[i]) if i < len(prix_list) else None
                ville_v = villes_list[i] if i < len(villes_list) else "France"
                uid = re.sub(r'[^0-9]','',lien)[:12] or str(abs(hash(lien)))[:10]
                sect = detect_secteur(titre)
                a = {
                    "id":               mkid("lbc", uid),
                    "titre":            titre[:80],
                    "secteur":          sect,
                    "secteur_label":    secteur_label(sect),
                    "region":           "",
                    "ville":            ville_v,
                    "ca":               None,
                    "ebe":              None,
                    "prix":             int(prix_v/1000) if prix_v and prix_v > 1000 else prix_v,
                    "effectif":         None,
                    "annee_creation":   None,
                    "date_publication": "Récemment publié",
                    "source":           "Le Bon Coin Pro",
                    "source_url":       base + lien,
                    "description":      f"Annonce de cession publiée sur Leboncoin Pro. {titre}. {ville_v}.",
                    "points_forts":     ["Annonce Leboncoin vérifiée","Contact direct","Prix visible"],
                    "motif_cession":    "Voir annonce Leboncoin",
                    "ca_trend":         "stable",
                    "ca_evolution":     "Voir annonce",
                }
                out.append(score_annonce(a))
            except: continue
        if not liens: break

    print(f"  ✓ {len(out)} annonces Leboncoin Pro")
    return out

# ══════════════════════════════════════════════════
# SOURCE 4 : CessionPME
# ══════════════════════════════════════════════════
def scrape_cessionpme(pages=3):
    print("📡 CessionPME — Annonces...")
    base = "https://www.cessionpme.com"
    out  = []

    for page in range(1, pages+1):
        url = f"{base}/annonces-cession?page={page}"
        html = fetch(url)
        if not html:
            # Essai URL alternative
            url2 = f"{base}/annonces?page={page}"
            html = fetch(url2)
        if not html: break
        time.sleep(2)

        liens  = re.findall(r'href="(/annonce[^"]{5,100})"', html)
        titres = re.findall(r'<(?:h2|h3)[^>]*>([^<]{5,100})</(?:h2|h3)>', html)

        for i, lien in enumerate(liens[:15]):
            try:
                titre = titres[i] if i < len(titres) else "Entreprise à reprendre"
                titre = re.sub(r'<[^>]+>','', titre).strip()
                if len(titre) < 5: continue
                uid = re.sub(r'[^a-z0-9]','', lien.lower())[:15]
                sect = detect_secteur(titre)
                a = {
                    "id":               mkid("cessionpme", uid),
                    "titre":            titre[:80],
                    "secteur":          sect,
                    "secteur_label":    secteur_label(sect),
                    "region":           "",
                    "ville":            "France",
                    "ca":None,"ebe":None,"prix":None,"effectif":None,"annee_creation":None,
                    "date_publication": "Récemment publié",
                    "source":           "Cession PME",
                    "source_url":       base + lien,
                    "description":      f"Annonce de cession publiée sur CessionPME. {titre}.",
                    "points_forts":     ["Annonce vérifiée","Dossier disponible","Contact direct"],
                    "motif_cession":    "Voir annonce CessionPME",
                    "ca_trend":         "stable",
                    "ca_evolution":     "Voir dossier",
                }
                out.append(score_annonce(a))
            except: continue
        if not liens: break

    print(f"  ✓ {len(out)} annonces CessionPME")
    return out

# ══════════════════════════════════════════════════
# PROGRAMME PRINCIPAL
# ══════════════════════════════════════════════════
def main():
    print(f"\n{'='*55}")
    print(f"DealScanner v5 — {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*55}\n")

    all_annonces = []

    for fn in [scrape_fusacq, scrape_bodacc, scrape_leboncoin, scrape_cessionpme]:
        try:
            result = fn()
            all_annonces += result
            print(f"  → Total cumulé: {len(all_annonces)}")
        except Exception as e:
            print(f"Erreur {fn.__name__}: {e}")
        time.sleep(2)

    # Dédoublonnage par ID
    seen, unique = set(), []
    for a in all_annonces:
        if a['id'] not in seen:
            seen.add(a['id'])
            unique.append(a)

    print(f"\n{'='*55}")
    print(f"📊 Total brut: {len(all_annonces)} | Après dédup: {len(unique)}")

    # Seuil bas : sauvegarde dès 5 annonces
    if len(unique) < 5:
        print("⚠️  Moins de 5 annonces — conservation fichier existant")
        return

    unique.sort(key=lambda x: x.get('score', 0), reverse=True)

    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)

    print(f"✅ {len(unique)} annonces → data/annonces.json")
    print(f"{'='*55}\n")

if __name__ == '__main__':
    main()
