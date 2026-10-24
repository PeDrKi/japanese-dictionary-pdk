-- ════════════════════════════════════════════════════════════════════════════
-- 日本語 Web — schema Supabase (Postgres) · phiên bản 8 (xung đột nhiều thiết bị + từ loại + vai trò + ngữ pháp + kiểm tra dữ liệu ở server)
-- Chạy: Supabase Dashboard → SQL Editor → New query → dán TOÀN BỘ → Run
-- Dùng được cho cả cài mới LẪN nâng cấp từ bản đầu (an toàn khi chạy lại nhiều lần).
-- Cấu trúc bám sát japanese.db của bản desktop (8 bảng, khoá chính UUID),
-- thêm cột user_id + Row Level Security để mỗi tài khoản chỉ thấy dữ liệu của mình.
--
-- Phần xử lý xung đột (nhiều thiết bị cùng sửa):
--   • cards / decks / radicals có cột `version` do SERVER tăng sau mỗi lần sửa.
--     App gửi "chỉ sửa nếu version vẫn là N" → phát hiện được ai đó vừa sửa trước.
--   • updated_at do SERVER đặt ở mọi lần ghi (không tin đồng hồ điện thoại).
--   • log_study(): ghi 1 lượt ôn + cập nhật lịch SRS NGUYÊN TỬ trên server, nên 2 thiết
--     bị cùng ôn 1 thẻ không ghi đè lên nhau; gửi lại cùng 1 lượt ôn (mất mạng rồi gửi
--     lại) không bị tính 2 lần; lượt ôn cũ hơn lượt gần nhất không phá lịch mới; giờ ôn ở tương lai (đồng hồ máy nhanh) bị chặn bằng giờ server.
-- ════════════════════════════════════════════════════════════════════════════

-- ── Danh mục bộ thẻ ─────────────────────────────────────────────────────────
create table if not exists public.deck_categories (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name        text not null,
  icon        text default '🗂️',
  sort_order  integer not null default 0,
  created_at  timestamptz not null default now(),
  unique (user_id, name)
);

-- ── Bộ thẻ ──────────────────────────────────────────────────────────────────
create table if not exists public.decks (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name         text not null,
  description  text,
  color        text default '#4A90D9',
  icon         text default '📁',
  category_id  uuid references public.deck_categories(id) on delete set null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  deleted_at   timestamptz
);
create unique index if not exists decks_user_name_alive
  on public.decks (user_id, name) where deleted_at is null;

-- ── Thẻ ─────────────────────────────────────────────────────────────────────
create table if not exists public.cards (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null default auth.uid() references auth.users(id) on delete cascade,
  type            text not null check (type in ('kanji','hiragana','katakana','vocab')),
  character       text not null,
  reading_on      text,
  reading_kun     text,
  reading_kana    text,
  reading_hanviet text,
  romaji          text,
  meaning_vi      text not null,
  meaning_en      text,
  example_jp      text,
  example_vi      text,
  stroke_count    integer,
  jlpt_level      text,
  status          text not null default 'new' check (status in ('new','learning','known')),
  is_favorite     boolean not null default false,
  source          text,
  notes           text,
  srs_interval    integer not null default 1,
  srs_ease        double precision not null default 2.5,
  srs_due_date    date,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  deleted_at      timestamptz
);
create index if not exists cards_user_created on public.cards (user_id, created_at desc);
create index if not exists cards_user_due     on public.cards (user_id, srs_due_date) where deleted_at is null;

-- ── Thẻ ↔ Bộ thẻ ────────────────────────────────────────────────────────────
create table if not exists public.deck_cards (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users(id) on delete cascade,
  deck_id     uuid not null references public.decks(id)  on delete cascade,
  card_id     uuid not null references public.cards(id)  on delete cascade,
  added_at    timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  deleted_at  timestamptz,
  unique (deck_id, card_id)
);
create index if not exists deck_cards_user on public.deck_cards (user_id);

-- ── Bộ thủ ──────────────────────────────────────────────────────────────────
create table if not exists public.radicals (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users(id) on delete cascade,
  character   text not null,
  name        text,
  color       text default '#4A90D9',
  sort_order  integer not null default 0,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  deleted_at  timestamptz
);
create unique index if not exists radicals_user_char_alive
  on public.radicals (user_id, character) where deleted_at is null;

create table if not exists public.radical_cards (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users(id) on delete cascade,
  radical_id  uuid not null references public.radicals(id) on delete cascade,
  card_id     uuid not null references public.cards(id)   on delete cascade,
  added_at    timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  deleted_at  timestamptz,
  unique (radical_id, card_id)
);
create index if not exists radical_cards_user on public.radical_cards (user_id);

-- ── Tách bộ do người dùng tự định nghĩa ─────────────────────────────────────
create table if not exists public.user_decompositions (
  user_id     uuid not null default auth.uid() references auth.users(id) on delete cascade,
  character   text not null,
  parts       text not null,
  updated_at  timestamptz not null default now(),
  deleted_at  timestamptz,
  primary key (user_id, character)
);

