import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { vi, test, expect, beforeEach, afterEach } from "vitest";
import App from "../App.jsx";
import { apiGet, apiPost } from "../api.js";

vi.mock("../api.js", () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

// fetchNow polls the job every 1500ms of real time, so give waitFor room.
const SLOW = { timeout: 4000 };

function mockApi(job) {
  let queueCalls = 0;
  apiGet.mockImplementation(async (path) => {
    if (path.startsWith("/api/queue")) {
      queueCalls += 1;
      return queueCalls <= 1
        ? { stories: [] }
        : { stories: [{ id: 9, title: "New story", priority: 70, band: "high",
                        n_sources: 1, category: "ports" }] };
    }
    if (path === "/api/settings-status")
      return { default_tier: "api", schedule_hours: 6 };
    if (path === "/api/jobs/j1") return job;
    return {};
  });
  apiPost.mockImplementation(async (path) =>
    path === "/api/fetch-now" ? { job_id: "j1" } : {});
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(cleanup);  // no vitest globals here, so RTL auto-cleanup doesn't register

test("fetch now reports the cycle summary and refreshes the queue", async () => {
  mockApi({ state: "done", result: { items_new: 12, stories_created: 3,
                                      stories_judged: 3, errors: [] } });
  render(<App />);
  expect(await screen.findByText(/queue is empty/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /fetch now/i }));
  expect(await screen.findByText(/12 new items/i, {}, SLOW)).toBeInTheDocument();
  expect(screen.getByText(/3 new stories/i)).toBeInTheDocument();
  expect(await screen.findByText("New story", {}, SLOW)).toBeInTheDocument();  // queue reloaded
}, 10000);

test("fetch now surfaces job errors instead of failing silently", async () => {
  mockApi({ state: "error", error: "httpx.ConnectError: no network" });
  render(<App />);
  expect(await screen.findByText(/queue is empty/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /fetch now/i }));
  expect(await screen.findByText(/no network/i, {}, SLOW)).toBeInTheDocument();
}, 10000);

test("fetch done with no new items still says so", async () => {
  mockApi({ state: "done", result: { items_new: 0, stories_created: 0,
                                     stories_judged: 0, errors: [] } });
  render(<App />);
  expect(await screen.findByText(/queue is empty/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /fetch now/i }));
  expect(await screen.findByText(/0 new items/i, {}, SLOW)).toBeInTheDocument();
}, 10000);
