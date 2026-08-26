-- Merchant Categories: Supabase table, seed data, FK on merchants, initial migration, RLS
-- Run this in the Supabase SQL Editor (Dashboard > SQL Editor > New query)
--
-- After running this SQL, run scripts/migrate_merchant_categories.py to classify
-- the ~1,326 merchants with NULL merchant_type via LLM batch classification.

-- ── Categories table ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.merchant_categories (
    id           SERIAL PRIMARY KEY,
    slug         TEXT UNIQUE NOT NULL,
    name         TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description  TEXT,
    icon         TEXT,
    sort_order   INT DEFAULT 0,
    is_active    BOOLEAN DEFAULT TRUE,
    created_at   TIMESTAMPTZ DEFAULT now(),
    updated_at   TIMESTAMPTZ DEFAULT now()
);

-- ── Seed 15 categories ───────────────────────────────────────────────────────

INSERT INTO public.merchant_categories (slug, name, display_name, description, icon, sort_order) VALUES
    ('grocery',              'Grocery',              'Grocery Stores',              'Supermarkets, grocery chains, and food stores',                  'ShoppingBasket',    1),
    ('pharmacy',             'Pharmacy',             'Pharmacies',                  'Pharmacies, drugstores, and health retailers',                   'Pill',              2),
    ('restaurant',           'Restaurant',           'Restaurants & Dining',        'Restaurants, fast food, cafes, bars, and dining establishments', 'UtensilsCrossed',   3),
    ('retail',               'Retail',               'Retail Stores',               'General retail, specialty shops, clothing, and department stores','ShoppingBag',       4),
    ('home-improvement',     'Home Improvement',     'Home Improvement & Hardware', 'Home improvement stores, hardware, lumber, and flooring',       'Hammer',            5),
    ('auto',                 'Auto',                 'Auto & Vehicles',             'Auto parts, repair, tires, oil change, and vehicle services',   'Car',               6),
    ('pets',                 'Pets',                 'Pet Stores',                  'Pet supply stores, pet food, grooming, and veterinary',          'PawPrint',          7),
    ('entertainment',        'Entertainment',        'Entertainment & Leisure',     'Movie theaters, museums, amusement parks, and recreation',      'Ticket',            8),
    ('telecom',              'Telecom',              'Phones & Internet',           'Cell phone plans, internet providers, and telecom services',    'Smartphone',        9),
    ('transportation',       'Transportation',       'Transportation',              'Public transit, ride services, and transportation providers',   'Bus',              10),
    ('hotels-lodging',       'Hotels & Lodging',     'Hotels & Lodging',            'Hotels, motels, inns, and lodging providers',                  'BedDouble',        11),
    ('airlines',             'Airlines',             'Airlines',                    'Airlines and air travel providers',                             'Plane',            12),
    ('cruises-travel',       'Cruises & Travel',     'Cruises & Travel',            'Cruise lines, travel agencies, and vacation packages',         'Ship',             13),
    ('thrift-secondhand',    'Thrift & Secondhand',  'Thrift & Secondhand',         'Thrift stores, consignment shops, and secondhand retailers',   'Recycle',          14),
    ('beauty-personal-care', 'Beauty & Personal Care', 'Beauty & Personal Care',    'Barber shops, salons, beauty supply, and personal care',       'Scissors',         15)
ON CONFLICT (slug) DO NOTHING;

-- ── Add category_id FK on merchants ──────────────────────────────────────────

ALTER TABLE public.merchants
    ADD COLUMN IF NOT EXISTS category_id INT REFERENCES public.merchant_categories(id);

CREATE INDEX IF NOT EXISTS idx_merchants_category_id ON public.merchants(category_id);

-- ── Updated_at trigger ───────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER merchant_categories_updated_at
    BEFORE UPDATE ON public.merchant_categories
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ── Migrate existing merchant_type values ────────────────────────────────────
-- Maps the 473 merchants with non-NULL merchant_type to their category_id.
-- The ~1,326 NULL merchants will be classified by migrate_merchant_categories.py.

-- Grocery (9 merchants)
UPDATE public.merchants SET category_id = (
    SELECT id FROM public.merchant_categories WHERE slug = 'grocery'
) WHERE merchant_type = 'Grocery';

-- Pharmacy (4 merchants: "Pharmacy" + "pharmacy")
UPDATE public.merchants SET category_id = (
    SELECT id FROM public.merchant_categories WHERE slug = 'pharmacy'
) WHERE LOWER(merchant_type) = 'pharmacy';

-- Restaurant (200 merchants: "Bars and Restaurants" + "restaurant")
UPDATE public.merchants SET category_id = (
    SELECT id FROM public.merchant_categories WHERE slug = 'restaurant'
) WHERE merchant_type IN ('Bars and Restaurants', 'restaurant');

-- Retail (59 merchants: "Specialty Retail" + "retail")
UPDATE public.merchants SET category_id = (
    SELECT id FROM public.merchant_categories WHERE slug = 'retail'
) WHERE merchant_type IN ('Specialty Retail', 'retail');

-- Home Improvement & Hardware (2 merchants)
UPDATE public.merchants SET category_id = (
    SELECT id FROM public.merchant_categories WHERE slug = 'home-improvement'
) WHERE merchant_type IN ('Home Improvement', 'Hardware');

-- Auto (37 merchants)
UPDATE public.merchants SET category_id = (
    SELECT id FROM public.merchant_categories WHERE slug = 'auto'
) WHERE merchant_type = 'Auto';

-- Pets (32 merchants)
UPDATE public.merchants SET category_id = (
    SELECT id FROM public.merchant_categories WHERE slug = 'pets'
) WHERE merchant_type = 'Pets';

-- Entertainment (27 merchants)
UPDATE public.merchants SET category_id = (
    SELECT id FROM public.merchant_categories WHERE slug = 'entertainment'
) WHERE merchant_type = 'Movies, Museums and Entertainment';

-- Telecom (1 merchant)
UPDATE public.merchants SET category_id = (
    SELECT id FROM public.merchant_categories WHERE slug = 'telecom'
) WHERE merchant_type = 'Cell Phone Plans';

-- Transportation (1 merchant)
UPDATE public.merchants SET category_id = (
    SELECT id FROM public.merchant_categories WHERE slug = 'transportation'
) WHERE merchant_type = 'Transportation';

-- Beauty & Personal Care (101 merchants)
UPDATE public.merchants SET category_id = (
    SELECT id FROM public.merchant_categories WHERE slug = 'beauty-personal-care'
) WHERE merchant_type = 'Personal Care';

-- ── Row Level Security ───────────────────────────────────────────────────────

ALTER TABLE public.merchant_categories ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all_merchant_categories" ON public.merchant_categories
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "anon_read_merchant_categories" ON public.merchant_categories
    FOR SELECT USING (true);

-- ── Verification query (run after to confirm) ────────────────────────────────
-- SELECT mc.slug, mc.display_name, COUNT(m.id) AS merchant_count
-- FROM public.merchant_categories mc
-- LEFT JOIN public.merchants m ON m.category_id = mc.id
-- GROUP BY mc.slug, mc.display_name, mc.sort_order
-- ORDER BY mc.sort_order;
