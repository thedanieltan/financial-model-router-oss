const form = document.getElementById('saas-form');
const statusEl = document.getElementById('status');

function payloadFromForm(formData) {
  const payload = {};
  for (const [key, value] of formData.entries()) {
    if (['company_name', 'currency'].includes(key)) {
      payload[key] = value;
    } else if (key === 'forecast_months') {
      payload[key] = Number.parseInt(value, 10);
    } else {
      payload[key] = Number.parseFloat(value);
    }
  }
  return payload;
}

function safeFilename(value) {
  const cleaned = String(value || 'saas-budget-forecast')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return `${cleaned || 'saas-budget-forecast'}-saas-budget-forecast.xlsx`;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  statusEl.textContent = 'Generating workbook…';
  const payload = payloadFromForm(new FormData(form));
  try {
    const response = await fetch('/api/v1/practitioner/saas-budget-forecast', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({detail: {message: response.statusText}}));
      throw new Error(error.detail?.message || response.statusText);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = safeFilename(payload.company_name);
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    statusEl.textContent = 'Workbook generated. Check your downloads folder.';
  } catch (error) {
    statusEl.textContent = `Error: ${error.message}`;
  }
});
