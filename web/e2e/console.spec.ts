import AxeBuilder from "@axe-core/playwright";
import { type Page, type Route, expect, test } from "@playwright/test";
import deadlines from "./fixtures/deadlines.json" with { type: "json" };
import inbox from "./fixtures/inbox.json" with { type: "json" };
import me from "./fixtures/me.json" with { type: "json" };
import monitor from "./fixtures/monitor.json" with { type: "json" };
import notice from "./fixtures/notice.json" with { type: "json" };
import people from "./fixtures/people.json" with { type: "json" };
import session from "./fixtures/session.json" with { type: "json" };

type Handler = (route: Route) => Promise<void>;
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=",
  "base64",
);

async function mockApi(page: Page, overrides: Record<string, Handler> = {}) {
  const posts: { path: string; body: unknown }[] = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    for (const [prefix, h] of Object.entries(overrides)) if (p.startsWith(prefix)) return h(route);
    if (route.request().method() === "POST" && p !== "/api/dev/sign-in") {
      posts.push({ path: p, body: route.request().postDataJSON() });
      return route.fulfill({ json: { ok: true } });
    }
    if (p === "/api/dev/people") return route.fulfill({ json: people });
    if (p === "/api/dev/sign-in") return route.fulfill({ json: session });
    if (p === "/api/me") return route.fulfill({ json: me });
    if (p === "/api/inbox") return route.fulfill({ json: inbox });
    if (p === "/api/deadlines") return route.fulfill({ json: deadlines });
    if (p === "/api/monitor") return route.fulfill({ json: monitor });
    if (p.endsWith("/page.png")) return route.fulfill({ body: PNG, contentType: "image/png" });
    if (p.startsWith("/api/notices/")) return route.fulfill({ json: notice });
    return route.fulfill({ status: 404, json: { detail: "No such endpoint" } });
  });
  return posts;
}

async function signIn(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Incoming notices" })).toBeVisible();
}

async function accessible(page: Page) {
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== "running"));
  await page.waitForTimeout(400);
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(r.violations.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
}

const toAct = inbox.filter((n) =>
  ["objection_required", "objection_review", "task", "review"].includes(n.action),
);

test("sign-in page is accessible", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByLabel("Person")).toBeVisible();
  await accessible(page);
});

test("the inbox puts what needs action first, soonest deadline on top", async ({ page }) => {
  await mockApi(page);
  await signIn(page);
  await expect(page.getByRole("button", { name: `To act on · ${toAct.length}` })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByRole("region", { name: "Deadlines in the next five weeks" })).toBeVisible();
  const first = page.locator(".list .row").first();
  await expect(first).toContainText(toAct[0].client ?? "Unknown client");
  await accessible(page);
});

test("a notice shows the deadline, the comparison with the return, and why it differs", async ({ page }) => {
  await mockApi(page);
  await signIn(page);
  await page.goto(`/#/notice/${notice.id}`);
  await expect(page.getByRole("heading", { name: /^Deadline / })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Notice against the filed return" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "What differs and why" })).toBeVisible();
  await expect(page.getByLabel(/^Received /)).toBeVisible();
  await accessible(page);
});

test("a clerk confirms the deadline", async ({ page }) => {
  const posts = await mockApi(page);
  await signIn(page);
  await page.goto(`/#/notice/${notice.id}`);
  await page.getByRole("button", { name: "Confirm deadline" }).click();
  await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].path).toMatch(/\/api\/deadlines\/\d+\/confirm/);
});

test("a decision the database refuses explains itself", async ({ page }) => {
  await mockApi(page, {
    [`/api/notices/${notice.id}/decision`]: (route) =>
      route.fulfill({
        status: 409,
        json: { detail: "confirm the deadline first (a second person checks every deadline)" },
      }),
  });
  await page.goto("/");
  await page.evaluate((s) => sessionStorage.setItem("tnd.session", JSON.stringify(s)), {
    ...session,
    person: { ...session.person, role: "advisor" },
  });
  await page.goto(`/#/notice/${notice.id}`);
  await page.reload();
  await page.getByRole("button", { name: "Objection filed" }).click();
  await expect(page.getByRole("alert")).toContainText("confirm the deadline first");
});

test("only an adviser releases a draft, and the verifier's refusal is shown", async ({ page }) => {
  await mockApi(page, {
    "/api/drafts/": (route) =>
      route.fulfill({
        status: 422,
        json: { detail: { title: "The draft cites something the desk cannot back" } },
      }),
  });
  await signIn(page);
  await page.goto(`/#/notice/${notice.id}`);
  await expect(page.getByRole("button", { name: "Release draft" })).toBeDisabled();
  await page.evaluate((s) => sessionStorage.setItem("tnd.session", JSON.stringify(s)), {
    ...session,
    person: { ...session.person, role: "advisor" },
  });
  await page.reload();
  await page.getByRole("button", { name: "Release draft" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "cannot back" })).toBeVisible();
});

test("the deadline register groups by week and confirms", async ({ page }) => {
  const posts = await mockApi(page);
  await signIn(page);
  await page.getByRole("link", { name: "Deadline register" }).click();
  await expect(page.getByRole("heading", { name: "Deadline register" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^Week of / }).first()).toBeVisible();
  await accessible(page);
  await page.getByRole("button", { name: "Confirm" }).first().click();
  await expect.poll(() => posts.length).toBe(1);
});

test("group operations sees numbers per firm and no client data", async ({ page }) => {
  await mockApi(page, {
    "/api/dev/sign-in": (route) =>
      route.fulfill({ json: { ...session, person: { ...session.person, role: "group_ops", firm: null } } }),
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Monitoring" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Notices per firm" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Incoming notices" })).toHaveCount(0);
  await accessible(page);
});

test("a failed load explains itself and retries", async ({ page }) => {
  let calls = 0;
  await mockApi(page, {
    "/api/inbox": async (route) => {
      calls += 1;
      if (calls <= 2) return route.fulfill({ status: 503, json: { detail: "database restarting" } });
      return route.fulfill({ json: inbox });
    },
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("Could not load the notices");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.locator(".list .row").first()).toBeVisible();
});

test("an empty inbox says what comes next", async ({ page }) => {
  await mockApi(page, { "/api/inbox": (route) => route.fulfill({ json: [] }) });
  await page.goto("/");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("No open notices.")).toBeVisible();
});

test("a skeleton shows while notices load", async ({ page }) => {
  await mockApi(page, {
    "/api/inbox": async (route) => {
      await new Promise((r) => setTimeout(r, 800));
      await route.fulfill({ json: inbox });
    },
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByLabel("Loading notices")).toBeVisible();
  await expect(page.locator(".list .row").first()).toBeVisible();
});

test("works on a phone without sideways scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await signIn(page);
  for (const hash of ["#/inbox", `#/notice/${notice.id}`, "#/deadlines"]) {
    await page.goto(`/${hash}`);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, hash).toBeLessThanOrEqual(0);
  }
});
