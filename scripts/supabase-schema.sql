-- ============================================
-- Djama Air Logistics - Supabase Schema
-- Execute dans Supabase > SQL Editor
-- ============================================

-- =====================
-- EXTENSIONS
-- =====================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =====================
-- ENUMS
-- =====================
CREATE TYPE client_type AS ENUM ('NEW', 'RECURRENT', 'VIP');
CREATE TYPE session_status AS ENUM ('BOT_ACTIVE', 'HUMAN_HANDOFF', 'HUMAN_ACTIVE', 'RESOLVED', 'CLOSED');
CREATE TYPE session_intent AS ENUM ('FRET', 'BILLETTERIE', 'PACK', 'COMPLAINT', 'GENERAL', 'UNKNOWN');
CREATE TYPE shipping_mode AS ENUM ('AERIEN', 'MARITIME', 'DHL_EXPRESS');
CREATE TYPE colis_nature AS ENUM ('NORMAL', 'FRAGILE', 'SENSIBLE');
CREATE TYPE ticket_type AS ENUM ('ALLER_SIMPLE', 'ALLER_RETOUR');
CREATE TYPE order_type AS ENUM ('FRET', 'BILLETTERIE', 'PACK');
CREATE TYPE order_status AS ENUM ('NOUVEAU', 'PRIS_EN_CHARGE', 'EN_COURS', 'LIVRE', 'ANNULE', 'HANDOFF');
CREATE TYPE agent_role AS ENUM ('ADMIN', 'AGENT_FRET', 'AGENT_BILLETTERIE', 'SUPERVISEUR');

