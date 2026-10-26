// End-to-end against the real backend (:8000) + Vite (:5173). Captures screenshots into ../screenshots.
// Prereqs: backend running, scripts/seed_demo.py executed (creates a pending change request for proc-agent-07).
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const PW = process.env.SENTRIX_DEMO_PASSWORD ?? "sentrix-demo";
const API = process.env.SENTRIX_API ?? "http://127.0.0.1:8000";
const SHOT = (name: string) => `../screenshots/${name}.png`;

// The backend rate-limits logins (20/min). The suite therefore signs in through the UI once per persona
// and reuses that operator token afterwards, instead of loosening the security control for tests.
const TOKENS: Record<string, string> = {};

async function apiToken(request: APIRequestContext, user: string): Promise<string> {
  if (!TOKENS[user]) {
    const r = await request.post(`${API}/v1/auth/login`, { data: { username: user, password: PW } });
    expect(r.status()).toBe(200);
    TOKENS[user] = (await r.json()).token;
  }
  return TOKENS[user];
}

/** Real UI sign-in through the login form (exercised by the "overview" test). */
async function uiLogin(page: Page, user: string) {
  await page.goto("/");
  await page.getByLabel("Persona").selectOption(user);
  await page.getByLabel("Password").fill(PW);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
}

/** Session for `user` from one cached API login; sets the token before the app boots. */
async function login(page: Page, user: string) {
  const tok = await apiToken(page.request, user);
  await page.goto("/");
  await page.evaluate((t) => sessionStorage.setItem("sentrix.token", t), tok);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
}

async function switchUser(page: Page, user: string) {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByLabel("Persona")).toBeVisible(); // signed out
  await login(page, user);
}

test.describe.configure({ mode: "serial" });

// Each run files its own pending request so the suite is repeatable on an already-approved demo DB.
test.beforeAll(async ({ request }) => {
  const tok = await apiToken(request, "meera");
  const r = await request.post(`${API}/v1/change-requests`, { headers: { Authorization: `Bearer ${tok}` }, data: {
    agent_id: "proc-agent-07", justification: `E2E run ${Date.now()}: raise purchase orders (Flow B)`,
    changes: { add_tools: ["erp.create_po"], add_anchors: [`create purchase orders in ERP (${Date.now()})`] } } });
  expect(r.status()).toBe(201);
});

test("login screen", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("SENTRIX Console")).toBeVisible();
  await expect(page.getByTestId("login-backdrop").locator("canvas")).toBeVisible(); // lazy 3D chunk loaded
  await page.waitForTimeout(1200);
  await page.screenshot({ path: SHOT("01-login") });
});

test("overview shows live, honest system state", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await uiLogin(page, "priya");
  await expect(page.getByText("The seven pillars in this build")).toBeVisible();
  await expect(page.getByRole("img", { name: /constellation of \d+ agents/ })).toBeVisible();
  await page.waitForTimeout(1500); // let the 3D scene render a few frames for the screenshot
  await expect(page.getByText("Verified")).toBeVisible();
  await page.screenshot({ path: SHOT("02-overview"), fullPage: true });
  expect(errors).toEqual([]);
});

test("agents fleet with filter", async ({ page }) => {
  await login(page, "priya");
  await page.getByRole("link", { name: "Agents" }).first().click();
  await expect(page.getByText("Procurement-Agent-07")).toBeVisible();
  await page.screenshot({ path: SHOT("03-agents"), fullPage: true });
});

