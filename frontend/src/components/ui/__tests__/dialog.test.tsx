import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Dialog } from "../Dialog";

describe("Dialog", () => {
  it("renders when open with title and closes on Escape", () => {
    const onClose = vi.fn();
    render(
      <Dialog open onClose={onClose} title="Подтверждение">
        <p>Удалить клип?</p>
      </Dialog>,
    );
    expect(screen.getByRole("dialog", { name: "Подтверждение" })).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("renders nothing when closed", () => {
    render(
      <Dialog open={false} onClose={() => {}} title="x">
        content
      </Dialog>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
