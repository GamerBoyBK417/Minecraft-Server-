// netlify/functions/sendTicket.js

export async function handler(event, context) {
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

    if (!fullName || !email) {
      return {
        statusCode: 400,
        headers: cors,
        body: JSON.stringify({ ok: false, error: "Missing required fields" }),
      };
    }

    // ---------- 1. Send Ticket to Discord ----------
    const discordPayload = {
      username: "Web Ticket",
      avatar_url: "https://coramtix.in/favicon.svg",
      embeds: [
        {
          title: "🎟️ New Support Ticket",
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

    await fetch(process.env.DISCORD_WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(discordPayload),
    });

    // ---------- 2. Send Confirmation Email ----------
    const emailPayload = {
      from: "support@coramtix.in",  // Verified domain email
      to: email,                    // User's email
      subject: "✅ Your Support Ticket has been Created",
      html: `
        <div style="font-family:Arial,Helvetica,sans-serif;color:#111;">
          <h2 style="color:#2563eb;">Hello ${fullName},</h2>
          <p>Thank you for contacting <b>CoRamTix Support</b>.</p>
          <p>Your ticket has been created successfully. Our team will get back to you within 24 hours.</p>
          <hr style="margin:20px 0;">
          <h3>📌 Ticket Details:</h3>
          <ul>
            <li><b>Full Name:</b> ${fullName}</li>
            <li><b>Email:</b> ${email}</li>
            <li><b>Mobile:</b> ${mobile || "—"}</li>
            <li><b>Product:</b> ${product || "—"}</li>
            <li><b>Payment Method:</b> ${paymentMethod || "—"}</li>
          </ul>
          <br>
          <a href="https://coramtix.in/support" style="display:inline-block;padding:10px 20px;background:#2563eb;color:white;text-decoration:none;border-radius:6px;margin-right:10px;">
            View Ticket Status
          </a>
          <a href="https://discord.gg/s5gWDFt558" style="display:inline-block;padding:10px 20px;background:#5865F2;color:white;text-decoration:none;border-radius:6px;">
            Join Our Discord
          </a>
          <br><br>
          <p>Regards,<br><b>CoRamTix Support Team</b></p>
        </div>
      `,
    };

    await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${process.env.RESEND_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(emailPayload),
    });

    return {
      statusCode: 200,
      headers: cors,
      body: JSON.stringify({ ok: true, message: "Ticket created & email sent" }),
    };

  } catch (err) {
    return {
      statusCode: 500,
      headers: cors,
      body: JSON.stringify({ ok: false, error: err.message }),
    };
  }
}
