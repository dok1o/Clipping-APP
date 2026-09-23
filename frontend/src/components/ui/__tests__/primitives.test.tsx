import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Button } from "../Button";
import { StatusBadge } from "../StatusBadge";
import { EmptyState, ErrorState, Progress } from "../Feedback";

describe("Button", () => {
  it("renders children and handles clicks", () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Сохранить</Button>);
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("is disabled while loading and announces busy state", () => {
    render(<Button loading>Публикация</Button>);
    const button = screen.getByRole("button") as HTMLButtonElement;
    expect(button.disabled).toBe(true); // jest-dom matchers not installed (minimal deps)
    expect(button.getAttribute("aria-busy")).toBe("true");
  });

  it("disabled button ignores clicks", () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Нет
      </Button>,
    );
    const button = screen.getByRole("button") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe("StatusBadge", () => {
  it("maps domain statuses to human text", () => {
    render(<StatusBadge status="render_failed" />);
    expect(screen.getByText("render failed")).toBeTruthy();
  });
  it("unknown status falls back to neutral style", () => {
    render(<StatusBadge status="weird_one" />);
    expect(screen.getByText("weird one")).toBeTruthy();
  });
});

describe("EmptyState", () => {
  it("shows title and hint", () => {
    render(<EmptyState title="Пока пусто" hint="Загрузите видео" />);
    expect(screen.getByText("Пока пусто")).toBeTruthy();
    expect(screen.getByText("Загрузите видео")).toBeTruthy();
  });
});

describe("ErrorState", () => {
  it("shows message, expandable technical details and retry", () => {
    const onRetry = vi.fn();
    const error = Object.assign(new Error("TikTok отклонил запрос"), {
      code: "platform_error",
      status: 502,
    });
    render(<ErrorState error={error} onRetry={onRetry} context="Публикация" />);
    expect(screen.getByText("TikTok отклонил запрос")).toBeTruthy();
    fireEvent.click(screen.getByText("Технические детали"));
    expect(screen.getByText(/platform_error/)).toBeTruthy();
    fireEvent.click(screen.getByText("Повторить"));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe("Progress", () => {
  it("clamps value into 0..100 and exposes aria", () => {
    render(<Progress value={150} label="Рендер" />);
    const bar = screen.getByRole("progressbar", { name: "Рендер" });
    expect(bar.getAttribute("aria-valuenow")).toBe("100");
  });
});
