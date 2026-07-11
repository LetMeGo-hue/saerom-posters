-- 삭제 시 서버 오류 방지용: posters DELETE 정책
-- Supabase SQL Editor에서 실행하세요.

alter table public.posters enable row level security;

drop policy if exists "Anyone can delete posters" on public.posters;
create policy "Anyone can delete posters"
  on public.posters for delete
  using (true);

drop policy if exists "Anyone can delete poster images" on storage.objects;
create policy "Anyone can delete poster images"
  on storage.objects for delete
  using (bucket_id = 'posters');
