const providerJobEditor = document.querySelector("#provider-job-editor");
const routingPolicy = document.querySelector("#routing-policy");
const providerRoutingStatus = document.querySelector("#provider-routing-status");

async function runProviderAction(path, label) {
  providerRoutingStatus.textContent = "";
  try {
    const job = JSON.parse(providerJobEditor.value);
    const result = await requestJson(`${path}?policy=${encodeURIComponent(routingPolicy.value)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(job),
    });
    showResult(label, result);
  } catch (error) {
    providerRoutingStatus.textContent = error.message;
  }
}

document.querySelector("#route-job-button").addEventListener("click", () => runProviderAction("/api/v2/jobs/routes", "Provider route decision"));
document.querySelector("#prepare-handoff-button").addEventListener("click", () => runProviderAction("/api/v2/jobs/handoffs", "Provider handoff"));
