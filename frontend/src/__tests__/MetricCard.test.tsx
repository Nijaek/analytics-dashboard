import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { MetricCard } from "@/components/dashboard";

describe("MetricCard", () => {
  it("renders label and numeric value", () => {
    render(<MetricCard label="Total Events" value={1234} />);
    expect(screen.getByText("Total Events")).toBeInTheDocument();
    expect(screen.getByText("1,234")).toBeInTheDocument();
  });

  it("renders label and string value", () => {
    render(<MetricCard label="Top Event" value="page_view" />);
    expect(screen.getByText("Top Event")).toBeInTheDocument();
    expect(screen.getByText("page_view")).toBeInTheDocument();
  });

  it("renders zero correctly", () => {
    render(<MetricCard label="Count" value={0} />);
    expect(screen.getByText("Count")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
  });
});
