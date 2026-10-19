/* JSON calls to the study server. GET without a body, POST with one. */

export class ApiError extends Error {}

export async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new ApiError("The study server is not responding.");
  }
  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    throw new ApiError(payload?.error || `${path} failed with HTTP ${res.status}.`);
  }
  return res.json();
}
