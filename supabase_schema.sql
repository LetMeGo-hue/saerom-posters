-- ============================================================
-- 새롬 포스터 플랫폼용 Supabase 스키마
-- SQL Editor에서 전체를 한 번에 실행하거나, 아래 블록을 나눠 실행하세요.
-- ============================================================

-- ---------- [1] 테이블 ----------
create table if not exists public.posters (
  id bigint generated always as identity primary key,
  image_url text,
  club_name text not null default '',
  event_content text not null default '',
  created_at timestamptz default now()
);

alter table public.posters enable row level security;

-- ---------- [2] 컬럼 추가 ----------
alter table public.posters add column if not exists slug text;
alter table public.posters add column if not exists title text;
alter table public.posters add column if not exists description text;
alter table public.posters add column if not exists category text;
alter table public.posters add column if not exists location text;
alter table public.posters add column if not exists start_date text;
alter table public.posters add column if not exists end_date text;
alter table public.posters add column if not exists detail_url text;
alter table public.posters add column if not exists image_path text;
alter table public.posters add column if not exists delete_pin_hash text;
alter table public.posters add column if not exists updated_at timestamptz default now();

-- image_url 이 NOT NULL 이면 풀어줌 (이미 nullable이면 그냥 통과)
do $$
begin
  begin
    alter table public.posters alter column image_url drop not null;
  exception
    when others then
      null;
  end;
end $$;

-- ---------- [3] 기존 행 채우기 ----------
update public.posters
set
  title = coalesce(nullif(trim(coalesce(title, '')), ''), nullif(trim(coalesce(club_name, '')), ''), '제목 없음'),
  description = coalesce(nullif(trim(coalesce(description, '')), ''), coalesce(event_content, '')),
  slug = coalesce(nullif(trim(coalesce(slug, '')), ''), 'poster-' || id::text),
  updated_at = coalesce(updated_at, created_at, now());

-- slug 중복이 있으면 id 붙여서 고유하게
update public.posters p
set slug = p.slug || '-' || p.id::text
where exists (
  select 1
  from public.posters x
  where x.slug = p.slug
    and x.id < p.id
);

create unique index if not exists posters_slug_unique on public.posters (slug);

-- ---------- [4] posters 테이블 RLS ----------
drop policy if exists "Anyone can read posters" on public.posters;
drop policy if exists "Anyone can insert posters" on public.posters;
drop policy if exists "Anyone can update posters" on public.posters;
drop policy if exists "Anyone can delete posters" on public.posters;

create policy "Anyone can read posters"
  on public.posters for select
  using (true);

create policy "Anyone can insert posters"
  on public.posters for insert
  with check (true);

create policy "Anyone can update posters"
  on public.posters for update
  using (true)
  with check (true);

create policy "Anyone can delete posters"
  on public.posters for delete
  using (true);

-- ---------- [5] Storage 버킷 ----------
insert into storage.buckets (id, name, public)
values ('posters', 'posters', true)
on conflict (id) do update set public = true;

-- ---------- [6] Storage RLS ----------
-- 이름이 달라도 충돌하지 않게 먼저 삭제 후 재생성
drop policy if exists "Anyone can upload poster images" on storage.objects;
drop policy if exists "Anyone can read poster images" on storage.objects;
drop policy if exists "Anyone can delete poster images" on storage.objects;
drop policy if exists "Public read posters" on storage.objects;
drop policy if exists "Public upload posters" on storage.objects;
drop policy if exists "Public delete posters" on storage.objects;

create policy "Anyone can read poster images"
  on storage.objects for select
  using (bucket_id = 'posters');

create policy "Anyone can upload poster images"
  on storage.objects for insert
  with check (bucket_id = 'posters');

create policy "Anyone can delete poster images"
  on storage.objects for delete
  using (bucket_id = 'posters');
