INSERT INTO public.users (username, password) VALUES
('anant', '1234'),
('aditya', '4567'),
('avin', '1010'),
('advaya', '1111');

INSERT INTO public.websites (user_id, url, name) VALUES
(1, 'https://www.amazon.in/?...', 'amazon'),
(2, 'https://www.amazon.in/?...', 'amazon'),
(1, 'https://www.youtube.com/', 'youtube'),
(4, 'https://www.youtube.com/', 'youtube');
