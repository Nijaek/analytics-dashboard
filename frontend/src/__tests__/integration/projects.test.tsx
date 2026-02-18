import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn(), back: vi.fn() }),
  useParams: () => ({}),
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

import ProjectsPage from "@/app/projects/page";

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
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

describe("Projects Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupCookieMock();
    // Simulate authenticated user
    cookieStore["logged_in"] = "true";
  });

  afterEach(() => {
    restoreCookie();
  });

  it("redirects to login when not authenticated", () => {
    delete cookieStore["logged_in"];
    renderWithProviders(<ProjectsPage />);
    expect(mockPush).toHaveBeenCalledWith("/login");
  });

  it("renders project list from API", async () => {
    renderWithProviders(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText("My Website")).toBeInTheDocument();
    });
    expect(screen.getByText("Mobile App")).toBeInTheDocument();
  });

  it("shows project API key prefixes", async () => {
    renderWithProviders(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText("My Website")).toBeInTheDocument();
    });
    // api_key.substring(0, 16) + "..."
    expect(screen.getByText(/proj_abc12345678/)).toBeInTheDocument();
    expect(screen.getByText(/proj_def45678901/)).toBeInTheDocument();
  });

  it("links projects to their dashboard pages", async () => {
    renderWithProviders(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText("My Website")).toBeInTheDocument();
    });

    const link = screen.getByText("My Website").closest("a");
    expect(link).toHaveAttribute("href", "/projects/1");
  });

  it("shows create project form when New Project is clicked", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText("My Website")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "New Project" }));
    expect(screen.getByPlaceholderText("Project name")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("creates a new project via the form", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText("My Website")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "New Project" }));
    await user.type(
      screen.getByPlaceholderText("Project name"),
      "New Project",
    );
    await user.click(screen.getByRole("button", { name: "Create" }));

    // After creation, the form should close (query re-fetch happens)
    await waitFor(() => {
      expect(
        screen.queryByPlaceholderText("Project name"),
      ).not.toBeInTheDocument();
    });
  });

  it("hides create form when Cancel is clicked", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText("My Website")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "New Project" }));
    expect(screen.getByPlaceholderText("Project name")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(
      screen.queryByPlaceholderText("Project name"),
    ).not.toBeInTheDocument();
  });
});
