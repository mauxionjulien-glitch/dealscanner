# 🔍 DealScanner

> Le Skyscanner des cessions d'entreprises françaises

## Architecture

```
GitHub (ce repo)
├── index.html          ← Site web complet
├── data/
│   └── annonces.json   ← Annonces scrappées (mis à jour auto)
├── scraper/
│   └── scrape.py       ← Scraper Python (BODACC + API Entreprises)
└── .github/workflows/
    └── scrape.yml      ← Automatisation toutes les 4h
```

## Fonctionnement

1. **GitHub Actions** lance `scraper/scrape.py` toutes les 4h
2. Le scraper récupère les vraies annonces depuis BODACC et l'API Entreprises
3. Les données sont sauvegardées dans `data/annonces.json`
4. Le site lit ce fichier JSON et affiche les annonces

## Sources de données

| Source | Type | Légalité |
|--------|------|----------|
| BODACC | API publique data.gouv.fr | ✅ 100% légal |
| API Entreprises | API publique gouvernementale | ✅ 100% légal |

## Lancer le scraper manuellement

```bash
python scraper/scrape.py
```

## Déploiement

Le site est hébergé sur Netlify. À chaque mise à jour de `data/annonces.json`,
Netlify redéploie automatiquement le site.
