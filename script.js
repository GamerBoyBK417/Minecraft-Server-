const form = document.getElementById('orderForm');
const statusMessage = document.getElementById('statusMessage');
const cooldownMessage = document.getElementById('cooldownMessage');
const submitBtn = document.getElementById('submitBtn');

const API_ENDPOINT = '/.netlify/functions/sendTicket';
const COOLDOWN_PERIOD_MS = 2 * 24 * 60 * 60 * 1000; // 2 days

function disableForm() {
  submitBtn.disabled = true;
  [...form.querySelectorAll('input')].forEach(i => i.disabled = true);
}

function checkCooldown() {
  const last = localStorage.getItem('lastTicketSubmission');
  if (!last) return;
  const diff = Date.now() - parseInt(last, 10);
  if (diff < COOLDOWN_PERIOD_MS) {
    const remainingHours = Math.ceil((COOLDOWN_PERIOD_MS - diff) / (1000 * 60 * 60));
    cooldownMessage.textContent = `You can submit another ticket in approximately ${remainingHours} hours.`;
    cooldownMessage.style.display = 'block';
    disableForm();
  }
}
document.addEventListener('DOMContentLoaded', checkCooldown);

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  // Anti-bot check
  if (!document.getElementById('humanCheck').checked) {
    statusMessage.textContent = 'Please confirm you are not a robot.';
    statusMessage.style.color = 'red';
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = 'Submitting...';
  statusMessage.textContent = '';

  const data = {
    fullName: form.fullName.value,
    email: form.email.value,
    mobile: form.mobile.value,
    product: form.product.value,
    paymentMethod: form.paymentMethod.value,
    ticketType: form.ticketType.value
  };

  try {
    const res = await fetch(API_ENDPOINT, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(data)
    });
    if (res.ok) {
      statusMessage.textContent = '✅ Ticket submitted successfully!';
      statusMessage.style.color = 'green';
      form.reset();
      localStorage.setItem('lastTicketSubmission', Date.now().toString());
      checkCooldown();
    } else {
      const err = await res.text();
      statusMessage.textContent = '❌ Failed to submit ticket. '+err;
      statusMessage.style.color = 'red';
      submitBtn.disabled = false;
      submitBtn.textContent = 'Submit Ticket';
    }
  } catch (err) {
    statusMessage.textContent = '❌ Network error. Please try again.';
    statusMessage.style.color = 'red';
    submitBtn.disabled = false;
    submitBtn.textContent = 'Submit Ticket';
  }
});
