-- 최소 테스트: 이것만 실행해서 posters 테이블이 생기는지 확인하세요.
-- SQL Editor에 붙여넣고 Run

create table if not exists public.posters (
  id bigint generated always as identity primary key,
  slug text,
  title text,
  description text,
  category text,
  location text,
  start_date text,
  end_date text,
  detail_url text,
  image_url text,
  image_path text,
  delete_pin_hash text,
  club_name text not null default '',
  event_content text not null default '',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- 실행 후 확인용 (결과가 1줄 나오면 성공)
select 'posters 테이블 있음' as result
from information_schema.tables
where table_schema = 'public'
  and table_name = 'posters';
