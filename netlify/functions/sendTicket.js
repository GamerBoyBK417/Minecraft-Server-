// netlify/functions/sendTicket.js
// Node 18+ me fetch available hota hai; node-fetch ki zaroorat nahi.

export async function handler(event, context) {
  // CORS + method guard
  const origin = event.headers.origin || "*";
  const cors = {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
  if (event.httpMethod === "OPTIONS") {
    return { statusCode: 204, headers: cors };
  }
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, headers: cors, body: "Method Not Allowed" };
  }

  try {
    const data = JSON.parse(event.body || "{}");
    const { fullName, email, mobile, product, paymentMethod } = data;

    // Basic validation
    if (!fullName || !email) {
      return {
        statusCode: 400,
        headers: cors,
        body: JSON.stringify({ ok: false, error: "Missing required fields" }),
      };
    }

    // Build Discord embed (server-side)
    const payload = {
      username: "Ticket Bot",
      avatar_url: "https://i.imgur.com/4M34Hi2.png",
      embeds: [
        {
          title: "New Support Ticket Received",
          color: 5814783,
          fields: [
            { name: "Full Name", value: fullName, inline: true },
            { name: "Email", value: email, inline: true },
            { name: "Mobile Number", value: mobile || "—", inline: true },
            { name: "Product", value: product || "—", inline: true },
            { name: "Payment Method", value: paymentMethod || "—", inline: true },
          ],
          timestamp: new Date().toISOString(),
        },
      ],
    };

    // Send to Discord via secret
    const resp = await fetch(process.env.DISCORD_WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const t = await resp.text();
      throw new Error(`Discord error ${resp.status}: ${t}`);
    }

    return {
      statusCode: 200,
      headers: cors,
      body: JSON.stringify({ ok: true }),
    };
  } catch (err) {
    return {
      statusCode: 500,
      headers: cors,
      body: JSON.stringify({ ok: false, error: err.message }),
    };
  }
}
