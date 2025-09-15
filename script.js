// update year
document.getElementById('copyright-year').textContent = new Date().getFullYear();

const cooldownSeconds = 300; // anti-spam cooldown
let lastSubmitTime = 0;

document.getElementById('orderForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const status = document.getElementById('orderStatus');
  status.className = 'text-center text-sm mt-2';

  // honeypot anti-bot
  if (document.getElementById('honeypot').value.trim() !== '') {
    return;
  }

  // checkbox anti-bot
  if (!document.getElementById('captchaCheck').checked) {
    status.textContent = 'Please confirm you are not a robot.';
    status.classList.add('text-red-500');
    return;
  }

  // cooldown anti-spam
  const now = Date.now();
  if (now - lastSubmitTime < cooldownSeconds * 1000) {
    const remaining = Math.ceil((cooldownSeconds * 1000 - (now - lastSubmitTime)) / 1000);
    status.textContent = `Please wait ${remaining}s before submitting again.`;
    status.classList.add('text-yellow-500');
    return;
  }

  // collect form data
  const formData = new FormData(e.target);
  const payload = Object.fromEntries(formData.entries());

  try {
    const res = await fetch('/.netlify/functions/sendOrder', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      lastSubmitTime = now;
      status.textContent = '✅ Order submitted successfully!';
      status.classList.add('text-green-600');
      e.target.reset();
    } else {
      const errText = await res.text();
      status.textContent = '❌ Failed to submit order. ' + errText;
      status.classList.add('text-red-500');
    }
  } catch (err) {
    status.textContent = '❌ Network error. Please try again.';
    status.classList.add('text-red-500');
  }
});
