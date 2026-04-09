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

## Limites

- Mono-utilisateur, mono-société.
- Les factures sont créées en brouillon : à valider/ajuster manuellement
  dans Evoliz avant envoi.
- Si vous supprimez une facture brouillon dans Evoliz, l'achat reste
  marqué comme refacturé en local — il faut le retirer manuellement de
  `data/rebill.db` pour le retraiter.
