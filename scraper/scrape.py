#!/usr/bin/env python3
"""
DealScanner — Scraper de vraies annonces
Sources légales :
  - BODACC (data.gouv.fr) — annonces légales de cession
  - Bpifrance API publique
Sauvegarde dans data/annonces.json
"""

import json
import time
import random
import hashlib
import datetime
import urllib.request
import urllib.parse
import os
import re

DATA_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'annonces.json')

# ── Mapping secteurs BODACC → DealScanner ────────────────────────────────────
SECTEUR_MAP = {
    'industrie':     ['industrie', 'fabrication', 'usinage', 'mécanique', 'btp', 'construction', 'bâtiment', 'métallurgie', 'plasturgie'],
    'services':      ['conseil', 'audit', 'comptable', 'juridique', 'rh', 'formation', 'communication', 'service'],
    'commerce':      ['commerce', 'distribution', 'retail', 'négoce', 'vente', 'import', 'export'],
    'tech':          ['informatique', 'logiciel', 'numérique', 'digital', 'web', 'saas', 'cloud', 'tech'],
    'sante':         ['santé', 'médical', 'pharmacie', 'paramédical', 'dentaire', 'clinique', 'optique'],
    'restauration':  ['restaurant', 'brasserie', 'boulangerie', 'hôtel', 'hcr', 'café', 'traiteur', 'pizzeria'],
    'transport':     ['transport', 'logistique', 'livraison', 'fret', 'déménagement', 'taxi'],
}

def detect_secteur(texte):
    """Détecte le secteur depuis un texte libre."""
    texte = texte.lower()
    for secteur, mots in SECTEUR_MAP.items():
        if any(m in texte for m in mots):
            return secteur
    return 'services'

def secteur_label(secteur):
    labels = {
        'industrie': 'Industrie',
        'services':  'Services B2B',
        'commerce':  'Commerce',
        'tech':      'Tech & Digital',
        'sante':     'Santé',
        'restauration': 'Restauration',
        'transport': 'Transport',
    }
    return labels.get(secteur, 'Services')

def make_id(source, uid):
    return hashlib.sha256(f"{source}:{uid}".encode()).hexdigest()[:12]

