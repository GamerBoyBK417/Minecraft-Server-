const form = document.getElementById('orderForm');
const statusMessage = document.getElementById('statusMessage');
const cooldownMessage = document.getElementById('cooldownMessage');
const submitBtn = document.getElementById('submitBtn');

const API_ENDPOINT = '/.netlify/functions/sendOrder';
const COOLDOWN_PERIOD_MS = 2 * 24 * 60 * 60 * 1000; // 2 days

function disableForm() {
  submitBtn.disabled = true;
  Array.from(form.querySelectorAll("input")).forEach(el => (el.disabled = true));
}

function checkCooldown() {
  const last = localStorage.getItem('lastOrderSubmission');
  if (!last) return;
  const diff = Date.now() - parseInt(last, 10);
  if (diff < COOLDOWN_PERIOD_MS) {
    const remainingHours = Math.ceil((COOLDOWN_PERIOD_MS - diff) / (1000 * 60 * 60));
    cooldownMessage.textContent = `You can submit another order in approximately ${remainingHours} hours.`;
    cooldownMessage.classList.remove('hidden');
    disableForm();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('year').textContent = new Date().getFullYear();
  checkCooldown();
});

form.addEventListener('submit', async e => {
  e.preventDefault();

  const honeypot = document.getElementById('honeypot').value;
  const isHuman = document.getElementById('isHuman').checked;
  if (honeypot) return; // silent spam fail
  if (!isHuman) {
    statusMessage.textContent = 'Please check the "I am not a robot" box.';
    statusMessage.style.color = 'red';
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = 'Submitting...';
  statusMessage.textContent = '';

  const data = Object.fromEntries(new FormData(form).entries());

  try {
    const res = await fetch(API_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (res.ok) {
      statusMessage.textContent = '✅ Order ticket submitted successfully!';
      statusMessage.style.color = 'green';
      form.reset();
      localStorage.setItem('lastOrderSubmission', Date.now().toString());
      checkCooldown();
    } else {
      const err = await res.text();
      statusMessage.textContent = '❌ Failed to submit order. ' + err;
      statusMessage.style.color = 'red';
      submitBtn.disabled = false;
      submitBtn.textContent = 'Submit Order';
    }
  } catch (err) {
    console.error(err);
    statusMessage.textContent = '❌ Network error. Please try again.';
    statusMessage.style.color = 'red';
    submitBtn.disabled = false;
    submitBtn.textContent = 'Submit Order';
  }
});
