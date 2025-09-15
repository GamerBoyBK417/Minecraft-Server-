// update year
document.getElementById('copyright-year').textContent = new Date().getFullYear();

// cooldown seconds for anti-spam
const cooldownSeconds = 400;
let lastSubmitTime = 0;

document.getElementById('ticketForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const status = document.getElementById('ticketStatus');
  status.className = 'text-center text-sm mt-2';

  // honeypot anti-bot
  if (document.getElementById('honeypot').value.trim() !== '') {
    // hidden field filled -> bot
    return;
  }

  // check captcha checkbox
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
    // Replace with your backend endpoint
    // await fetch('/api/ticket', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });

    console.log('Ticket payload', payload);

    lastSubmitTime = now;
    status.textContent = '✅ Ticket submitted successfully (demo).';
    status.classList.add('text-green-600');
    e.target.reset();
  } catch (err) {
    status.textContent = '❌ Error submitting ticket.';
    status.classList.add('text-red-500');
  }
});
