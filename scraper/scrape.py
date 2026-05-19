#!/usr/bin/env python3
"""DealScanner Scraper v4 — URLs corrigées 2025"""

import json, time, datetime, hashlib, os, re
import urllib.request, urllib.parse

DATA_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'annonces.json')

SECTEUR_MAP = {
    'industrie':    ['industrie','fabrication','usinage','mécanique','btp','construction','bâtiment','métallurgie','menuiserie','plomberie','maçonnerie','soudure','charpente'],
    'services':     ['conseil','audit','comptable','juridique','rh','formation','communication','service','agence','cabinet','nettoyage','sécurité','gardiennage'],
    'commerce':     ['commerce','distribution','retail','négoce','vente','import','export','boutique','magasin','épicerie','boucherie','fleuriste','tabac'],
    'tech':         ['informatique','logiciel','numérique','digital','web','saas','cloud','tech','développement','internet','ecommerce'],
    'sante':        ['santé','médical','pharmacie','dentaire','clinique','optique','infirmier','kiné','ostéo','vétérinaire','laboratoire'],
    'restauration': ['restaurant','brasserie','boulangerie','hôtel','café','traiteur','pizzeria','snack','bar','crêperie','pâtisserie'],
    'transport':    ['transport','logistique','livraison','fret','déménagement','taxi','vtc','ambulance'],
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

def fetch(url, t=20, accept='application/json'):
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        'Accept': accept,
        'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=t) as r:
            raw = r.read()
            if accept == 'application/json':
                return json.loads(raw.decode('utf-8'))
            else:
                for enc in ['utf-8','latin-1']:
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

# ── BODACC — URL corrigée 2025 ────────────────────────────────────
def scrape_bodacc(n=100):
    print("📡 BODACC — Ventes fonds de commerce...")
    # Nouvelle URL API v1 (plus stable)
    url = (
        "https://bodacc-datadila.opendatasoft.com/api/records/1.0/search/"
        "?dataset=annonces-commerciales-bodacc-a-b"
        "&q=typeavis%3AVente"
        "&sort=dateparution"
        "&rows=100"
        "&facet=typeavis"
    )
    data = fetch(url)

    # Fallback URL v2
    if not data:
        url2 = (
            "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets"
            "/annonces-commerciales-bodacc-a-b/records"
            "?select=*&where=typeavis%3D%22Vente%22"
            f"&order_by=dateparution%20desc&limit=100"
        )
        data = fetch(url2)

    if not data:
        print("  BODACC non disponible"); return []

    # Parser les deux formats possibles
    records = (data.get('records') or  # format v1
               data.get('results') or  # format v2
               [])

    out = []
    for rec in records[:n]:
        try:
            # Format v1
            fields = rec.get('fields', rec)
            ville    = fields.get('ville','') or ''
            dept     = fields.get('departement_nom_officiel','') or fields.get('departement','') or ''
            date_s   = fields.get('dateparution','') or ''
            num      = fields.get('numerounique','') or str(abs(hash(str(rec))))[:8]
            acte     = fields.get('acte') or {}
            activite = ''
            if isinstance(acte, dict):
                activite = acte.get('activite','') or acte.get('descriptif','') or ''
            if not activite:
                activite = fields.get('commercant','') or ''
            if not activite and not ville: continue

            sect  = detect_secteur(activite)
            annee = date_s[:4] if date_s else '2025'
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
                "description":      f"Vente fonds de commerce — BODACC officiel. {activite[:100] or 'Activité non précisée'}. {ville}, {dept}.",
                "points_forts":     ["Publication légale officielle","Cession authentifiée BODACC","Dossier vérifiable"],
                "motif_cession":    "Annonce légale BODACC",
                "ca_trend":         "stable", "ca_evolution": "Non communiqué",
            }
            out.append(score_annonce(a))
        except: continue

    print(f"  ✓ {len(out)} annonces")
    return out

