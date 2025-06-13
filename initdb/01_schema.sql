-- Create users table and sequence
CREATE SEQUENCE IF NOT EXISTS public.users_id_seq;

CREATE TABLE IF NOT EXISTS public.users (
    id integer PRIMARY KEY DEFAULT nextval('public.users_id_seq'),
    username VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL
);

-- Ensure the sequence is in sync with existing user IDs
SELECT setval('public.users_id_seq', COALESCE((SELECT MAX(id) FROM public.users), 1), true);

-- Create websites table and sequence
CREATE SEQUENCE IF NOT EXISTS public.websites_id_seq;

CREATE TABLE IF NOT EXISTS public.websites (
    id integer PRIMARY KEY DEFAULT nextval('public.websites_id_seq'),
    user_id integer REFERENCES public.users(id),
    url TEXT NOT NULL,
    name TEXT
);

-- Ensure the sequence is in sync with existing website IDs
SELECT setval('public.websites_id_seq', COALESCE((SELECT MAX(id) FROM public.websites), 1), true);

-- Grant permissions
GRANT ALL ON TABLE public.users TO flask_user;
GRANT ALL ON SEQUENCE public.users_id_seq TO flask_user;
GRANT ALL ON TABLE public.websites TO flask_user;
GRANT ALL ON SEQUENCE public.websites_id_seq TO flask_user;
