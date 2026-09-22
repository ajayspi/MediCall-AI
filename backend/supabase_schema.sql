-- TalkByte AI — Supabase Schema
-- Run this in Supabase SQL Editor

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Core tables

-- Restaurants
CREATE TABLE restaurants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    telnyx_number TEXT,
    address TEXT,
    closing_time TIME DEFAULT '22:00',
    ai_instructions TEXT DEFAULT '',
    active BOOLEAN DEFAULT true,
    plan TEXT DEFAULT 'starter',
    pos_provider TEXT DEFAULT 'square',
    pos_config JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Restaurant users (multi-tenant)
CREATE TABLE restaurant_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID REFERENCES restaurants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT DEFAULT 'staff', -- owner, staff, readonly
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(restaurant_id, user_id)
);

-- Menu items with pgvector for RAG
CREATE TABLE menu_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID REFERENCES restaurants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    price_cents INTEGER NOT NULL,
    category TEXT,
    available BOOLEAN DEFAULT true,
    embedding VECTOR(1536), -- pgvector for RAG
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Calls
CREATE TABLE calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID REFERENCES restaurants(id) ON DELETE CASCADE,
    caller_number TEXT NOT NULL,
    state TEXT DEFAULT 'GREETING',
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    transcript JSONB DEFAULT '[]',
    stt_confidence REAL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Orders
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id UUID REFERENCES calls(id) ON DELETE SET NULL,
    restaurant_id UUID REFERENCES restaurants(id) ON DELETE CASCADE,
    items JSONB NOT NULL DEFAULT '[]',
    total_cents INTEGER NOT NULL,
    state TEXT DEFAULT 'PLACED', -- PLACED, LINK_SENT, PAID, SYNCED, FAILED
    pos_order_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    paid_at TIMESTAMPTZ
);

-- Payment events
CREATE TABLE payment_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID REFERENCES orders(id) ON DELETE CASCADE,
    stripe_payment_link TEXT,
    stripe_session_id TEXT,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    paid_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ
);

-- Plans
CREATE TABLE plans (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    monthly_cents INTEGER NOT NULL,
    call_limit INTEGER
);

INSERT INTO plans (id, name, monthly_cents, call_limit) VALUES
    ('starter', 'Starter', 14900, 1000),
    ('growth', 'Growth', 19900, 5000),
    ('enterprise', 'Enterprise', 29900, NULL);

-- Subscriptions
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID REFERENCES restaurants(id) ON DELETE CASCADE,
    plan_id TEXT REFERENCES plans(id),
    stripe_subscription_id TEXT,
    status TEXT DEFAULT 'active',
    current_period_end TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_calls_restaurant ON calls(restaurant_id);
CREATE INDEX idx_calls_state ON calls(state);
CREATE INDEX idx_orders_restaurant ON orders(restaurant_id);
CREATE INDEX idx_orders_state ON orders(state);
CREATE INDEX idx_menu_items_restaurant ON menu_items(restaurant_id);
CREATE INDEX idx_menu_items_available ON menu_items(available);
CREATE INDEX idx_restaurant_users_user ON restaurant_users(user_id);

-- pgvector similarity search function
CREATE OR REPLACE FUNCTION search_menu_items(
    restaurant_uuid UUID,
    query_embedding VECTOR(1536),
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    name TEXT,
    description TEXT,
    price_cents INTEGER,
    category TEXT,
    similarity REAL
) LANGUAGE sql AS $$
    SELECT
        mi.id,
        mi.name,
        mi.description,
        mi.price_cents,
        mi.category,
        1 - (mi.embedding <=> query_embedding) AS similarity
    FROM menu_items mi
    WHERE mi.restaurant_id = restaurant_uuid
      AND mi.available = true
      AND mi.embedding IS NOT NULL
    ORDER BY mi.embedding <=> query_embedding
    LIMIT match_count;
$$;

-- Updated at trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER update_restaurants_updated_at BEFORE UPDATE ON restaurants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_menu_items_updated_at BEFORE UPDATE ON menu_items
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_calls_updated_at BEFORE UPDATE ON calls
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_orders_updated_at BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_subscriptions_updated_at BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- RLS Policies
ALTER TABLE restaurants ENABLE ROW LEVEL SECURITY;
ALTER TABLE restaurant_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE menu_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

-- Restaurant owners see their own restaurant
CREATE POLICY restaurant_own_data ON restaurants
    FOR ALL USING (
        id IN (
            SELECT restaurant_id FROM restaurant_users 
            WHERE user_id = auth.uid() AND role = 'owner'
        )
    );

-- Staff can read restaurant
CREATE POLICY restaurant_staff_read ON restaurants
    FOR SELECT USING (
        id IN (
            SELECT restaurant_id FROM restaurant_users 
            WHERE user_id = auth.uid()
        )
    );

-- Menu items: restaurant staff can manage
CREATE POLICY menu_items_manage ON menu_items
    FOR ALL USING (
        restaurant_id IN (
            SELECT restaurant_id FROM restaurant_users 
            WHERE user_id = auth.uid()
        )
    );

-- Calls: restaurant staff can read
CREATE POLICY calls_read ON calls
    FOR SELECT USING (
        restaurant_id IN (
            SELECT restaurant_id FROM restaurant_users 
            WHERE user_id = auth.uid()
        )
    );

-- Orders: restaurant staff can manage
CREATE POLICY orders_manage ON orders
    FOR ALL USING (
        restaurant_id IN (
            SELECT restaurant_id FROM restaurant_users 
            WHERE user_id = auth.uid()
        )
    );

-- Payment events: restaurant staff can read
CREATE POLICY payment_events_read ON payment_events
    FOR SELECT USING (
        order_id IN (
            SELECT id FROM orders WHERE restaurant_id IN (
                SELECT restaurant_id FROM restaurant_users 
                WHERE user_id = auth.uid()
            )
        )
    );

-- Subscriptions: restaurant owners can manage
CREATE POLICY subscriptions_manage ON subscriptions
    FOR ALL USING (
        restaurant_id IN (
            SELECT restaurant_id FROM restaurant_users 
            WHERE user_id = auth.uid() AND role = 'owner'
        )
    );