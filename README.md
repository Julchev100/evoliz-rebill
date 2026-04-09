---
title: Evoliz Rebill
emoji: 📑
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
short_description: Refacturer les achats Evoliz marques billable
---

# evoliz-rebill

Petit outil web local pour refacturer aux clients les factures d'achat
marquées `billable=true` dans Evoliz.

> Le frontmatter YAML ci-dessus est interprété par Hugging Face Spaces
> et ignoré par GitHub.

## Installation

```bash
python -m venv .venv
. .venv/Scripts/activate          # Windows
pip install -e .
cp .env.example .env              # puis éditer avec vos clés
uvicorn app.main:app --reload
```

Ouvrir http://localhost:8000

## Comment ça marche

1. L'outil interroge `GET /companies/{id}/buys` paginé.
2. Filtre les achats `billable=true` ayant un `client` rattaché.
3. Exclut ceux déjà refacturés (table SQLite locale `data/rebill.db`).
4. Affiche le reste, groupé par client.
5. Sur clic, crée des factures de vente **en brouillon** via
   `POST /companies/{id}/invoices` (une facture par client, une ligne par
   achat).
6. Marque les achats traités en base locale.

## Déploiement Hugging Face Spaces (gratuit, sans CB)

1. **Crée la Space** : https://huggingface.co/new-space
   - Owner : ton compte HF
   - Space name : `evoliz-rebill`
   - License : MIT (ou autre)
   - SDK : **Docker**
   - Visibility : Private (recommandé) ou Public

2. **Pousse le code** vers le repo de la Space (HuggingFace fournit l'URL git) :
   ```bash
   git remote add hf https://huggingface.co/spaces/<TON_USER>/evoliz-rebill
   git push hf main
   ```
   Ou via le bouton « Files » → « Upload files » dans l'UI HF.

3. **Configure les secrets** dans Settings → Variables and secrets :
   - `EVOLIZ_PUBLIC_KEY` (Secret)
   - `EVOLIZ_SECRET_KEY` (Secret)
   - `APP_PASSWORD` (Secret) — mot de passe d'accès au site
   - `APP_USER` (Variable, optionnel, défaut `admin`)

4. La Space rebuilds automatiquement. À l'ouverture de l'URL, le navigateur
   te demandera user/mot de passe via HTTP Basic Auth.

### Persistance et HF Spaces gratuit

Le filesystem est éphémère sur le tier gratuit : la SQLite locale est
**wipée à chaque redémarrage** de la Space. C'est pour ça que :

- **Les clés API doivent venir des Secrets HF** (pas de `/settings` UI),
  l'app le détecte automatiquement et désactive le formulaire.
- **L'historique « déjà refacturé »** est reconstruit à chaque scan en
  parsant les commentaires des factures de vente Evoliz : chaque facture
  générée contient un marqueur `[BUYS:id1,id2,...]` qui sert de source
  de vérité. Source = Evoliz, donc immune à un wipe HF.

## Déploiement local (alternative)

Pour un usage purement personnel sans cloud :
```bash
python -m venv .venv && . .venv/Scripts/activate
pip install -e .
uvicorn app.main:app
```
Saisis tes clés via `/settings` (stockées en SQLite locale persistante).

## Limites

- Mono-utilisateur, mono-société : une instance déployée = un compte Evoliz.
  Pour du vrai multi-tenant (plusieurs entreprises sur une seule URL),
  il faudrait ajouter un système de comptes utilisateurs et l'isolation
  des données.
- Les factures sont créées en brouillon : à valider/ajuster manuellement
  dans Evoliz avant envoi.
- Si vous supprimez une facture brouillon dans Evoliz, l'achat reste
  marqué comme refacturé en local — il faut le retirer manuellement de
  `data/rebill.db` pour le retraiter.
