create extension if not exists pg_cron with schema pg_catalog;
create extension if not exists pg_net with schema extensions;

create or replace function public.dispatch_github_workflow(
  workflow_file text,
  workflow_inputs jsonb default '{}'::jsonb
) returns bigint
language plpgsql
security definer
set search_path = public, vault, extensions
as $$
declare
  github_token text;
  request_id bigint;
begin
  select decrypted_secret into github_token
  from vault.decrypted_secrets
  where name = 'github_actions_dispatch_token'
  order by created_at desc
  limit 1;

  if github_token is null then
    raise exception 'Vault secret github_actions_dispatch_token is missing';
  end if;

  select net.http_post(
    url := format('https://api.github.com/repos/flight1697/ai-daily-brief/actions/workflows/%s/dispatches', workflow_file),
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || github_token,
      'Accept', 'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'Content-Type', 'application/json'
    ),
    body := jsonb_build_object('ref', 'main', 'inputs', workflow_inputs)
  ) into request_id;
  return request_id;
end;
$$;

revoke all on function public.dispatch_github_workflow(text, jsonb) from public, anon, authenticated;

create or replace function public.dispatch_daily_brief() returns bigint
language plpgsql security definer set search_path = public
as $$
declare target text := to_char((now() at time zone 'Asia/Shanghai')::date - 1, 'YYYY-MM-DD');
begin
  if exists (select 1 from public.runs where target_date = target::date and email_status like 'sent:%') then
    return null;
  end if;
  return public.dispatch_github_workflow('daily.yml', jsonb_build_object(
    'target_date', target, 'dry_run', false, 'scheduled_run', true
  ));
end;
$$;

create or replace function public.dispatch_health_check() returns bigint
language sql security definer set search_path = public
as $$ select public.dispatch_github_workflow('health.yml', jsonb_build_object(
  'target_date', to_char((now() at time zone 'Asia/Shanghai')::date - 1, 'YYYY-MM-DD'), 'send_alert', true
)); $$;

create or replace function public.dispatch_weekly_report() returns bigint
language sql security definer set search_path = public
as $$ select public.dispatch_github_workflow('weekly.yml', jsonb_build_object(
  'target_date', to_char((now() at time zone 'Asia/Shanghai')::date - 1, 'YYYY-MM-DD'), 'send_email', true
)); $$;

create or replace function public.dispatch_pages_refresh() returns bigint
language sql security definer set search_path = public
as $$ select public.dispatch_github_workflow('pages.yml', '{}'::jsonb); $$;

revoke all on function public.dispatch_daily_brief() from public, anon, authenticated;
revoke all on function public.dispatch_health_check() from public, anon, authenticated;
revoke all on function public.dispatch_weekly_report() from public, anon, authenticated;
revoke all on function public.dispatch_pages_refresh() from public, anon, authenticated;

do $$
declare job record;
begin
  for job in select jobid from cron.job where jobname in (
    'ai-daily-primary', 'ai-daily-fallback', 'ai-health-check', 'ai-weekly-report', 'ai-pages-refresh'
  ) loop
    perform cron.unschedule(job.jobid);
  end loop;
end $$;

select cron.schedule('ai-daily-primary', '45 0 * * *', $$select public.dispatch_daily_brief()$$);
select cron.schedule('ai-daily-fallback', '15 1 * * *', $$select public.dispatch_daily_brief()$$);
select cron.schedule('ai-health-check', '0 2 * * *', $$select public.dispatch_health_check()$$);
select cron.schedule('ai-weekly-report', '30 2 * * 1', $$select public.dispatch_weekly_report()$$);
select cron.schedule('ai-pages-refresh', '0 3 * * *', $$select public.dispatch_pages_refresh()$$);
