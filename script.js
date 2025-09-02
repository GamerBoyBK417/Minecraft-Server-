const API_ENDPOINT = '/.netlify/functions/sendTicket';
const COOLDOWN_PERIOD_MS = 2 * 24 * 60 * 60 * 1000;

function disableForm(form) {
  const btn = form.querySelector(".submitBtn");
  btn.disabled = true;
  form.querySelectorAll("input, textarea").forEach(el => (el.disabled = true));
}

function checkCooldown(form) {
  const last = localStorage.getItem('lastTicketSubmission');
  const msg = form.querySelector(".cooldownMessage");
  if (!last) return;
  const diff = Date.now() - parseInt(last, 10);
  if (diff < COOLDOWN_PERIOD_MS) {
    const remainingHours = Math.ceil((COOLDOWN_PERIOD_MS - diff) / (1000 * 60 * 60));
    msg.textContent = `You can submit another ticket in ~${remainingHours} hours.`;
    msg.style.display = 'block';
    disableForm(form);
  }
}

// Attach handler to both forms
document.querySelectorAll("form.ticketForm").forEach(form => {
  document.addEventListener("DOMContentLoaded", () => checkCooldown(form));

  form.addEventListener("submit", async e => {
    e.preventDefault();
    const btn = form.querySelector(".submitBtn");
    const msg = form.querySelector(".statusMessage");

    const email = form.email.value.trim();
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      msg.textContent = "❌ Please enter a valid email address.";
      msg.style.color = "red";
      return;
    }

    btn.disabled = true;
    btn.textContent = "Submitting...";
    msg.textContent = "";

    // Collect fields dynamically
    const data = Object.fromEntries(new FormData(form).entries());

    try {
      const res = await fetch(API_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });

      if (res.ok) {
        msg.innerHTML = "✅ Ticket submitted successfully!<br>💬 Our Support Team is available 24/7.";
        msg.style.color = "green";
        form.reset();
        localStorage.setItem("lastTicketSubmission", Date.now().toString());
        checkCooldown(form);
      } else {
        const err = await res.text();
        msg.textContent = "❌ Failed to submit ticket. " + err;
        msg.style.color = "red";
        btn.disabled = false;
        btn.textContent = "Submit Ticket";
      }
    } catch (err) {
      msg.textContent = "❌ Network error. Please try again.";
      msg.style.color = "red";
      btn.disabled = false;
      btn.textContent = "Submit Ticket";
    }
  });
});
