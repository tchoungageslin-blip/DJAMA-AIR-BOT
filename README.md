# Djama Air Logistics - WhatsApp AI Assistant

Bot WhatsApp intelligent pour la pré-qualification logistique et la billetterie aérienne.

## Architecture

```
├── api/                    # Python FastAPI (Vercel Serverless)
│   ├── index.py           # Entry point + API routes
│   ├── bot/               # AI agent, pricing, vision/OCR
│   ├── db/                # Database connection & queries
│   └── services/          # WhatsApp, sessions, notifications
├── src/                    # Next.js Dashboard (App Router)
│   ├── app/               # Pages
│   │   ├── login/
│   │   └── dashboard/     # Inbox, Orders, Supervision, Settings
│   └── lib/               # Utilities
├── prisma/                # Database schema
├── scripts/               # SQL seeds
└── vercel.json            # Deployment config
```

## Stack

- **Frontend**: Next.js 14, TailwindCSS, Lucide Icons
- **Backend**: Python FastAPI (Vercel Serverless Functions)
- **IA**: GPT-4o (OpenAI) - texte + vision/OCR
- **DB**: PostgreSQL (Vercel Postgres / Neon)
- **Cache**: Redis (Vercel KV / Upstash)
- **WhatsApp**: Vendrix.net (Meta Cloud API)
- **Hosting**: Vercel

## Setup

### 1. Installer les dépendances

```bash
npm install
```

### 2. Configurer l'environnement

```bash
cp .env.example .env
# Remplir les variables dans .env
```

### 3. Initialiser la base de données

```bash
npx prisma db push
# Puis exécuter scripts/init-db.sql pour les données initiales
```

### 4. Lancer en développement

```bash
npm run dev
```

### 5. Déployer sur Vercel

```bash
vercel --prod
```

## Variables d'Environnement Requises

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Clé API OpenAI (GPT-4o) |
| `DATABASE_URL` | URL PostgreSQL (Neon/Vercel Postgres) |
| `REDIS_URL` | URL Redis (Upstash/Vercel KV) |
| `VENDRIX_API_KEY` | Clé API Vendrix.net |
| `VENDRIX_WEBHOOK_SECRET` | Secret de vérification webhook |
| `JWT_SECRET` | Secret pour les tokens JWT dashboard |

## Fonctionnalités

### Bot WhatsApp
- Identification automatique des clients récurrents
- Estimation tarifaire instantanée (aérien/maritime)
- Détection des cas sensibles (batteries, liquides, etc.)
- Analyse d'images/PDF (OCR chinois/français/anglais)
- Multi-colis avec calcul séparé normal/fragile
- Adaptation automatique à la langue du client
- Handoff intelligent vers l'équipe humaine

### Dashboard
- **Inbox** : Conversations triées par statut avec chat en temps réel
- **Commandes** : Tableaux Fret / Billetterie / Packs
- **Supervision** : Kill-switch global, silent takeover, audit
- **Paramètres** : Grilles tarifaires, notifications, SLA

## Grille Tarifaire (Défaut)

### Aérien - Chine → Cameroun
| Poids | Prix/kg |
|-------|---------|
| 0-25 kg | 10 000 FCFA |
| 25-100 kg | 7 500 FCFA |
| +100 kg | 6 000 FCFA |

### Aérien - International → Cameroun
| Poids | Prix/kg |
|-------|---------|
| <100 kg | 10 500 FCFA |
| +100 kg | 8 000 FCFA |

---

**Djama Air Logistics** - *Nous relions vos ambitions*
