-- ============================================
-- Djama Air Logistics - Database Initialization
-- Run this after prisma migrate to seed initial data
-- ============================================

-- Insert default admin agent
-- Email: airdjama@gmail.com | Password: airdjama2026
-- Hash: SHA-256("change-me-in-pro" + "airdjama2026")
INSERT INTO agents (id, email, password_hash, full_name, role, is_active, created_at)
VALUES (
  gen_random_uuid(),
  'airdjama@gmail.com',
  'c08e33232ccd460aa5cf233eb545e8210108c9a1750a954818bdc217f2515719',
  'Abdelkarim',
  'ADMIN',
  true,
  NOW()
);

-- Insert default settings
INSERT INTO settings (id, key, value) VALUES
  (gen_random_uuid(), 'notification_whatsapp_number', '+237677129600'),
  (gen_random_uuid(), 'notification_email', 'admin@djamaairlogistics.com'),
  (gen_random_uuid(), 'company_name', 'Djama Air Logistics'),
  (gen_random_uuid(), 'delivery_delay_aerien', '5 à 7 jours'),
  (gen_random_uuid(), 'sla_response_minutes', '15'),
  (gen_random_uuid(), 'bot_enabled', 'true');

-- Insert default pricing grids
-- Aérien Chine
INSERT INTO pricing_grids (id, mode, origin, rules, currency, valid_from, created_at, updated_at)
VALUES (
  gen_random_uuid(),
  'aerien_chine',
  'chine',
  '[{"min_weight": 0, "max_weight": 25, "price_per_kg": 10000}, {"min_weight": 25, "max_weight": 100, "price_per_kg": 7500}, {"min_weight": 100, "max_weight": 999999, "price_per_kg": 6000}]'::jsonb,
  'FCFA',
  NOW(),
  NOW(),
  NOW()
);

-- Aérien International
INSERT INTO pricing_grids (id, mode, origin, rules, currency, valid_from, created_at, updated_at)
VALUES (
  gen_random_uuid(),
  'aerien_international',
  'international',
  '[{"min_weight": 0, "max_weight": 100, "price_per_kg": 10500}, {"min_weight": 100, "max_weight": 999999, "price_per_kg": 8000}]'::jsonb,
  'FCFA',
  NOW(),
  NOW(),
  NOW()
);

-- Maritime
INSERT INTO pricing_grids (id, mode, origin, rules, currency, valid_from, created_at, updated_at)
VALUES (
  gen_random_uuid(),
  'maritime',
  'chine',
  '[{"min_weight": 0, "max_weight": 300, "price_per_cbm": 330000}, {"min_weight": 300, "max_weight": 500, "price_per_cbm": 350000}, {"min_weight": 500, "max_weight": 800, "price_per_cbm": 370000}, {"min_weight": 800, "max_weight": 1000, "price_per_cbm": 390000}, {"min_weight": 1000, "max_weight": 999999, "price_per_tonne": 400000}]'::jsonb,
  'FCFA',
  NOW(),
  NOW(),
  NOW()
);

-- DHL Express
INSERT INTO pricing_grids (id, mode, origin, rules, currency, valid_from, created_at, updated_at)
VALUES (
  gen_random_uuid(),
  'dhl_express',
  'france_europe',
  '[{"min_weight": 0, "max_weight": 2, "price_fixed": 55000}, {"min_weight": 2, "max_weight": 5, "price_fixed": 85000}]'::jsonb,
  'FCFA',
  NOW(),
  NOW(),
  NOW()
);

INSERT INTO pricing_grids (id, mode, origin, rules, currency, valid_from, created_at, updated_at)
VALUES (
  gen_random_uuid(),
  'dhl_express',
  'usa_canada',
  '[{"min_weight": 0, "max_weight": 2, "price_fixed": 65000}, {"min_weight": 2, "max_weight": 5, "price_fixed": 95000}]'::jsonb,
  'FCFA',
  NOW(),
  NOW(),
  NOW()
);

-- Gros Volumes Export
INSERT INTO pricing_grids (id, mode, origin, rules, currency, valid_from, created_at, updated_at)
VALUES (
  gen_random_uuid(),
  'gros_volumes_export',
  'cameroun',
  '[{"min_weight": 50, "max_weight": 100, "price_per_kg": 9000}, {"min_weight": 100, "max_weight": 250, "price_per_kg": 8500}, {"min_weight": 250, "max_weight": 500, "price_per_kg": 8300}]'::jsonb,
  'FCFA',
  NOW(),
  NOW(),
  NOW()
);
