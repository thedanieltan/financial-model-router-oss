const PYODIDE_VERSION = "0.29.4";
const PYODIDE_BASE = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
let runtimePromise;

async function initializeRuntime() {
  importScripts(`${PYODIDE_BASE}pyodide.js`);
  const pyodide = await loadPyodide({ indexURL: PYODIDE_BASE });
  await pyodide.loadPackage("micropip");
  const micropip = pyodide.pyimport("micropip");
  const buildResponse = await fetch(new URL("version.json", self.location.href));
  if (!buildResponse.ok) throw new Error(`Unable to load build metadata (${buildResponse.status}).`);
  const build = await buildResponse.json();
  if (typeof build.wheel_asset !== "string" || !build.wheel_asset.endsWith(".whl")) {
    throw new Error("The Pages build did not publish a valid FMR wheel asset.");
  }
  await micropip.install(new URL(build.wheel_asset, self.location.href).href);
  const runtimeSource = await fetch(new URL("demo_runtime.py", self.location.href));
  if (!runtimeSource.ok) throw new Error(`Unable to load demo runtime (${runtimeSource.status}).`);
  await pyodide.runPythonAsync(await runtimeSource.text());
  return pyodide;
}

runtimePromise = initializeRuntime();
runtimePromise.then(() => self.postMessage({ type: "ready" })).catch((error) => {
  self.postMessage({ type: "fatal", error: error.message });
});

self.onmessage = async (event) => {
  const { id, action, payload } = event.data || {};
  try {
    const pyodide = await runtimePromise;
    pyodide.globals.set("fmr_payload_json", JSON.stringify(payload || {}));
    pyodide.globals.set("fmr_execute", action === "execute");
    const result = await pyodide.runPythonAsync("run_demo_json(fmr_payload_json, fmr_execute)");
    self.postMessage({ type: "result", id, result: JSON.parse(result) });
  } catch (error) {
    self.postMessage({ type: "error", id, error: error.message });
  }
};
