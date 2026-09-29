import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getPromptRecommendations } from "@/components/networking";
import RecommendationsTab from "./RecommendationsTab";
import { PromptType } from "./types";

vi.mock("@/components/networking", () => ({ getPromptRecommendations: vi.fn() }));
vi.mock("@/components/common_components/ModelSelector", () => ({
  default: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => (
    <select aria-label="Reviewer model" value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="prompt-model">Prompt model</option>
      <option value="reviewer-model">Reviewer model</option>
    </select>
  ),
}));

const prompt: PromptType = {
  name: "Greeting",
  model: "prompt-model",
  config: {},
  tools: [],
  developerMessage: "",
  messages: [{ role: "user", content: "Please give {{name}} a friendly greeting" }],
  environment: "development",
};

const improvedPrompt = "---\nmodel: prompt-model\n---\nUser: Greet {{name}}";
const result = {
  recommendations: [
    {
      category: "token_efficiency" as const,
      severity: "low" as const,
      excerpt: "friendly greeting",
      issue: "The wording is longer than needed",
      suggestion: "Use a shorter instruction",
    },
  ],
  improved_prompt: improvedPrompt,
  original_tokens: 40,
  improved_tokens: 25,
};

describe("RecommendationsTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getPromptRecommendations).mockResolvedValue(result);
  });

  it("shows the review and applies its rewritten prompt", async () => {
    const user = userEvent.setup();
    const onApply = vi.fn();
    render(<RecommendationsTab prompt={prompt} accessToken="token" onApply={onApply} />);

    await user.selectOptions(screen.getByRole("combobox", { name: "Reviewer model" }), "reviewer-model");
    await user.click(screen.getByRole("button", { name: "Review prompt" }));

    expect(getPromptRecommendations).toHaveBeenCalledWith(
      "token",
      expect.stringContaining("{{name}}"),
      "reviewer-model",
    );
    expect(await screen.findByText("The wording is longer than needed")).toBeInTheDocument();
    expect(screen.getByText("Estimated prompt tokens: 40 before, 25 after")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Apply improved prompt" }));
    expect(onApply).toHaveBeenCalledWith(improvedPrompt);
  });

  it("does not apply a review after the draft changes", async () => {
    const user = userEvent.setup();
    const onApply = vi.fn();
    const view = render(<RecommendationsTab prompt={prompt} accessToken="token" onApply={onApply} />);
    await user.click(screen.getByRole("button", { name: "Review prompt" }));
    await screen.findByText("The wording is longer than needed");

    view.rerender(
      <RecommendationsTab
        prompt={{ ...prompt, messages: [{ role: "user", content: "Different draft" }] }}
        accessToken="token"
        onApply={onApply}
      />,
    );

    expect(screen.getByRole("button", { name: "Apply improved prompt" })).toBeDisabled();
    expect(onApply).not.toHaveBeenCalled();
  });
});