def fetch_json(url, timeout=15):
    """Fetch HTTP avec User-Agent réaliste."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; DealScanner/1.0)',
        'Accept': 'application/json',
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f"  Erreur fetch {url[:60]}: {e}")
        return None

# ── Source 1 : BODACC (data.gouv.fr) — 100% légal ───────────────────────────
def scrape_bodacc(max_results=50):
    """
    BODACC = Bulletin Officiel des Annonces Civiles et Commerciales
    Toutes les ventes de fonds de commerce publiées légalement en France.
    API publique : data.gouv.fr
    """
    print("📡 BODACC — Ventes de fonds de commerce...")
    annonces = []
    
    # API BODACC via data.gouv.fr
    url = (
        "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets"
        "/annonces-commerciales-bodacc-a-b/records"
        "?where=typeavis%3D%27Vente%27"
        "&order_by=dateparution%20desc"
        f"&limit={min(max_results, 100)}"
        "&timezone=Europe%2FParis"
    )
    
    data = fetch_json(url)
    if not data or 'results' not in data:
        print("  BODACC non disponible")
        return []

    for rec in data.get('results', []):
        try:
            # Extraction des champs BODACC
            acte = rec.get('acte', {}) or {}
            registre = rec.get('registre', '') or ''
            ville = rec.get('ville', '') or ''
            dept = rec.get('departement_nom_officiel', '') or ''
            date_str = rec.get('dateparution', '') or ''
            numero = rec.get('numerounique', str(random.randint(10000, 99999)))
            
            # Description de l'activité
            activite = ''
            if isinstance(acte, dict):
                activite = acte.get('activite', '') or acte.get('descriptif', '') or ''
            if not activite:
                activite = rec.get('commercant', '') or ''
            
            if not activite and not ville:
                continue

            # Région depuis département
            region = dept if dept else 'France'
            
            # Secteur
            secteur = detect_secteur(activite + ' ' + registre)
            
            # Date de publication
            pub = 'Récemment publié'
            if date_str:
                try:
                    d = datetime.datetime.fromisoformat(date_str[:10])
                    delta = (datetime.datetime.now() - d).days
                    if delta == 0:     pub = "Publié aujourd'hui"
                    elif delta == 1:   pub = "Publié hier"
                    elif delta < 7:    pub = f"il y a {delta} jours"
                    elif delta < 30:   pub = f"il y a {delta//7} semaine(s)"
                    else:              pub = f"il y a {delta//30} mois"
                except:
                    pass

            annonce = {
                "id":               make_id("bodacc", str(numero)),
                "titre":            (activite[:80] if activite else f"Fonds de commerce — {ville}").strip(),
                "secteur":          secteur,
                "secteur_label":    secteur_label(secteur),
                "region":           region,
                "ville":            ville,
                "ca":               None,
                "ebe":              None,
                "prix":             None,
                "effectif":         None,
                "annee_creation":   None,
                "date_publication": pub,
                "source":           "BODACC",
                "source_url":       f"https://www.bodacc.fr/annonce/detail-annonce/A/{date_str[:4] if date_str else '2025'}/{numero}",
                "score":            60,
                "score_financier":  60,
                "score_valorisation": 55,
                "score_croissance": 60,
                "score_risque":     65,
                "description":      f"Cession de fonds de commerce publiée au BODACC. Activité : {activite[:100] if activite else 'Non précisée'}. Localisation : {ville}, {region}.",
                "points_forts":     ["Publication légale officielle", "Cession authentifiée", "Dossier vérifiable"],
                "motif_cession":    "Annonce légale de cession",
                "ca_trend":         "stable",
                "ca_evolution":     "Non communiqué",
            }
            annonces.append(annonce)
            
        except Exception as e:
            print(f"  Erreur parsing: {e}")
            continue

    print(f"  ✓ {len(annonces)} annonces BODACC récupérées")
    return annonces

# ── Source 2 : API Entreprises data.gouv.fr ──────────────────────────────────
def scrape_api_entreprises(max_results=30):
    """
    Recherche d'entreprises en cession via l'API publique.
    """
    print("📡 API Entreprises — Recherche cessions...")
    annonces = []
    
    # Secteurs à scraper
    queries = ['cession fonds commerce', 'vente entreprise', 'transmission entreprise']
    
    for q in queries[:1]:  # 1 requête pour éviter rate limiting
        url = (
            f"https://recherche-entreprises.api.gouv.fr/search"
            f"?q={urllib.parse.quote(q)}"
            f"&page=1&per_page=20"
        )
        data = fetch_json(url)
        if not data:
            continue
            
        for res in data.get('results', [])[:10]:
            try:
                nom = res.get('nom_complet', '') or res.get('nom_raison_sociale', '')
                if not nom:
                    continue
                    
                siege = res.get('siege', {}) or {}
                ville = siege.get('libelle_commune', '') or ''
                dept = siege.get('libelle_departement', '') or ''
                activite_principale = res.get('activite_principale', '') or ''
                libelle_activite = res.get('libelle_activite_principale', '') or ''
                
                secteur = detect_secteur(libelle_activite + ' ' + activite_principale)
                siren = res.get('siren', str(random.randint(100000000, 999999999)))
                
                annonce = {
                    "id":               make_id("apientreprises", siren),
                    "titre":            f"{nom[:70]} — {libelle_activite[:40] if libelle_activite else 'Entreprise'}",
                    "secteur":          secteur,
                    "secteur_label":    secteur_label(secteur),
                    "region":           dept,
                    "ville":            ville,
                    "ca":               None,
                    "ebe":              None,
                    "prix":             None,
                    "effectif":         None,
                    "annee_creation":   None,
                    "date_publication": "Récemment publié",
                    "source":           "API Entreprises",
                    "source_url":       f"https://annuaire-entreprises.data.gouv.fr/entreprise/{siren}",
                    "score":            55,
                    "score_financier":  55,
                    "score_valorisation": 50,
                    "score_croissance": 60,
                    "score_risque":     55,
                    "description":      f"{nom}. Activité : {libelle_activite or activite_principale}. Localisation : {ville}, {dept}.",
                    "points_forts":     ["Données officielles", "SIREN vérifié", "Entreprise active"],
                    "motif_cession":    "À préciser avec le cédant",
                    "ca_trend":         "stable",
                    "ca_evolution":     "Non communiqué",
                }
                annonces.append(annonce)
            except Exception as e:
                continue
        
        time.sleep(1)  # Respecte le rate limit

    print(f"  ✓ {len(annonces)} entreprises trouvées")
    return annonces

# ── Calcul DealScore ─────────────────────────────────────────────────────────
def compute_score(annonce):
    """Calcule le DealScore si les données financières sont disponibles."""
    score = 60  # Base neutre si pas de données financières
    
    if annonce.get('ca') and annonce.get('ebe'):
        ca, ebe = annonce['ca'], annonce['ebe']
        marge = ebe / ca if ca > 0 else 0
        
        # Santé financière
        s_fin = 50
        if marge > 0.20: s_fin += 25
        elif marge > 0.12: s_fin += 15
        elif marge > 0.08: s_fin += 5
        
        # Valorisation
        s_val = 60
        if annonce.get('prix') and ebe > 0:
            multiple = annonce['prix'] / ebe
            if multiple < 3: s_val = 85
            elif multiple < 5: s_val = 70
            elif multiple < 8: s_val = 55
            else: s_val = 40
        
        score = int((s_fin * 0.4) + (s_val * 0.3) + (60 * 0.3))
        annonce['score_financier'] = s_fin
        annonce['score_valorisation'] = s_val
    
    # Bonus secteur
    bonus = {'tech': 15, 'sante': 10, 'services': 5, 'restauration': -5}
    score += bonus.get(annonce.get('secteur', ''), 0)
    
    annonce['score'] = max(40, min(95, score))
    return annonce

# ── Programme principal ──────────────────────────────────────────────────────
def main():
    print(f"\n{'='*50}")
    print(f"DealScanner Scraper — {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*50}")
    
    all_annonces = []
    
    # Source 1 : BODACC
    try:
        bodacc = scrape_bodacc(max_results=80)
        all_annonces.extend(bodacc)
    except Exception as e:
        print(f"Erreur BODACC: {e}")
    
    time.sleep(2)
    
    # Source 2 : API Entreprises
    try:
        api_ent = scrape_api_entreprises(max_results=20)
        all_annonces.extend(api_ent)
    except Exception as e:
        print(f"Erreur API Entreprises: {e}")
    
    # Calcul des scores
    all_annonces = [compute_score(a) for a in all_annonces]
    
    # Dédoublonnage par ID
    seen = set()
    unique = []
    for a in all_annonces:
        if a['id'] not in seen:
            seen.add(a['id'])
            unique.append(a)
    
    # Si pas assez de vraies annonces, on garde les anciennes
    if len(unique) < 10:
        print(f"⚠️  Seulement {len(unique)} annonces récupérées — conservation des données existantes")
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            print(f"✓ {len(existing)} annonces existantes conservées")
            return
        except:
            pass
    
    # Tri par score
    unique.sort(key=lambda x: x.get('score', 0), reverse=True)
    
    # Sauvegarde
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*50}")
    print(f"✅ {len(unique)} annonces sauvegardées dans data/annonces.json")
    print(f"{'='*50}\n")

if __name__ == '__main__':
    main()