-- ── Lịch sử ôn tập ──────────────────────────────────────────────────────────
create table if not exists public.study_sessions (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users(id) on delete cascade,
  card_id     uuid not null references public.cards(id) on delete cascade,
  result      text not null check (result in ('correct','incorrect')),
  studied_at  timestamptz not null default now()
);
create index if not exists study_user_time on public.study_sessions (user_id, studied_at desc);
create index if not exists study_card_time on public.study_sessions (card_id, studied_at desc);

-- ── Ngữ pháp (v7) ──────────────────────────────────────────────────────────
create table if not exists public.grammar_points (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null default auth.uid() references auth.users(id) on delete cascade,
  title        text not null check (length(title) between 1 and 200),   -- mẫu câu, vd 〜てから
  meaning_vi   text not null default '',
  structure    text,                                                      -- cấu tạo, vd V-て + から
  explanation  text,                                                      -- giải thích / cách dùng / lưu ý
  examples     text,                                                      -- mỗi dòng: câu tiếng Nhật | nghĩa tiếng Việt
  jlpt_level   text check (jlpt_level is null or jlpt_level in ('N5','N4','N3','N2','N1')),
  version      bigint not null default 1,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index if not exists grammar_user on public.grammar_points (user_id);

-- ════════════ PHIÊN BẢN 2: XỬ LÝ XUNG ĐỘT ════════════════════════════════════

-- Số phiên bản của từng hàng (server tăng sau mỗi lần sửa)
alter table public.cards    add column if not exists version bigint not null default 1;
alter table public.decks    add column if not exists version bigint not null default 1;
alter table public.radicals add column if not exists version bigint not null default 1;

-- Bản đầu dùng kiểu real (float4); đổi sang double precision để phép tính SRS giống hệt
-- bản desktop (Python dùng double). Làm tròn về 1 chữ số thập phân vì ease luôn là bội của 0.1.
do $$
begin
  if exists (select 1 from information_schema.columns
             where table_schema = 'public' and table_name = 'cards'
               and column_name = 'srs_ease' and data_type = 'real') then
    alter table public.cards alter column srs_ease type double precision
      using round(srs_ease::numeric, 1)::double precision;
  end if;
end $$;

-- Trigger cho bảng có version: ép version=1 khi tạo, +1 khi sửa; updated_at do server đặt
create or replace function public.touch_versioned() returns trigger
language plpgsql as $$
begin
  if tg_op = 'INSERT' then
    new.version := 1;
  else
    new.version := old.version + 1;
  end if;
  new.updated_at := clock_timestamp();
  return new;
end $$;

-- Trigger cho bảng không có version: chỉ đặt updated_at do server
create or replace function public.touch_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := clock_timestamp();
  return new;
end $$;

do $$
declare t text;
begin
  foreach t in array array['cards','decks','radicals','grammar_points']
  loop
    execute format('drop trigger if exists trg_touch on public.%I', t);
    execute format('create trigger trg_touch before insert or update on public.%I
                    for each row execute function public.touch_versioned()', t);
  end loop;
  foreach t in array array['deck_cards','radical_cards','user_decompositions']
  loop
    execute format('drop trigger if exists trg_touch on public.%I', t);
    execute format('create trigger trg_touch before insert or update on public.%I
                    for each row execute function public.touch_updated_at()', t);
  end loop;
end $$;

-- ══ PHIÊN BẢN 6: VAI TRÒ (user / admin) ═════════════════════════════════════════════════════════
--  • Mọi quyền được kiểm tra Ở SERVER (RLS + hàm security definer), giao diện chỉ ẩn/hiện nút.
--  • user : chỉ thấy và sửa dữ liệu CỦA MÌNH. Không tự đổi được vai trò / trạng thái của mình.
--  • admin: xem danh sách tài khoản + số liệu tổng (KHÔNG đọc được nội dung thẻ riêng của ai),
--           khóa/mở khóa, đổi vai trò, xóa tài khoản, quản lý "bộ thẻ mẫu" dùng chung.
--  • Tài khoản bị khóa: mọi truy vấn dữ liệu bị từ chối (RLS), đăng nhập vẫn được nhưng app báo bị khóa.
--  • Cấp quyền admin ĐẦU TIÊN: chạy trong SQL Editor (xem README):
--      update public.profiles set role = 'admin' where user_id = (select id from auth.users where email = 'ban@example.com');
create table if not exists public.profiles (
  user_id     uuid primary key references auth.users(id) on delete cascade,
  role        text not null default 'user' check (role in ('user', 'admin')),
  status      text not null default 'active' check (status in ('active', 'blocked')),
  created_at  timestamptz not null default now()
);
alter table public.profiles enable row level security;
drop policy if exists "read own profile" on public.profiles;
create policy "read own profile" on public.profiles for select to authenticated using (user_id = auth.uid());
-- Cố ý KHÔNG có policy insert/update/delete: người dùng không thể tự nâng quyền; mọi thay đổi đi qua hàm bên dưới.

insert into public.profiles (user_id) select id from auth.users on conflict do nothing;   -- tài khoản đã có từ trước = user

create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (user_id) values (new.id) on conflict do nothing;
  return new;
end $$;
drop trigger if exists trg_new_user on auth.users;
create trigger trg_new_user after insert on auth.users for each row execute function public.handle_new_user();

create or replace function public.jp_is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from profiles where user_id = auth.uid() and role = 'admin' and status = 'active') $$;

create or replace function public.jp_is_active() returns boolean
language sql stable security definer set search_path = public as $$
  select not exists (select 1 from profiles where user_id = auth.uid() and status = 'blocked') $$;

-- Thông tin vai trò của chính mình (tự tạo hồ sơ nếu thiếu, vd tài khoản tạo trước khi có trigger)
create or replace function public.jp_me() returns table (role text, status text)
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null then raise exception 'Chưa đăng nhập'; end if;
  insert into profiles (user_id) values (auth.uid()) on conflict do nothing;
  return query select p.role, p.status from profiles p where p.user_id = auth.uid();
end $$;

create or replace function public.admin_list_users() returns table (
  user_id uuid, email text, role text, status text, created_at timestamptz, last_sign_in_at timestamptz,
  cards bigint, decks bigint, last_study timestamptz)
language plpgsql stable security definer set search_path = public as $$
begin
  if not jp_is_admin() then raise exception 'Không có quyền quản trị'; end if;
  return query
    select u.id, u.email::text, coalesce(p.role, 'user'), coalesce(p.status, 'active'), u.created_at, u.last_sign_in_at,
           (select count(*) from cards c where c.user_id = u.id and c.deleted_at is null),
           (select count(*) from decks d where d.user_id = u.id and d.deleted_at is null),
           (select max(s.studied_at) from study_sessions s where s.user_id = u.id)
    from auth.users u left join profiles p on p.user_id = u.id
    order by u.created_at desc;
end $$;

create or replace function public.admin_stats() returns json
language plpgsql stable security definer set search_path = public as $$
begin
  if not jp_is_admin() then raise exception 'Không có quyền quản trị'; end if;
  return json_build_object(
    'users',      (select count(*) from auth.users),
    'admins',     (select count(*) from profiles where role = 'admin'),
    'blocked',    (select count(*) from profiles where status = 'blocked'),
    'active_7d',  (select count(distinct user_id) from study_sessions where studied_at > now() - interval '7 days'),
    'cards',      (select count(*) from cards where deleted_at is null),
    'sessions',   (select count(*) from study_sessions),
    'starters',   (select count(*) from starter_decks));
end $$;

create or replace function public.admin_set_role(p_user uuid, p_role text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not jp_is_admin() then raise exception 'Không có quyền quản trị'; end if;
  if p_role not in ('user', 'admin') then raise exception 'Vai trò không hợp lệ'; end if;
  if p_user = auth.uid() and p_role <> 'admin' then raise exception 'Không thể tự hạ quyền của chính mình'; end if;
  insert into profiles (user_id, role) values (p_user, p_role) on conflict (user_id) do update set role = excluded.role;
end $$;

create or replace function public.admin_set_status(p_user uuid, p_status text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not jp_is_admin() then raise exception 'Không có quyền quản trị'; end if;
  if p_status not in ('active', 'blocked') then raise exception 'Trạng thái không hợp lệ'; end if;
  if p_user = auth.uid() then raise exception 'Không thể tự khóa tài khoản của chính mình'; end if;
  insert into profiles (user_id, status) values (p_user, p_status) on conflict (user_id) do update set status = excluded.status;
end $$;

create or replace function public.admin_delete_user(p_user uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not jp_is_admin() then raise exception 'Không có quyền quản trị'; end if;
  if p_user = auth.uid() then raise exception 'Không thể tự xóa tài khoản của chính mình ở đây'; end if;
  delete from auth.users where id = p_user;      -- toàn bộ dữ liệu của họ tự xóa theo (on delete cascade)
end $$;

-- Tự xóa tài khoản của mình (quyền của mọi người dùng, cần cho việc đáp ứng yêu cầu xóa dữ liệu)
create or replace function public.delete_my_account() returns void
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null then raise exception 'Chưa đăng nhập'; end if;
  if (select role from profiles where user_id = auth.uid()) = 'admin'
     and (select count(*) from profiles where role = 'admin' and status = 'active') <= 1 then
    raise exception 'Bạn là quản trị viên duy nhất — hãy cấp quyền admin cho người khác trước khi xóa tài khoản';
  end if;
  delete from auth.users where id = auth.uid();
end $$;

-- ── Bộ thẻ mẫu (nội dung dùng chung do admin quản lý, ai cũng thêm được vào thẻ của mình) ──
create table if not exists public.starter_decks (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  description text,
  icon        text default '📘',
  color       text default '#4A90D9',
  level       text,
  published   boolean not null default true,
  created_by  uuid references auth.users(id) on delete set null default auth.uid(),
  created_at  timestamptz not null default now()
);
create table if not exists public.starter_cards (
  id              uuid primary key default gen_random_uuid(),
  deck_id         uuid not null references public.starter_decks(id) on delete cascade,
  type            text not null check (type in ('kanji','hiragana','katakana','vocab')),
  character       text not null,
  reading_on      text, reading_kun text, reading_kana text, reading_hanviet text, romaji text,
  meaning_vi      text not null,
  meaning_en      text, example_jp text, example_vi text,
  stroke_count    integer, jlpt_level text, pos text,
  sort_order      integer not null default 0
);
create index if not exists starter_cards_deck on public.starter_cards (deck_id);
alter table public.starter_decks enable row level security;
alter table public.starter_cards enable row level security;
drop policy if exists "read starters" on public.starter_decks;
drop policy if exists "read starter cards" on public.starter_cards;
create policy "read starters" on public.starter_decks for select to authenticated
  using (jp_is_active() and (published or jp_is_admin()));
create policy "read starter cards" on public.starter_cards for select to authenticated
  using (jp_is_active() and exists (select 1 from starter_decks d where d.id = deck_id and (d.published or jp_is_admin())));
-- Ghi: chỉ qua hàm admin_* bên dưới (không có policy ghi)

-- Admin đăng 1 bộ thẻ CỦA MÌNH làm bộ mẫu (chụp lại nội dung tại thời điểm đăng). Đăng lại = thay nội dung cũ.
create or replace function public.admin_publish_deck(p_deck uuid, p_name text default null, p_level text default null,
                                                      p_replace uuid default null) returns uuid
language plpgsql security definer set search_path = public as $$
declare d decks; sid uuid;
begin
  if not jp_is_admin() then raise exception 'Không có quyền quản trị'; end if;
  select * into d from decks where id = p_deck and user_id = auth.uid() and deleted_at is null;
  if not found then raise exception 'Không tìm thấy bộ thẻ của bạn'; end if;
  if p_replace is not null then
    update starter_decks set name = coalesce(nullif(p_name, ''), d.name), description = d.description, icon = d.icon,
           color = d.color, level = coalesce(p_level, level) where id = p_replace returning id into sid;
    if sid is null then raise exception 'Bộ mẫu cần thay không tồn tại'; end if;
    delete from starter_cards where deck_id = sid;
  else
    insert into starter_decks (name, description, icon, color, level)
    values (coalesce(nullif(p_name, ''), d.name), d.description, d.icon, d.color, p_level) returning id into sid;
  end if;
  insert into starter_cards (deck_id, type, character, reading_on, reading_kun, reading_kana, reading_hanviet, romaji,
                             meaning_vi, meaning_en, example_jp, example_vi, stroke_count, jlpt_level, pos, sort_order)
  select sid, c.type, c.character, c.reading_on, c.reading_kun, c.reading_kana, c.reading_hanviet, c.romaji,
         c.meaning_vi, c.meaning_en, c.example_jp, c.example_vi, c.stroke_count, c.jlpt_level, c.pos,
         row_number() over (order by dc.added_at, c.created_at)
  from deck_cards dc join cards c on c.id = dc.card_id
  where dc.deck_id = p_deck and dc.deleted_at is null and c.deleted_at is null and c.user_id = auth.uid();
  return sid;
end $$;

create or replace function public.admin_set_starter(p_id uuid, p_published boolean) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not jp_is_admin() then raise exception 'Không có quyền quản trị'; end if;
  update starter_decks set published = p_published where id = p_id;
end $$;

create or replace function public.admin_delete_starter(p_id uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not jp_is_admin() then raise exception 'Không có quyền quản trị'; end if;
  delete from starter_decks where id = p_id;
end $$;

-- Người dùng thêm 1 bộ mẫu vào thẻ của mình: tạo bộ thẻ mới, thẻ đã có (cùng loại + chữ) thì dùng lại thay vì nhân đôi.
create or replace function public.import_starter_deck(p_starter uuid) returns json
language plpgsql security definer set search_path = public as $$
declare s starter_decks; me uuid := auth.uid(); did uuid := gen_random_uuid(); nm text; k int := 1;
        r starter_cards; cid uuid; added int := 0; linked int := 0;
begin
  if me is null then raise exception 'Chưa đăng nhập'; end if;
  if not jp_is_active() then raise exception 'Tài khoản đang bị khóa'; end if;
  select * into s from starter_decks where id = p_starter and (published or jp_is_admin());
  if not found then raise exception 'Không tìm thấy bộ thẻ mẫu'; end if;
  nm := s.name;
  while exists (select 1 from decks where user_id = me and name = nm and deleted_at is null) loop
    k := k + 1; nm := s.name || ' (' || k || ')';
  end loop;
  insert into decks (id, user_id, name, description, icon, color) values (did, me, nm, s.description, s.icon, s.color);
  for r in select * from starter_cards where deck_id = p_starter order by sort_order loop
    select id into cid from cards where user_id = me and type = r.type and character = r.character and deleted_at is null limit 1;
    if cid is null then
      insert into cards (user_id, type, character, reading_on, reading_kun, reading_kana, reading_hanviet, romaji,
                         meaning_vi, meaning_en, example_jp, example_vi, stroke_count, jlpt_level, pos)
      values (me, r.type, r.character, r.reading_on, r.reading_kun, r.reading_kana, r.reading_hanviet, r.romaji,
              r.meaning_vi, r.meaning_en, r.example_jp, r.example_vi, r.stroke_count, r.jlpt_level, r.pos) returning id into cid;
      added := added + 1;
    else linked := linked + 1; end if;
    insert into deck_cards (user_id, deck_id, card_id) values (me, did, cid) on conflict do nothing;
  end loop;
  return json_build_object('deck_id', did, 'name', nm, 'added', added, 'linked', linked);
end $$;

revoke execute on function public.admin_list_users(), public.admin_stats(), public.admin_set_role(uuid, text),
  public.admin_set_status(uuid, text), public.admin_delete_user(uuid), public.admin_publish_deck(uuid, text, text, uuid),
  public.admin_set_starter(uuid, boolean), public.admin_delete_starter(uuid), public.import_starter_deck(uuid),
  public.delete_my_account(), public.jp_me() from public, anon;
grant execute on function public.admin_list_users(), public.admin_stats(), public.admin_set_role(uuid, text),
  public.admin_set_status(uuid, text), public.admin_delete_user(uuid), public.admin_publish_deck(uuid, text, text, uuid),
  public.admin_set_starter(uuid, boolean), public.admin_delete_starter(uuid), public.import_starter_deck(uuid),
  public.delete_my_account(), public.jp_me(), public.jp_is_admin(), public.jp_is_active() to authenticated;

-- ── Row Level Security ──────────────────────────────────────────────────────
do $$
declare t text;
begin
  foreach t in array array['deck_categories','decks','cards','deck_cards','radicals',
                           'radical_cards','user_decompositions','study_sessions','grammar_points']
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists "own rows" on public.%I', t);
    execute format('create policy "own rows" on public.%I for all to authenticated
                    using (user_id = auth.uid() and public.jp_is_active())
                    with check (user_id = auth.uid() and public.jp_is_active())', t);
  end loop;
end $$;

-- ── PHIÊN BẢN 4-5: từ loại (danh từ, động từ [nhóm 1-3], tính từ い/な, đại từ, trợ từ, trạng từ, liên từ, thán từ) ──────
alter table public.cards add column if not exists pos text;
-- (v5: mở rộng danh sách từ loại → xoá ràng buộc cũ rồi tạo lại; chạy lại nhiều lần vẫn an toàn)
alter table public.cards drop constraint if exists cards_pos_check;
alter table public.cards add constraint cards_pos_check
  check (pos is null or pos in ('noun', 'verb', 'verb1', 'verb2', 'verb3', 'adj_i', 'adj_na',
                                'pronoun', 'particle', 'adverb', 'conjunction', 'interjection'));

-- ── Phiên bản schema (app kiểm tra khi khởi động để báo "chưa chạy schema mới") ──
create or replace function public.jp_schema_version() returns integer
language sql stable as $$ select 7 $$;

-- Chữ ký nhẹ của toàn bộ dữ liệu của bạn: app hỏi cái này mỗi ~60 giây thay vì tải lại tất cả.
-- Đổi khi có thêm / xóa / sửa bất kỳ hàng nào (chạy với quyền của người gọi nên RLS chỉ tính dữ liệu của bạn).
create or replace function public.jp_sync_sig() returns text
language sql stable set search_path = public as $$
  select md5(concat_ws('|',
    (select count(*)::text || coalesce(max(updated_at)::text, '') from cards),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from decks),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from radicals),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from deck_cards),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from radical_cards),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from user_decompositions),
    (select count(*)::text || coalesce(max(studied_at)::text, '') from study_sessions),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from grammar_points),
    (select coalesce(md5(string_agg(id::text || name || coalesce(icon, '') || sort_order::text, ',' order by id)), '') from deck_categories)
  )) $$;

-- ── Ghi 1 lượt ôn + cập nhật lịch SRS, nguyên tử trên server ────────────────
-- Thuật toán y hệt domain/srs.py của bản desktop (SM-2 rút gọn), dùng cùng kiểu số thực
-- double và cùng cách làm tròn (.5 về số chẵn) nên cho đúng kết quả của Python.
--   p_id     : UUID do thiết bị tạo cho lượt ôn này → gửi lại cùng id thì KHÔNG tính lần 2
--   p_at     : thời điểm ôn thật (khi ôn lúc offline, gửi muộn)
--   p_today  : ngày hiện tại theo giờ máy người dùng (server dùng UTC nên không tự biết)
-- Trả về hàng thẻ sau khi cập nhật (hoặc null nếu thẻ không còn).
create or replace function public.log_study(
  p_id uuid, p_card uuid, p_result text,
  p_at timestamptz default now(), p_today date default current_date
) returns public.cards
language plpgsql
set search_path = public
as $$
declare
  c public.cards;
  last_at timestamptz;
  iv int; ez double precision; ne double precision; ni int; ns text;
begin
  if p_result not in ('correct', 'incorrect') then
    raise exception 'p_result phải là correct hoặc incorrect';
  end if;

  if not public.jp_is_active() then raise exception 'Tài khoản đang bị khóa' using errcode = '42501'; end if;
  if p_at > now() then p_at := now(); end if;          -- đồng hồ máy chạy nhanh: không cho lượt ôn "ở tương lai" làm các lượt thật sau đó bị coi là cũ
  select * into c from public.cards where id = p_card for update;   -- khoá hàng: 2 thiết bị xếp hàng lần lượt
  if not found then return null; end if;

  select max(studied_at) into last_at from public.study_sessions where card_id = p_card;

  insert into public.study_sessions (id, card_id, result, studied_at)
  values (p_id, p_card, p_result, p_at)
  on conflict (id) do nothing;
  if not found then return c; end if;                  -- lượt này đã được ghi trước đó (gửi lại)

  if last_at is not null and p_at < last_at then       -- lượt ôn cũ hơn lượt gần nhất: giữ lịch mới
    return c;
  end if;

  iv := coalesce(nullif(c.srs_interval, 0), 1);
  ez := coalesce(nullif(c.srs_ease, 0), 2.5::double precision);

  if p_result = 'correct' then
    ne := least(ez + 0.1::double precision, 2.8::double precision);   -- ease tối đa 2.8
    ni := least(greatest(iv + 1, round(iv * ne)::int), 90);           -- luôn tăng, tối đa 90 ngày
    ns := case when c.status = 'new' then 'learning' else 'known' end;
  else
    ne := greatest(ez - 0.2::double precision, 1.3::double precision);   -- ease tối thiểu 1.3
    ni := 1;
    ns := case when c.status = 'known' then 'learning' else 'new' end;
  end if;

  update public.cards
     set status = ns, srs_interval = ni, srs_ease = ne, srs_due_date = p_today + ni
   where id = p_card
  returning * into c;
  return c;
end $$;

grant execute on function public.log_study(uuid, uuid, text, timestamptz, date) to authenticated;
grant execute on function public.jp_schema_version() to authenticated, anon;
grant execute on function public.jp_sync_sig() to authenticated;
revoke execute on function public.log_study(uuid, uuid, text, timestamptz, date) from public, anon;
revoke execute on function public.jp_sync_sig() from public, anon;

-- ══ PHIÊN BẢN 8: KIỂM TRA DỮ LIỆU Ở SERVER ═══════════════════════════════════════════════════════
-- App đã kiểm tra dữ liệu ở trình duyệt, nhưng ai cũng có thể gọi API trực tiếp → server phải tự kiểm tra lại.
-- Giới hạn ở đây rộng hơn giới hạn của app (để không chặn nhầm dữ liệu hợp lệ), chỉ nhằm chặn dữ liệu phi lý / quá lớn.
-- "not valid" = chỉ áp dụng cho dữ liệu GHI MỚI/SỬA; dữ liệu cũ đang có không bị kiểm tra lại nên không thể làm hỏng việc chạy schema.
do $$
declare r record;
begin
  for r in select * from (values
    ('cards',          'cards_len_chk',    'length(character) between 1 and 200 and length(meaning_vi) <= 800 and coalesce(length(meaning_en),0) <= 800 and coalesce(length(reading_on),0) <= 400 and coalesce(length(reading_kun),0) <= 400 and coalesce(length(reading_kana),0) <= 400 and coalesce(length(reading_hanviet),0) <= 400 and coalesce(length(romaji),0) <= 400 and coalesce(length(example_jp),0) <= 2000 and coalesce(length(example_vi),0) <= 2000 and coalesce(length(source),0) <= 400 and coalesce(length(notes),0) <= 4000'),
    ('cards',          'cards_num_chk',    'srs_interval between 0 and 3650 and srs_ease between 1 and 5 and (stroke_count is null or stroke_count between 1 and 100) and (jlpt_level is null or jlpt_level in (''N5'',''N4'',''N3'',''N2'',''N1''))'),
    ('decks',          'decks_len_chk',    'length(name) between 1 and 200 and coalesce(length(description),0) <= 1000 and coalesce(length(icon),0) <= 16 and coalesce(length(color),0) <= 32'),
    ('deck_categories','cats_len_chk',     'length(name) between 1 and 200 and coalesce(length(icon),0) <= 16'),
    ('radicals',       'radicals_len_chk', 'length(character) between 1 and 16 and coalesce(length(name),0) <= 200 and coalesce(length(color),0) <= 32'),
    ('user_decompositions','decomp_len_chk','length(character) between 1 and 16 and length(parts) <= 400'),
    ('grammar_points', 'grammar_len_chk',  'length(meaning_vi) <= 600 and coalesce(length(structure),0) <= 600 and coalesce(length(explanation),0) <= 6000 and coalesce(length(examples),0) <= 8000')
  ) as t(tbl, cname, expr)
  loop
    execute format('alter table public.%I drop constraint if exists %I', r.tbl, r.cname);
    execute format('alter table public.%I add constraint %I check (%s) not valid', r.tbl, r.cname, r.expr);
  end loop;
end $$;

-- ══ PHIÊN BẢN 9: TRẠNG THÁI THẸ TÍNH THEO SỐ LẦN HỌC ═══════════════════════════════════════════════
-- study_count = điểm học của thẻ: trả lời đúng +1, trả lời sai −1 (không xuống dưới 0).
-- Chưa học = 0 · Đang học = 1–19 · Đã nhớ = từ 20 trở lên.
-- Cột status do server tự tính từ study_count (trigger), nên không thiết bị nào đặt sai được.
alter table public.cards add column if not exists study_count integer not null default 0;

create or replace function public.jp_status_of(n integer) returns text
language sql immutable as $$ select case when coalesce(n, 0) <= 0 then 'new' when n < 20 then 'learning' else 'known' end $$;

create or replace function public.jp_cards_status() returns trigger
language plpgsql set search_path = public as $$
begin
  new.study_count := greatest(coalesce(new.study_count, 0), 0);
  new.status := public.jp_status_of(new.study_count);
  return new;
end $$;
drop trigger if exists cards_status on public.cards;
create trigger cards_status before insert or update on public.cards
  for each row execute function public.jp_cards_status();

-- Tính lại điểm học từ lịch sử ôn đã có (phát lại theo thời gian, đúng +1 / sai −1, không xuống dưới 0). Chạy lại an toàn.
do $$
declare r record; n int; cur uuid := null;
begin
  update public.cards set study_count = 0 where study_count <> 0 and not exists (select 1 from public.study_sessions s where s.card_id = cards.id);
  for r in select card_id, result from public.study_sessions order by card_id, studied_at, id loop
    if cur is distinct from r.card_id then
      if cur is not null then update public.cards set study_count = n where id = cur and study_count <> n; end if;
      cur := r.card_id; n := 0;
    end if;
    n := case when r.result = 'correct' then n + 1 else greatest(0, n - 1) end;
  end loop;
  if cur is not null then update public.cards set study_count = n where id = cur and study_count <> n; end if;
end $$;
update public.cards set study_count = study_count where status is distinct from public.jp_status_of(study_count);

create or replace function public.log_study(
  p_id uuid, p_card uuid, p_result text,
  p_at timestamptz default now(), p_today date default current_date
) returns public.cards
language plpgsql
set search_path = public
as $$
declare
  c public.cards;
  last_at timestamptz;
  iv int; ez double precision; ne double precision; ni int;
begin
  if p_result not in ('correct', 'incorrect') then
    raise exception 'p_result phải là correct hoặc incorrect';
  end if;
  if not public.jp_is_active() then raise exception 'Tài khoản đang bị khóa' using errcode = '42501'; end if;
  if p_at > now() then p_at := now(); end if;
  select * into c from public.cards where id = p_card for update;
  if not found then return null; end if;

  select max(studied_at) into last_at from public.study_sessions where card_id = p_card;

  insert into public.study_sessions (id, card_id, result, studied_at)
  values (p_id, p_card, p_result, p_at)
  on conflict (id) do nothing;
  if not found then return c; end if;                  -- lượt này đã được ghi trước đó (gửi lại)

  if last_at is not null and p_at < last_at then       -- lượt ôn cũ hơn lượt gần nhất: vẫn tính điểm học, giữ lịch mới
    update public.cards set study_count = case when p_result = 'correct' then study_count + 1 else greatest(0, study_count - 1) end where id = p_card returning * into c;
    return c;
  end if;

  iv := coalesce(nullif(c.srs_interval, 0), 1);
  ez := coalesce(nullif(c.srs_ease, 0), 2.5::double precision);
  if p_result = 'correct' then
    ne := least(ez + 0.1::double precision, 2.8::double precision);
    ni := least(greatest(iv + 1, round(iv * ne)::int), 90);
  else
    ne := greatest(ez - 0.2::double precision, 1.3::double precision);
    ni := 1;
  end if;

  update public.cards
     set study_count = case when p_result = 'correct' then study_count + 1 else greatest(0, study_count - 1) end, srs_interval = ni, srs_ease = ne, srs_due_date = p_today + ni
   where id = p_card
  returning * into c;                                  -- trigger tự đặt status theo study_count
  return c;
end $$;

create or replace function public.jp_schema_version() returns integer
language sql stable as $$ select 9 $$;

-- ══ PHIÊN BẢN 10: BẢNG CHIA ĐỘNG TỪ ══════════════════════════════════════════════════════════════
-- conj_forms : các cột của bảng (thể て, thể ない…), có thể thêm / sửa / xóa / ẩn / đổi thứ tự. kind = loại thể chuẩn (để tự điền), null = cột tự đặt
-- conj_verbs : mỗi hàng là 1 động từ ở thể ます (cột đầu), grp = nhóm 1 / 2 / 3
-- conj_cells : nội dung từng ô (động từ × thể)
create table if not exists public.conj_forms (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name        text not null check (length(name) between 1 and 60),
  kind        text,
  hidden      boolean not null default false,
  sort_order  integer not null default 0,
  version     bigint not null default 1,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists conj_forms_user on public.conj_forms (user_id);

create table if not exists public.conj_verbs (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users(id) on delete cascade,
  masu        text not null check (length(masu) between 1 and 100),
  meaning_vi  text,
  grp         smallint check (grp is null or grp in (1, 2, 3)),
  sort_order  integer not null default 0,
  version     bigint not null default 1,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists conj_verbs_user on public.conj_verbs (user_id);

create table if not exists public.conj_cells (
  verb_id     uuid not null references public.conj_verbs(id) on delete cascade,
  form_id     uuid not null references public.conj_forms(id) on delete cascade,
  user_id     uuid not null default auth.uid() references auth.users(id) on delete cascade,
  value       text not null check (length(value) between 1 and 200),
  updated_at  timestamptz not null default now(),
  primary key (verb_id, form_id)
);
create index if not exists conj_cells_user on public.conj_cells (user_id);

do $$
declare t text;
begin
  foreach t in array array['conj_forms','conj_verbs']
  loop
    execute format('drop trigger if exists trg_touch on public.%I', t);
    execute format('create trigger trg_touch before insert or update on public.%I for each row execute function public.touch_versioned()', t);
  end loop;
  execute 'drop trigger if exists trg_touch on public.conj_cells';
  execute 'create trigger trg_touch before insert or update on public.conj_cells for each row execute function public.touch_updated_at()';
  foreach t in array array['conj_forms','conj_verbs','conj_cells']
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists "own rows" on public.%I', t);
    execute format('create policy "own rows" on public.%I for all to authenticated
                    using (user_id = auth.uid() and public.jp_is_active())
                    with check (user_id = auth.uid() and public.jp_is_active())', t);
  end loop;
end $$;
grant select, insert, update, delete on public.conj_forms, public.conj_verbs, public.conj_cells to authenticated;

-- Chữ ký đồng bộ: thêm 3 bảng mới
create or replace function public.jp_sync_sig() returns text
language sql stable set search_path = public as $$
  select md5(concat_ws('|',
    (select count(*)::text || coalesce(max(updated_at)::text, '') from cards),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from decks),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from radicals),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from deck_cards),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from radical_cards),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from user_decompositions),
    (select count(*)::text || coalesce(max(studied_at)::text, '') from study_sessions),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from grammar_points),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from conj_forms),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from conj_verbs),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from conj_cells),
    (select coalesce(md5(string_agg(id::text || name || coalesce(icon, '') || sort_order::text, ',' order by id)), '') from deck_categories)
  )) $$;