# ── BODACC Procédures ─────────────────────────────────────────────
def scrape_bodacc_procedures(n=40):
    print("📡 BODACC — Procédures collectives (reprises)...")
    url = (
        "https://bodacc-datadila.opendatasoft.com/api/records/1.0/search/"
        "?dataset=annonces-commerciales-bodacc-a-b"
        "&q=typeavis%3ARedressement+OR+typeavis%3ASauvegarde"
        "&sort=dateparution&rows=50"
    )
    data = fetch(url)
    if not data: print("  Non disponible"); return []

    records = data.get('records', [])
    out = []
    for rec in records[:n]:
        try:
            fields   = rec.get('fields', rec)
            ville    = fields.get('ville','') or ''
            dept     = fields.get('departement_nom_officiel','') or ''
            date_s   = fields.get('dateparution','') or ''
            num      = fields.get('numerounique','') or str(abs(hash(str(rec))))[:8]
            acte     = fields.get('acte') or {}
            activite = ''
            if isinstance(acte, dict): activite = acte.get('activite','') or ''
            if not activite: activite = fields.get('commercant','') or ''
            if not activite: continue
            sect = detect_secteur(activite)
            a = {
                "id":               mkid("bodaccb", num),
                "titre":            f"⚖️ Reprise possible — {activite[:60]}",
                "secteur":          sect, "secteur_label": secteur_label(sect),
                "region":           dept, "ville": ville,
                "ca":None,"ebe":None,"prix":None,"effectif":None,"annee_creation":None,
                "date_publication": age_label(date_s),
                "source":           "BODACC",
                "source_url":       "https://www.bodacc.fr",
                "description":      f"Entreprise en procédure collective — reprise possible. {activite[:100]}. {ville}, {dept}.",
                "points_forts":     ["Prix de reprise négociable","Actifs potentiellement valorisables","Procédure encadrée par le tribunal"],
                "motif_cession":    "Redressement / Sauvegarde judiciaire",
                "ca_trend":         "down", "ca_evolution": "À évaluer avec le mandataire",
            }
            out.append(score_annonce(a))
        except: continue
    print(f"  ✓ {len(out)} procédures")
    return out

# ── Fusacq — scraping HTML ────────────────────────────────────────
def scrape_fusacq(pages=5):
    print("📡 Fusacq — Scraping annonces...")
    base = "https://www.fusacq.com"
    out  = []

    for page in range(1, pages+1):
        url  = f"{base}/reprendre-une-entreprise/annonces-cession-entreprise_fr_?p={page}"
        html = fetch(url, accept='text/html')
        if not html: break
        time.sleep(2)

        # Extraction liens + titres
        liens = re.findall(
            r'href="(/vente-entreprise[^"]{10,200})"[^>]*>\s*([^<]{5,100})',
            html
        )
        if not liens:
            # Pattern alternatif
            liens_raw = re.findall(r'href="(/vente-entreprise[^"]+)"', html)
            titres_raw = re.findall(r'<(?:h2|h3|a)[^>]*class="[^"]*(?:title|titre|nom)[^"]*"[^>]*>([^<]{5,100})<', html)
            liens = list(zip(liens_raw[:20], titres_raw[:20]))

        for lien, titre in liens[:20]:
            try:
                titre = re.sub(r'<[^>]+>','', titre).strip()
                if len(titre) < 5: continue
                # Extraire infos depuis l'URL
                parts = lien.split('-')
                ville = ''
                for p in parts[::-1]:
                    if len(p) > 3 and p.isalpha():
                        ville = p.capitalize()
                        break
                uid  = lien.split(',')[-1].split('_')[0] or str(abs(hash(lien)))[:8]
                sect = detect_secteur(titre)
                a = {
                    "id":               mkid("fusacq", uid),
                    "titre":            titre[:75],
                    "secteur":          sect, "secteur_label": secteur_label(sect),
                    "region":           "", "ville": ville or "France",
                    "ca":None,"ebe":None,"prix":None,"effectif":None,"annee_creation":None,
                    "date_publication": "Récemment publié",
                    "source":           "Fusacq",
                    "source_url":       base + lien,
                    "description":      f"Annonce de cession d'entreprise publiée sur Fusacq. {titre}.",
                    "points_forts":     ["Annonce vérifiée Fusacq","Dossier disponible sur demande","Contact direct avec le cédant"],
                    "motif_cession":    "Voir annonce complète sur Fusacq",
                    "ca_trend":         "stable", "ca_evolution": "Voir dossier",
                }
                out.append(score_annonce(a))
            except: continue
        if not liens: break

    print(f"  ✓ {len(out)} annonces Fusacq")
    return out