-- =====================
-- CLIENTS
-- =====================
CREATE TABLE clients (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  phone_number TEXT UNIQUE NOT NULL,
  first_name TEXT,
  last_name TEXT,
  client_type client_type DEFAULT 'NEW' NOT NULL,
  language TEXT DEFAULT 'fr' NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_clients_phone ON clients(phone_number);

-- =====================
-- PREFERENCES
-- =====================
CREATE TABLE preferences (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  client_id TEXT UNIQUE NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  frequent_destinations TEXT[] DEFAULT '{}',
  frequent_goods TEXT[] DEFAULT '{}',
  preferred_mode TEXT,
  notes TEXT
);

-- =====================
-- AGENTS
-- =====================
CREATE TABLE agents (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  full_name TEXT NOT NULL,
  role agent_role DEFAULT 'AGENT_FRET' NOT NULL,
  is_active BOOLEAN DEFAULT true NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_agents_email ON agents(email);

-- =====================
-- SESSIONS
-- =====================
CREATE TABLE sessions (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  status session_status DEFAULT 'BOT_ACTIVE' NOT NULL,
  current_intent session_intent DEFAULT 'UNKNOWN' NOT NULL,
  agent_id TEXT REFERENCES agents(id),
  tags TEXT[] DEFAULT '{}',
  ai_summary TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
  closed_at TIMESTAMPTZ
);

CREATE INDEX idx_sessions_client ON sessions(client_id);
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_updated ON sessions(updated_at DESC);

-- =====================
-- MESSAGES
-- =====================
CREATE TABLE messages (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  sender TEXT NOT NULL,
  content TEXT NOT NULL,
  media_url TEXT,
  media_type TEXT,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_messages_session ON messages(session_id);
CREATE INDEX idx_messages_created ON messages(created_at);

-- =====================
-- LEADS - FRET
-- =====================
CREATE TABLE leads_fret (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  session_id TEXT,
  goods_nature TEXT,
  colis_nature colis_nature DEFAULT 'NORMAL' NOT NULL,
  weight_real DOUBLE PRECISION,
  weight_volumetric DOUBLE PRECISION,
  weight_billable DOUBLE PRECISION,
  length_cm DOUBLE PRECISION,
  width_cm DOUBLE PRECISION,
  height_cm DOUBLE PRECISION,
  origin TEXT,
  destination TEXT,
  shipping_mode shipping_mode DEFAULT 'AERIEN' NOT NULL,
  estimated_price INTEGER,
  pack_type TEXT,
  is_sensitive BOOLEAN DEFAULT false NOT NULL,
  sensitive_reason TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_leads_fret_client ON leads_fret(client_id);

-- =====================
-- LEADS - BILLETTERIE
-- =====================
CREATE TABLE leads_billet (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  session_id TEXT,
  departure TEXT,
  destination TEXT,
  date_depart TIMESTAMPTZ,
  date_retour TIMESTAMPTZ,
  pax_count INTEGER,
  pax_details TEXT,
  ticket_type ticket_type DEFAULT 'ALLER_SIMPLE' NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_leads_billet_client ON leads_billet(client_id);

-- =====================
-- ORDERS
-- =====================
CREATE TABLE orders (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  order_number TEXT UNIQUE NOT NULL,
  client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  order_type order_type NOT NULL,
  status order_status DEFAULT 'NOUVEAU' NOT NULL,
  data JSONB NOT NULL DEFAULT '{}',
  estimated_price INTEGER,
  final_price INTEGER,
  assigned_agent TEXT,
  shipping_mark TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_orders_client ON orders(client_id);
CREATE INDEX idx_orders_type ON orders(order_type);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_number ON orders(order_number);

-- =====================
-- PRICING GRIDS
-- =====================
CREATE TABLE pricing_grids (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  mode TEXT NOT NULL,
  origin TEXT NOT NULL,
  rules JSONB NOT NULL,
  currency TEXT DEFAULT 'FCFA' NOT NULL,
  valid_from TIMESTAMPTZ DEFAULT NOW() NOT NULL,
  valid_until TIMESTAMPTZ,
  updated_by TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_pricing_mode ON pricing_grids(mode, origin);

-- =====================
-- SETTINGS
-- =====================
CREATE TABLE settings (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  key TEXT UNIQUE NOT NULL,
  value TEXT NOT NULL
);

-- =====================
-- NOTIFICATIONS
-- =====================
CREATE TABLE notifications (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  type TEXT NOT NULL,
  channel TEXT NOT NULL,
  recipient TEXT NOT NULL,
  message TEXT NOT NULL,
  session_id TEXT,
  sent BOOLEAN DEFAULT false NOT NULL,
  sent_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_notifications_channel ON notifications(channel);
CREATE INDEX idx_notifications_created ON notifications(created_at DESC);


-- ============================================
-- SEED DATA
-- ============================================

-- Admin agent
-- Email: airdjama@gmail.com | Password: airdjama2026
-- Hash: SHA-256 with salt = JWT_SECRET[:16] ("change-me-in-pro")
-- IMPORTANT: If you change JWT_SECRET, you must re-create this admin!
INSERT INTO agents (id, email, password_hash, full_name, role, is_active, created_at)
VALUES (
  gen_random_uuid()::text,
  'airdjama@gmail.com',
  'c08e33232ccd460aa5cf233eb545e8210108c9a1750a954818bdc217f2515719',
  'Abdelkarim',
  'ADMIN',
  true,
  NOW()
);

-- Default settings
INSERT INTO settings (id, key, value) VALUES
  (gen_random_uuid()::text, 'notification_whatsapp_number', '+237677129600'),
  (gen_random_uuid()::text, 'notification_email', 'admin@djamaairlogistics.com'),
  (gen_random_uuid()::text, 'company_name', 'Djama Air Logistics'),
  (gen_random_uuid()::text, 'delivery_delay_aerien', '5 a 7 jours'),
  (gen_random_uuid()::text, 'sla_response_minutes', '15'),
  (gen_random_uuid()::text, 'bot_enabled', 'true');

-- Pricing grids
-- Aerien Chine
INSERT INTO pricing_grids (id, mode, origin, rules, currency, valid_from, created_at, updated_at) VALUES (
  gen_random_uuid()::text, 'aerien_chine', 'chine',
  '[{"min_weight": 0, "max_weight": 25, "price_per_kg": 10000}, {"min_weight": 25, "max_weight": 100, "price_per_kg": 7500}, {"min_weight": 100, "max_weight": 999999, "price_per_kg": 6000}]'::jsonb,
  'FCFA', NOW(), NOW(), NOW()
);

-- Aerien International
INSERT INTO pricing_grids (id, mode, origin, rules, currency, valid_from, created_at, updated_at) VALUES (
  gen_random_uuid()::text, 'aerien_international', 'international',
  '[{"min_weight": 0, "max_weight": 100, "price_per_kg": 10500}, {"min_weight": 100, "max_weight": 999999, "price_per_kg": 8000}]'::jsonb,
  'FCFA', NOW(), NOW(), NOW()
);

-- Maritime
INSERT INTO pricing_grids (id, mode, origin, rules, currency, valid_from, created_at, updated_at) VALUES (
  gen_random_uuid()::text, 'maritime', 'chine',
  '[{"min_weight": 0, "max_weight": 300, "price_per_cbm": 330000}, {"min_weight": 300, "max_weight": 500, "price_per_cbm": 350000}, {"min_weight": 500, "max_weight": 800, "price_per_cbm": 370000}, {"min_weight": 800, "max_weight": 1000, "price_per_cbm": 390000}, {"min_weight": 1000, "max_weight": 999999, "price_per_tonne": 400000}]'::jsonb,
  'FCFA', NOW(), NOW(), NOW()
);

-- DHL Express - France/Europe
INSERT INTO pricing_grids (id, mode, origin, rules, currency, valid_from, created_at, updated_at) VALUES (
  gen_random_uuid()::text, 'dhl_express', 'france_europe',
  '[{"min_weight": 0, "max_weight": 2, "price_fixed": 55000}, {"min_weight": 2, "max_weight": 5, "price_fixed": 85000}]'::jsonb,
  'FCFA', NOW(), NOW(), NOW()
);

-- DHL Express - USA/Canada
INSERT INTO pricing_grids (id, mode, origin, rules, currency, valid_from, created_at, updated_at) VALUES (
  gen_random_uuid()::text, 'dhl_express', 'usa_canada',
  '[{"min_weight": 0, "max_weight": 2, "price_fixed": 65000}, {"min_weight": 2, "max_weight": 5, "price_fixed": 95000}]'::jsonb,
  'FCFA', NOW(), NOW(), NOW()
);

-- Gros Volumes Export
INSERT INTO pricing_grids (id, mode, origin, rules, currency, valid_from, created_at, updated_at) VALUES (
  gen_random_uuid()::text, 'gros_volumes_export', 'cameroun',
  '[{"min_weight": 50, "max_weight": 100, "price_per_kg": 9000}, {"min_weight": 100, "max_weight": 250, "price_per_kg": 8500}, {"min_weight": 250, "max_weight": 500, "price_per_kg": 8300}]'::jsonb,
  'FCFA', NOW(), NOW(), NOW()
);

-- ============================================
-- DONE! Tables and seed data created.
-- Next: set your JWT_SECRET in Vercel env vars,
-- then re-create the admin with the correct password hash.
-- ============================================
