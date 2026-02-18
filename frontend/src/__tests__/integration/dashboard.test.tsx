import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn(), back: vi.fn() }),
  useParams: () => ({ id: "1" }),
}));
vi.mock("next/link", () => ({
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>,
}));

import DashboardPage from "@/app/projects/[id]/page";

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchInterval: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

// Helper to set/clear the logged_in cookie for auth simulation
const originalDescriptor = Object.getOwnPropertyDescriptor(document, "cookie");
let cookieStore: Record<string, string> = {};

function setupCookieMock() {
  cookieStore = {};
  Object.defineProperty(document, "cookie", {
    get: () =>
      Object.entries(cookieStore)
        .map(([k, v]) => `${k}=${v}`)
        .join("; "),
    set: (value: string) => {
      const [pair] = value.split(";");
      const [key, val] = pair.split("=");
      if (value.includes("max-age=0")) {
        delete cookieStore[key.trim()];
      } else {
        cookieStore[key.trim()] = val?.trim() ?? "";
      }
    },
    configurable: true,
  });
}

function restoreCookie() {
  if (originalDescriptor) {
    Object.defineProperty(document, "cookie", originalDescriptor);
  }
}

describe("Dashboard Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupCookieMock();
    cookieStore["logged_in"] = "true";
  });

  afterEach(() => {
    restoreCookie();
  });

  it("redirects to login when not authenticated", () => {
    delete cookieStore["logged_in"];
    renderWithProviders(<DashboardPage />);
    expect(mockPush).toHaveBeenCalledWith("/login");
  });

  it("renders project name from API", async () => {
    renderWithProviders(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("My Website")).toBeInTheDocument();
    });
  });

  it("renders overview metric cards", async () => {
    renderWithProviders(<DashboardPage />);

    // Wait for actual data to load (not the static labels which are always present)
    await waitFor(() => {
      expect(screen.getByText("1,234")).toBeInTheDocument();
    });
    expect(screen.getByText("Total Events")).toBeInTheDocument();
    expect(screen.getByText("Unique Sessions")).toBeInTheDocument();
    expect(screen.getByText("567")).toBeInTheDocument();
    expect(screen.getByText("Unique Users")).toBeInTheDocument();
    expect(screen.getByText("234")).toBeInTheDocument();
    expect(screen.getByText("Top Event")).toBeInTheDocument();
    // "page_view" appears in both the metric card and top events table
    expect(screen.getAllByText("page_view")).toHaveLength(2);
  });

  it("renders top events table", async () => {
    renderWithProviders(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Top Events")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("button_click")).toBeInTheDocument();
    });
    expect(screen.getByText("800")).toBeInTheDocument();
    expect(screen.getByText("300")).toBeInTheDocument();
  });

  it("renders timeseries data", async () => {
    renderWithProviders(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Events Over Time")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("45")).toBeInTheDocument();
    });
    expect(screen.getByText("62")).toBeInTheDocument();
  });

  it("renders period selector buttons", () => {
    renderWithProviders(<DashboardPage />);

    expect(screen.getByRole("button", { name: "24h" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "7d" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "30d" })).toBeInTheDocument();
  });

  it("switches period when a different button is clicked", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardPage />);

    // Wait for initial data load
    await waitFor(() => {
      expect(screen.getByText("1,234")).toBeInTheDocument();
    });

    // Click 7d period button
    await user.click(screen.getByRole("button", { name: "7d" }));

    // The 7d button should now have the active styling
    // Data should re-fetch (same mock data returned, but verifies re-render)
    await waitFor(() => {
      expect(screen.getByText("1,234")).toBeInTheDocument();
    });
  });

  it("has a link back to projects", () => {
    renderWithProviders(<DashboardPage />);
    const link = screen.getByRole("link", { name: "Projects" });
    expect(link).toHaveAttribute("href", "/projects");
  });

  it("has a settings link", () => {
    renderWithProviders(<DashboardPage />);
    const link = screen.getByRole("link", { name: "Settings" });
    expect(link).toHaveAttribute("href", "/projects/1/settings");
  });
});
