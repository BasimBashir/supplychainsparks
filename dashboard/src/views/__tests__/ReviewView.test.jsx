import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, test, expect } from "vitest";
import ReviewView from "../ReviewView.jsx";

const api = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }));
vi.mock("../../api.js", () => api);

const DETAIL = {
  story: { id: 3, title: "T", status: "review", priority: 80 },
  sources: [], judge: null,
  generations: [
    { id: 11, format: "article", language: "en", content: "EN body" },
    { id: 12, format: "article", language: "ar", content: "AR body" },
    { id: 13, format: "linkedin", language: "en", content: "hook\n\ninsight" },
  ],
};

test("approve disabled while flags open, enabled after resolve", async () => {
  api.apiGet.mockReset();
  api.apiPost.mockReset();
  let flags = [{ id: 21, claim: "by 2031", verdict: "unsupported" }];
  api.apiGet.mockImplementation(async (p) =>
    p.includes("stories/3")
      ? { ...DETAIL, open_flags: flags }
      : { stories: [{ id: 3, title: "T", status: "review", priority: 80,
                      band: "high", category: "c", n_sources: 1, judge: null }] });
  api.apiPost.mockResolvedValue({ status: "ok" });

  render(<ReviewView onOpen={() => {}} />);
  await userEvent.click(await screen.findByText("T"));
  expect(await screen.findByDisplayValue("EN body")).toBeInTheDocument();
  expect(screen.getByText(/by 2031/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /approve/i })).toBeDisabled();

  flags = [];  // resolve -> next refresh reports no open flags
  await userEvent.click(screen.getByRole("button", { name: /resolve/i }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: /^approve$/i })).toBeEnabled());
});
