import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ToastProvider, useToast } from "../Toast";

function Harness() {
  const toast = useToast();
  return (
    <div>
      <button onClick={() => toast.success("Готово")}>ok</button>
      <button onClick={() => toast.error("Сбой")}>bad</button>
    </div>
  );
}

describe("Toast", () => {
  it("renders messages into the live region", () => {
    render(
      <ToastProvider>
        <Harness />
      </ToastProvider>,
    );
    expect(screen.queryByText("Готово")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "ok" }));
    expect(screen.getByText("Готово")).toBeTruthy();
    expect(screen.getByRole("status")).toBeTruthy(); // toast item is announced
    expect(document.querySelector('[aria-label="Уведомления"]')).toBeTruthy();
  });

  it("closes manually", () => {
    render(
      <ToastProvider>
        <Harness />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "bad" }));
    fireEvent.click(screen.getByRole("button", { name: "Закрыть уведомление" }));
    expect(screen.queryByText("Сбой")).toBeNull();
  });

  it("auto-dismisses success toasts", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Harness />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "ok" }));
    act(() => {
      vi.advanceTimersByTime(4100);
    });
    expect(screen.queryByText("Готово")).toBeNull();
    vi.useRealTimers();
  });
});
