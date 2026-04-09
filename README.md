# evoliz-rebill

Petit outil web local pour refacturer aux clients les factures d'achat
marquées `billable=true` dans Evoliz.

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

## Déploiement Fly.io (mono-tenant + Basic Auth)

L'app est mono-utilisateur : une instance Fly.io = un compte Evoliz.
Protégée par HTTP Basic Auth dès qu'`APP_PASSWORD` est défini.

```bash
# 1. installer flyctl : https://fly.io/docs/flyctl/install/
# 2. se connecter (1 fois)
fly auth login

# 3. créer l'app (utilise fly.toml fourni). NE PAS déployer tout de suite.
fly launch --no-deploy --copy-config

# 4. créer le volume persistant (1 GB suffit)
fly volumes create data --size 1 --region cdg

# 5. définir le mot de passe d'accès (le user est "admin" par défaut)
fly secrets set APP_PASSWORD='choisis-un-mot-de-passe-fort'
# optionnel : changer le username
# fly secrets set APP_USER='julien'

# 6. déployer
fly deploy
```

Tu obtiens une URL `https://evoliz-rebill.fly.dev` (ou similaire). Au 1er
accès, le navigateur te demande user/mot de passe. Ensuite, va sur
`/settings` pour saisir tes clés API Evoliz (stockées sur le volume
persistant).

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