revoke execute on function public.jp_sync_sig() from public, anon;
grant execute on function public.jp_sync_sig() to authenticated;

create or replace function public.jp_schema_version() returns integer
language sql stable as $$ select 10 $$;

-- ══ PHIÊN BẢN 11: BẢN DỊCH (đoạn văn tiếng Nhật + nghĩa tiếng Việt do bạn ghi) ═══════════════════════
create table if not exists public.translations (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users(id) on delete cascade,
  title       text,
  jp          text not null check (length(jp) between 1 and 30000),     -- văn bản tiếng Nhật (1 câu … cả bài dài)
  vi          text check (vi is null or length(vi) <= 40000),           -- bản dịch tiếng Việt
  note        text check (note is null or length(note) <= 3000),
  jlpt_level  text check (jlpt_level is null or jlpt_level in ('N5','N4','N3','N2','N1')),
  version     bigint not null default 1,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists translations_user on public.translations (user_id, created_at desc);
drop trigger if exists trg_touch on public.translations;
create trigger trg_touch before insert or update on public.translations for each row execute function public.touch_versioned();
alter table public.translations enable row level security;
drop policy if exists "own rows" on public.translations;
create policy "own rows" on public.translations for all to authenticated
  using (user_id = auth.uid() and public.jp_is_active()) with check (user_id = auth.uid() and public.jp_is_active());
grant select, insert, update, delete on public.translations to authenticated;

create or replace function public.jp_sync_sig() returns text
language sql stable set search_path = public as $$
  select md5(concat_ws('|',
    (select count(*)::text || coalesce(max(updated_at)::text, '') from cards),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from decks),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from radicals),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from deck_cards),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from radical_cards),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from user_decompositions),
    (select count(*)::text || coalesce(max(studied_at)::text, '') from study_sessions),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from grammar_points),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from conj_forms),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from conj_verbs),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from conj_cells),
    (select count(*)::text || coalesce(max(updated_at)::text, '') from translations),
    (select coalesce(md5(string_agg(id::text || name || coalesce(icon, '') || sort_order::text, ',' order by id)), '') from deck_categories)
  )) $$;
revoke execute on function public.jp_sync_sig() from public, anon;
grant execute on function public.jp_sync_sig() to authenticated;

create or replace function public.jp_schema_version() returns integer
language sql stable as $$ select 11 $$;

-- ══ PHIÊN BẢN 12: CỘT TỪ VỰNG BÊN PHẢI CỦA BẢN DỊCH ═══════════════════════════════════════════════════
-- glossary: mỗi dòng "từ = nghĩa" (như cột từ vựng bên cạnh bài đọc)
alter table public.translations add column if not exists glossary text;
alter table public.translations drop constraint if exists translations_glossary_chk;
alter table public.translations add constraint translations_glossary_chk check (glossary is null or length(glossary) <= 20000) not valid;
create or replace function public.jp_schema_version() returns integer
language sql stable as $$ select 12 $$;

-- Báo cho API nạp lại cấu trúc mới ngay (cột version, hàm log_study)
notify pgrst, 'reload schema';
