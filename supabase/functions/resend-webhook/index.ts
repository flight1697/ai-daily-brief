import { createClient } from "npm:@supabase/supabase-js@2";
import { Webhook } from "npm:svix@1";

type ResendEvent = {
  type: "email.sent" | "email.delivered" | "email.bounced" | "email.complained" | string;
  created_at: string;
  data: {
    email_id: string;
    to?: string[];
    subject?: string;
  };
};

const statusByType: Record<string, string> = {
  "email.sent": "sent",
  "email.delivered": "delivered",
  "email.bounced": "bounced",
  "email.complained": "complained",
};

Deno.serve(async (request) => {
  if (request.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const webhookSecret = Deno.env.get("RESEND_WEBHOOK_SECRET");
  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!webhookSecret || !supabaseUrl || !serviceRoleKey) {
    return new Response("Server is not configured", { status: 500 });
  }

  const payload = await request.text();
  let event: ResendEvent;
  try {
    event = new Webhook(webhookSecret).verify(payload, {
      "svix-id": request.headers.get("svix-id") ?? "",
      "svix-timestamp": request.headers.get("svix-timestamp") ?? "",
      "svix-signature": request.headers.get("svix-signature") ?? "",
    }) as ResendEvent;
  } catch {
    return new Response("Invalid signature", { status: 401 });
  }

  const status = statusByType[event.type];
  if (!status || !event.data?.email_id) {
    return Response.json({ accepted: true, ignored: true });
  }

  const eventColumn: Record<string, string> = {
    delivered: "delivered_at",
    bounced: "bounced_at",
    complained: "complained_at",
    sent: "sent_at",
  };
  const row: Record<string, unknown> = {
    message_id: event.data.email_id,
    recipient: event.data.to?.join(",") ?? "",
    subject: event.data.subject ?? "",
    status,
    last_event_at: event.created_at,
    event_payload: event,
    [eventColumn[status]]: event.created_at,
  };

  const supabase = createClient(supabaseUrl, serviceRoleKey, {
    auth: { persistSession: false },
  });
  const { error } = await supabase.from("deliveries").upsert(row, {
    onConflict: "message_id",
  });
  if (error) {
    console.error(error);
    return new Response("Database write failed", { status: 500 });
  }
  return Response.json({ accepted: true });
});

