import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, test, expect, afterEach } from "vitest";
import QueueView from "../QueueView.jsx";
import { apiGet, apiPost } from "../../api.js";

vi.mock("../../api.js", () => ({
  apiGet: vi.fn(async () => ({
    stories: [{
      id: 7, title: "Jeddah expansion", priority: 88, band: "high",
      category: "ports-shipping", n_sources: 3, status: "ranked",
      judge: { gist: "Big capex.", rationale: "Largest this year.",
               scores: { sc: 9, saudi: 10, impact: 8, novelty: 7 } },
    }],
    unscored_count: 0,
  })),
  apiPost: vi.fn(async () => ({ status: "selected" })),
}));
afterEach(cleanup);   // vitest config has no globals:true -> no RTL auto-cleanup

test("renders ranked story with rationale and selects it", async () => {
  const onSelect = vi.fn();
  render(<QueueView onSelect={onSelect} />);
  expect(await screen.findByText("Jeddah expansion")).toBeInTheDocument();
  expect(screen.getByText(/Largest this year/)).toBeInTheDocument();
  expect(screen.getByText("3 sources")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /select/i }));
  expect(onSelect).toHaveBeenCalledWith(7);
});

test("deletes a story after confirming and refreshes", async () => {
  window.confirm = vi.fn(() => true);
  render(<QueueView onSelect={() => {}} />);
  expect(await screen.findByText("Jeddah expansion")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /delete/i }));
  expect(apiPost).toHaveBeenCalledWith("/api/stories/7/delete");
});

test("surfaces unscored stories when no judge is available", async () => {
  apiGet.mockResolvedValueOnce({ stories: [], unscored_count: 12 });
  render(<QueueView onSelect={() => {}} />);

  expect(await screen.findByText(/12 stories waiting to be scored/i)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /show them/i }));
  expect(apiGet).toHaveBeenCalledWith("/api/queue?band=unscored");
});