test("owner cannot approve; security approver approves the seeded change request", async ({ page }) => {
  await login(page, "meera");
  await page.getByRole("link", { name: "Change Requests" }).first().click();
  const pending = page.locator("li", { hasText: "proc-agent-07" }).filter({ hasText: "pending" });
  await expect(pending.first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0); // owner has no approve control
  await page.screenshot({ path: SHOT("04-change-request-pending"), fullPage: true });

  await switchUser(page, "priya");
  await page.getByRole("link", { name: "Change Requests" }).first().click();
  await pending.first().getByRole("button", { name: "Approve" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.screenshot({ path: SHOT("05-approval-confirm") });
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText(/Approved\. Contract is now v\d+/)).toBeVisible();
  await page.screenshot({ path: SHOT("06-change-request-approved"), fullPage: true });
});

test("contract versions verify and diff shows the approved capability", async ({ page }) => {
  await login(page, "priya");
  await page.goto("/contracts/proc-agent-07");
  await expect(page.getByText(/Trusted: owner and security signatures valid/)).toBeVisible();
  await page.getByRole("button", { name: "Compare last two" }).click();
  await expect(page.getByText(/erp\.create_po/).first()).toBeVisible();
  await page.screenshot({ path: SHOT("07-contract-versions-diff"), fullPage: true });
  await expect(page.getByRole("button", { name: "Compile draft" })).toBeDisabled(); // security role cannot author

  await switchUser(page, "arjun");
  await page.goto("/contracts/proc-agent-07");
  await page.getByRole("button", { name: "Compile draft" }).click();
  await expect(page.getByText(/NOT granted/).first()).toBeVisible();
  await page.locator("text=Contract Compiler").scrollIntoViewIfNeeded();
  await page.screenshot({ path: SHOT("08-contract-compiler"), fullPage: true });
});

test("audit chain verifies in the browser", async ({ page }) => {
  await login(page, "auditor");
  await page.getByRole("link", { name: "Audit Log" }).first().click();
  await page.getByRole("button", { name: "Verify chain" }).click();
  await expect(page.getByText(/Chain intact/)).toBeVisible();
  await page.locator("tbody tr").first().click();
  await expect(page.getByText("hash = sha256(event ‖ prev_hash)")).toBeVisible();
  await page.screenshot({ path: SHOT("09-audit-verified"), fullPage: true });
});

test("register an agent in the UI; the one-time secret is shown", async ({ page }) => {
  await login(page, "arjun");
  await page.getByRole("link", { name: "Agents" }).first().click();
  await page.getByRole("button", { name: "Register agent" }).click();
  const id = `e2e-agent-${Date.now()}`;
  await page.getByLabel("Agent ID").fill(id);
  await page.getByLabel("Display name").fill("E2E Support Agent");
  await page.getByLabel("Role", { exact: true }).fill("support");
  await page.getByRole("button", { name: "Register", exact: true }).click();
  await expect(page.getByText(/shown once/)).toBeVisible();
  await page.screenshot({ path: SHOT("11-register-agent-secret") });
  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByRole("cell", { name: new RegExp(id) })).toBeVisible();
});

test("security revokes a live task token from the Credentials page", async ({ page, request }) => {
  const api = API;
  const auth = async (u: string) => ({ Authorization: `Bearer ${await apiToken(request, u)}` });
  const id = `e2e-proc-${Date.now()}`;
  const secret = (await (await request.post(`${api}/v1/agents`, { headers: await auth("arjun"),
    data: { agent_id: id, name: "E2E Procurement", owner: "meera", role: "procurement" } })).json()).agent_secret;
  const contract = { agent_id: id, owner: "meera", role: "procurement", purpose: "Compare supplier prices (E2E)",
    allowed_tools: ["supplier_api.get_quote", "procurement.compare"], data_domains: { allow: ["suppliers/*"], deny: ["hr/*"] },
    anchors: ["retrieve supplier price quotes"] };
  expect((await request.post(`${api}/v1/contracts/${id}/versions`, { headers: await auth("priya"), data: { contract, reviewed: true } })).status()).toBe(201);
  const task = await request.post(`${api}/v1/tasks`, { headers: { "X-Agent-Secret": secret }, data: { agent_id: id, description: "get quotes" } });
  expect(task.status()).toBe(201);

  await login(page, "priya");
  await page.getByRole("link", { name: "Credentials" }).first().click();
  const row = page.locator("tr", { hasText: id });
  await expect(row.getByText("active")).toBeVisible();
  await row.getByRole("button", { name: "Revoke" }).click();
  await page.getByLabel("Reason (audited)").fill("E2E: suspected misuse");
  await page.screenshot({ path: SHOT("12-credentials-revoke") });
  await page.getByRole("button", { name: "Revoke token" }).click();
  await expect(page.getByText(/^Revoked tk-/)).toBeVisible();
  await expect(row.getByText("revoked", { exact: true })).toBeVisible();
});

test("Signal Lab explains the poisoned-quote action with the real engines", async ({ page }) => {
  await login(page, "priya");
  await page.getByRole("link", { name: "Signal Lab" }).first().click();
  await page.getByText("Out-of-role read 1 step after poisoned quote").click();
  await page.getByRole("button", { name: "Analyse" }).click();
  await expect(page.getByText(/Cause: supplier_quote\.pdf, page 2, line 14/)).toBeVisible();
  await expect(page.getByText("deception override", { exact: true })).toBeVisible();
  await expect(page.locator("section", { hasText: "Role-fit evidence" }).getByText("minilm-onnx")).toBeVisible(); // real model, not the fallback
  await page.screenshot({ path: SHOT("13-signal-lab"), fullPage: true });
});

test("drift page charts measured CUSUM with hover readout", async ({ page }) => {
  await login(page, "auditor");
  await page.getByRole("link", { name: "Drift" }).first().click();
  const chart = page.getByRole("img", { name: /CUSUM statistic/ });
  await expect(chart).toBeVisible();
  const box = (await chart.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.55, box.y + box.height * 0.5);
  await expect(page.getByText(/^Window \d+ · /)).toBeVisible();
  await page.screenshot({ path: SHOT("14-drift"), fullPage: true });
});

test("mobile layout has no horizontal overflow", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: "dark" });
  const page = await ctx.newPage();
  await login(page, "priya");
  await expect(page.getByRole("navigation", { name: "Mobile" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.screenshot({ path: SHOT("10-mobile-overview"), fullPage: true });
  await ctx.close();
});
