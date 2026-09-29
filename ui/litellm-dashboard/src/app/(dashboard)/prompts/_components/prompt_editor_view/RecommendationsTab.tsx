import { useState } from "react";
import ModelSelector from "@/components/common_components/ModelSelector";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getPromptRecommendations, PromptRecommendationsResponse } from "@/components/networking";
import { PromptType } from "./types";
import { convertToDotPrompt } from "./utils";

interface RecommendationsTabProps {
  prompt: PromptType;
  accessToken: string | null;
  onApply: (improvedPrompt: string) => void;
}

const SEVERITIES = ["high", "medium", "low"] as const;

export default function RecommendationsTab({ prompt, accessToken, onApply }: RecommendationsTabProps) {
  const [reviewerModel, setReviewerModel] = useState<string | null>(null);
  const [result, setResult] = useState<{ data: PromptRecommendationsResponse; source: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const source = convertToDotPrompt(prompt);
  const selectedModel = reviewerModel || prompt.model || "";
  const stale = result !== null && result.source !== source;

  const review = async () => {
    if (!accessToken || !selectedModel) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getPromptRecommendations(accessToken, source, selectedModel);
      setResult({ data, source });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not review this prompt");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 p-6 pb-20">
      <div className="space-y-3 rounded-lg border border-border bg-background p-4">
        <div>
          <h2 className="font-medium text-foreground">Improve prompt</h2>
          <p className="text-sm text-muted-foreground">
            Review the draft and suggest a shorter prompt with the same settings and variables
          </p>
        </div>
        <div className="max-w-sm space-y-1">
          <p className="text-sm font-medium">Reviewer model</p>
          <ModelSelector
            accessToken={accessToken || ""}
            value={selectedModel}
            onChange={setReviewerModel}
            showLabel={false}
          />
        </div>
        <Button type="button" onClick={review} disabled={loading || !accessToken || !selectedModel}>
          {loading ? "Reviewing..." : "Review prompt"}
        </Button>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
      </div>

      {result && (
        <>
          {stale && (
            <p role="status" className="text-sm text-warning">
              The draft changed. Run the review again before applying
            </p>
          )}
          <div className="space-y-3">
            <h3 className="font-medium">Recommendations</h3>
            {result.data.recommendations.length === 0 && (
              <p className="text-sm text-muted-foreground">No specific issues found</p>
            )}
            {SEVERITIES.map((severity) => {
              const items = result.data.recommendations.filter((item) => item.severity === severity);
              if (items.length === 0) return null;
              return (
                <div key={severity} className="space-y-2">
                  <h4 className="text-sm font-medium capitalize">{severity} priority</h4>
                  {items.map((item, index) => (
                    <div
                      key={`${severity}-${index}`}
                      className="space-y-1 rounded-lg border border-border bg-background p-3 text-sm"
                    >
                      <Badge variant="secondary">{item.category.replace("_", " ")}</Badge>
                      <p className="font-medium">{item.issue}</p>
                      {item.excerpt && <p className="break-words text-muted-foreground">{item.excerpt}</p>}
                      <p>{item.suggestion}</p>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="font-medium">Shorter draft</h3>
                <p className="text-sm text-muted-foreground">
                  Estimated prompt tokens: {result.data.original_tokens} before, {result.data.improved_tokens} after
                </p>
              </div>
              <Button type="button" onClick={() => onApply(result.data.improved_prompt)} disabled={stale}>
                Apply improved prompt
              </Button>
            </div>
            <div className="grid gap-3 xl:grid-cols-2">
              <div className="min-w-0 rounded-lg border border-border bg-background p-3">
                <h4 className="mb-2 text-sm font-medium">Before</h4>
                <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs">{result.source}</pre>
              </div>
              <div className="min-w-0 rounded-lg border border-border bg-background p-3">
                <h4 className="mb-2 text-sm font-medium">After</h4>
                <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs">
                  {result.data.improved_prompt}
                </pre>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">Applying updates this draft. Publish when you are ready</p>
          </div>
        </>
      )}
    </div>
  );
}
