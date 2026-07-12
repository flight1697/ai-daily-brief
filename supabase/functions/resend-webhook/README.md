# Resend webhook

This Supabase Edge Function verifies Resend/Svix signatures and persists
`email.sent`, `email.delivered`, `email.bounced`, and `email.complained` events.

Deploy after applying `supabase/migrations/001_metrics.sql`:

```bash
supabase functions deploy resend-webhook --no-verify-jwt
supabase secrets set RESEND_WEBHOOK_SECRET=whsec_xxx
```

Register the resulting function URL in Resend Webhooks. JWT verification is
disabled because Resend cannot provide a Supabase JWT; authenticity is enforced
by the mandatory Svix signature verification in the function.
