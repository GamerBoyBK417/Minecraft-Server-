// Get form elements
const form = document.getElementById('ticketForm');
const statusMessage = document.getElementById('statusMessage');
const cooldownMessage = document.getElementById('cooldownMessage');
const submitBtn = document.getElementById('submitBtn');

// Netlify Function endpoint
const API_ENDPOINT = '/.netlify/functions/sendTicket';

// Cooldown period: 2 days in ms
const COOLDOWN_PERIOD_MS = 2 * 24 * 60 * 60 * 1000;

// Utilities
function disableForm() {
  submitBtn.disabled = true;
  const inputs = form.getElementsByTagName('input');
  for (let i = 0; i < inputs.length; i++) inputs[i].disabled = true;
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

// Submit handler
form.addEventListener('submit', async (event) => {
  event.preventDefault();

  // Anti-spam checks
  const honeypot = document.getElementById('honeypot').value;
  const isHuman = document.getElementById('isHuman').checked;
  if (honeypot) return; // silent fail
  if (!isHuman) {
    statusMessage.textContent = 'Please check the "I am not a robot" box.';
    statusMessage.style.color = 'red';
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = 'Submitting...';
  statusMessage.textContent = '';

  // Collect fields
  const data = {
    fullName: form.fullName.value,
    email: form.email.value,
    mobile: form.mobile.value,
    product: form.product.value,
    paymentMethod: form.paymentMethod.value,
  };

  try {
    const res = await fetch(API_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (res.ok) {
      statusMessage.textContent = '✅ Ticket submitted successfully!';
      statusMessage.style.color = 'green';
      form.reset();
      localStorage.setItem('lastTicketSubmission', Date.now().toString());
      checkCooldown();
    } else {
      const err = await res.text();
      statusMessage.textContent = '❌ Failed to submit ticket. ' + err;
      statusMessage.style.color = 'red';
      submitBtn.disabled = false;
      submitBtn.textContent = 'Submit Ticket';
    }
  } catch (e) {
    console.error(e);
    statusMessage.textContent = '❌ Network error. Please try again.';
    statusMessage.style.color = 'red';
    submitBtn.disabled = false;
    submitBtn.textContent = 'Submit Ticket';
  }
});
