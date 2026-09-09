import { render, screen, fireEvent } from "@testing-library/react";
import { cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, test, expect, beforeEach, afterEach } from "vitest";
import SourcesView from "../SourcesView.jsx";
import { apiGet, apiPost } from "../../api.js";

vi.mock("../../api.js", () => ({ apiGet: vi.fn(), apiPost: vi.fn() }));

const FIXTURE = { sources: [
  { id: 1, name: "Google News - Saudi ports", kind: "rss", url: "https://news.google.com/rss/ports",
    healthy: true, enabled: true, credibility: 0.6, category_hint: "ports-shipping" },
  { id: 2, name: "Broken feed", kind: "html", url: "https://example.com/news",
    healthy: false, enabled: false, credibility: 0.4, category_hint: null },
] };

beforeEach(() => {
  vi.clearAllMocks();
  apiGet.mockImplementation(async () => FIXTURE);
  apiPost.mockImplementation(async () => ({ status: "added" }));
});
afterEach(cleanup);

test("lists existing sources with health and enabled state", async () => {
  render(<SourcesView />);
  expect(await screen.findByText("Google News - Saudi ports")).toBeInTheDocument();
  expect(screen.getByText("https://news.google.com/rss/ports")).toBeInTheDocument();
  expect(screen.getByText(/unhealthy/i)).toBeInTheDocument();
  expect(screen.getByText(/disabled/i)).toBeInTheDocument();
});

test("adds a source through the form and reloads the list", async () => {
  const user = userEvent.setup();
  render(<SourcesView />);
  expect(await screen.findByText("Google News - Saudi ports")).toBeInTheDocument();

  await user.type(screen.getByLabelText(/name/i), "Zahid feed");
  await user.type(screen.getByLabelText(/url/i), "https://zahid.com/rss");
  await user.click(screen.getByRole("button", { name: /add source/i }));

  expect(apiPost).toHaveBeenCalledWith("/api/sources",
    expect.objectContaining({ name: "Zahid feed", kind: "rss",
                               url: "https://zahid.com/rss" }));
  expect(await screen.findByText(/added/i)).toBeInTheDocument();
  const listReloads = apiGet.mock.calls.filter((c) => c[0] === "/api/sources").length;
  expect(listReloads).toBeGreaterThanOrEqual(2);  // initial + after-add reload
});

test("toggles a source off", async () => {
  const user = userEvent.setup();
  render(<SourcesView />);
  expect(await screen.findByText("Google News - Saudi ports")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /disable/i }));
  expect(apiPost).toHaveBeenCalledWith("/api/sources/1/toggle", { enabled: false });
});

test("shows an error when adding an invalid url", async () => {
  apiPost.mockImplementation(async () => { throw new Error("/api/sources: 400"); });
  const user = userEvent.setup();
  render(<SourcesView />);
  expect(await screen.findByText("Google News - Saudi ports")).toBeInTheDocument();

  await user.type(screen.getByLabelText(/name/i), "X");
  await user.type(screen.getByLabelText(/url/i), "nope");
  await user.click(screen.getByRole("button", { name: /add source/i }));

  expect(await screen.findByText(/400/)).toBeInTheDocument();
});

test("adds a web-search source by topic", async () => {
  const user = userEvent.setup();
  render(<SourcesView />);
  expect(await screen.findByText("Google News - Saudi ports")).toBeInTheDocument();

  await user.selectOptions(screen.getByLabelText(/type/i), "search");
  await user.type(screen.getByLabelText(/name/i), "Red Sea watch");
  const topicInput = screen.getByLabelText(/topic/i);
  await user.type(topicInput, "Red Sea shipping attacks");
  await user.click(screen.getByRole("button", { name: /add source/i }));

  expect(apiPost).toHaveBeenCalledWith("/api/sources",
    expect.objectContaining({ name: "Red Sea watch", kind: "search",
                               topic: "Red Sea shipping attacks", url: null }));
  expect(await screen.findByText(/added/i)).toBeInTheDocument();
});

test("deletes a source after confirming", async () => {
  window.confirm = vi.fn(() => true);
  const user = userEvent.setup();
  render(<SourcesView />);
  expect(await screen.findByText("Google News - Saudi ports")).toBeInTheDocument();

  await user.click(screen.getAllByRole("button", { name: /delete/i })[0]);
  expect(window.confirm).toHaveBeenCalled();
  expect(apiPost).toHaveBeenCalledWith("/api/sources/1/delete");
  expect(await screen.findByText(/deleted/i)).toBeInTheDocument();
});

test("cancel keeps the source", async () => {
  window.confirm = vi.fn(() => false);
  const user = userEvent.setup();
  render(<SourcesView />);
  expect(await screen.findByText("Google News - Saudi ports")).toBeInTheDocument();

  await user.click(screen.getAllByRole("button", { name: /delete/i })[0]);
  expect(apiPost).not.toHaveBeenCalledWith("/api/sources/1/delete");
});