# ── CCI / Transentreprise ─────────────────────────────────────────
def scrape_cci(pages=3):
    print("📡 CCI / Transentreprise...")
    # URL corrigée
    urls_to_try = [
        "https://www.transentreprise.com/annonces-cession",
        "https://www.transentreprise.com/entreprises-a-reprendre",
        "https://www.transentreprise.com/annonces",
    ]
    base = "https://www.transentreprise.com"
    out  = []

    for base_url in urls_to_try:
        for page in range(1, pages+1):
            sep = '&' if '?' in base_url else '?'
            url = f"{base_url}{sep}page={page}"
            html = fetch(url, accept='text/html')
            if not html: continue
            time.sleep(1.5)

            # Extraction
            liens  = re.findall(r'href="(/(?:annonce|entreprise|offre)[^"]{5,100})"', html)
            titres = re.findall(r'<(?:h2|h3)[^>]*>([^<]{10,120})</(?:h2|h3)>', html)

            if not liens: continue

            for i, lien in enumerate(liens[:15]):
                try:
                    titre = titres[i] if i < len(titres) else "Entreprise à reprendre"
                    titre = re.sub(r'<[^>]+>','', titre).strip()
                    if len(titre) < 5: continue
                    sect = detect_secteur(titre)
                    a = {
                        "id":               mkid("cci", lien),
                        "titre":            titre[:75],
                        "secteur":          sect, "secteur_label": secteur_label(sect),
                        "region":           "", "ville": "France",
                        "ca":None,"ebe":None,"prix":None,"effectif":None,"annee_creation":None,
                        "date_publication": "Récemment publié",
                        "source":           "CCI France",
                        "source_url":       base + lien,
                        "description":      f"Annonce de cession — réseau CCI France / Transentreprise. {titre}.",
                        "points_forts":     ["Réseau CCI officiel","Accompagnement disponible","Dossier vérifié par la CCI"],
                        "motif_cession":    "Voir annonce complète",
                        "ca_trend":         "stable", "ca_evolution": "Voir dossier",
                    }
                    out.append(score_annonce(a))
                except: continue
            break  # URL trouvée

    print(f"  ✓ {len(out)} annonces CCI")
    return out

# ── Programme principal ───────────────────────────────────────────
def main():
    print(f"\n{'='*55}")
    print(f"DealScanner v4 — {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*55}\n")

    all_annonces = []

    for fn in [scrape_bodacc, scrape_bodacc_procedures, scrape_fusacq, scrape_cci]:
        try: all_annonces += fn()
        except Exception as e: print(f"Erreur {fn.__name__}: {e}")
        time.sleep(2)

    # Dédoublonnage
    seen, unique = set(), []
    for a in all_annonces:
        if a['id'] not in seen:
            seen.add(a['id'])
            unique.append(a)

    print(f"\n📊 Total: {len(all_annonces)} | Dédup: {len(unique)}")

    if len(unique) < 10:
        print("⚠️  Pas assez de données — conservation fichier existant")
        return

    unique.sort(key=lambda x: x.get('score',0), reverse=True)

    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)

    print(f"✅ {len(unique)} annonces → data/annonces.json")
    print(f"{'='*55}\n")

if __name__ == '__main__':
    main()
